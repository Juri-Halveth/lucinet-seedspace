from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from halveth_nova.engine import NovaEngine
from halveth_nova.jsonutil import canonical_json, sha256_bytes, sha256_json
from halveth_nova.model import Claim
from halveth_nova.store import NovaStore


class IntegrityRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # Match NovaStore's resolved paths, including Windows short temp names.
        self.root = Path(self.tmp.name).resolve()
        self.engine = NovaEngine(self.root)
        self.engine.init("regression")

    def source(self, text="alpha", locator="source.txt"):
        return self.engine.store.ingest_bytes(locator, text.encode("utf-8"))

    def rewrite_receipt(self, change):
        row = self.engine.store.ledger()[0]
        change(row["receipt"])
        row.pop("entry_hash")
        row["entry_hash"] = sha256_json(row)
        self.engine.store.ledger_path.write_text(canonical_json(row)+"\n", encoding="utf-8")
        resume = self.engine.store.read_resume()
        resume["entry_hash"] = row["entry_hash"]
        self.engine.store.resume_path.write_text(canonical_json(resume)+"\n", encoding="utf-8")

    def test_resume_checks_every_continuation_field_and_type(self):
        self.source()
        self.engine.run("alpha", next_seed="original seed")
        original = self.engine.store.resume_path.read_text(encoding="utf-8")
        for field, value in [("next_seed", "different seed"), ("run_id", "run_fake"),
                             ("updated_at", "2000-01-01T00:00:00Z"), ("sequence", True)]:
            with self.subTest(field=field):
                resume = json.loads(original)
                resume[field] = value
                self.engine.store.resume_path.write_text(canonical_json(resume), encoding="utf-8")
                self.assertFalse(self.engine.store.verify()["ok"])
                with self.assertRaises(RuntimeError):
                    self.engine.resume()
        self.engine.store.resume_path.write_text(original, encoding="utf-8")
        self.assertEqual(self.engine.resume()["next_seed"], "original seed")

    def test_restored_source_reactivates_existing_version_and_preserves_history(self):
        first = self.source("alpha")
        before = self.engine.run("alpha")
        second = self.source("beta")
        events_before = self.engine.store.source_events_path.read_bytes()
        restored = self.source("alpha")
        self.assertFalse(restored["created"])
        self.assertEqual(restored["source_id"], first["source_id"])
        self.assertEqual(len(self.engine.store.sources()), 2)
        statuses = self.engine.store.status_map()
        self.assertEqual(statuses[first["source_id"]]["status"], "active")
        self.assertIsNone(statuses[first["source_id"]]["superseded_by"])
        self.assertEqual(statuses[second["source_id"]]["status"], "superseded")
        self.assertEqual(statuses[second["source_id"]]["superseded_by"], first["source_id"])
        self.assertTrue(self.engine.store.source_events_path.read_bytes().startswith(events_before))
        self.assertTrue(self.engine.store.verify()["ok"])
        self.assertEqual(self.engine.store.ledger()[0], before)
        hit = self.engine.search("alpha")[0]
        self.assertTrue(hit["usable_as_current"])

    def test_unchanged_and_retracted_sources_are_not_silently_reactivated(self):
        row = self.source()
        self.engine.store.set_status(row["source_id"], "retracted", note="human correction")
        events = self.engine.store.source_events_path.read_bytes()
        self.source()
        self.assertEqual(self.engine.store.source_events_path.read_bytes(), events)
        self.assertEqual(self.engine.store.status_map()[row["source_id"]]["status"], "retracted")

    def test_restored_retracted_version_displaces_the_other_current_version(self):
        first = self.source("alpha")
        second = self.source("beta")
        self.engine.store.set_status(first["source_id"], "retracted", note="human correction")
        self.source("alpha")
        statuses = self.engine.store.status_map()
        self.assertEqual(statuses[first["source_id"]]["status"], "retracted")
        self.assertEqual(statuses[second["source_id"]]["status"], "superseded")
        self.assertFalse(self.engine.search("beta")[0]["usable_as_current"])

    def test_export_is_locked_while_capturing_and_reads_each_snapshot_file_once(self):
        self.source()
        self.engine.run("alpha")
        target = self.root / "snapshot.zip"
        original = Path.read_bytes
        captured = []
        def observing_read(path):
            if path == self.engine.store.ledger_path:
                with self.assertRaisesRegex(RuntimeError, "WORKSPACE_BUSY"):
                    with NovaStore(self.root).write_lock(timeout=0.05):
                        pass
            if path == self.engine.store.resume_path:
                captured.append(path)
            return original(path)
        with patch.object(Path, "read_bytes", observing_read):
            result = self.engine.store.export_zip(target)
        self.assertEqual(len(captured), 1)
        self.assertNotIn(".nova/write.lock", [row["path"] for row in result["manifest"]["files"]])
        with zipfile.ZipFile(target) as archive:
            for row in result["manifest"]["files"]:
                data = archive.read(row["path"])
                self.assertEqual(len(data), row["bytes"])
                self.assertEqual(sha256_bytes(data), row["sha256"])

    def test_export_archives_the_same_bytes_it_hashes(self):
        self.source()
        self.engine.run("alpha")
        original = Path.read_bytes
        reads = 0
        def changed_on_second_read(path):
            nonlocal reads
            data = original(path)
            if path == self.engine.store.ledger_path:
                reads += 1
                if reads > 1:
                    return data + b"changed between capture and archive\n"
            return data
        target = self.root / "snapshot.zip"
        with patch.object(Path, "read_bytes", changed_on_second_read):
            result = self.engine.store.export_zip(target)
        with zipfile.ZipFile(target) as archive:
            for row in result["manifest"]["files"]:
                self.assertEqual(sha256_bytes(archive.read(row["path"])), row["sha256"])

    def test_export_cannot_overwrite_its_own_workspace(self):
        self.source()
        config = self.engine.store.config_path.read_bytes()
        with self.assertRaises(ValueError):
            self.engine.store.export_zip(self.engine.store.config_path)
        self.assertEqual(self.engine.store.config_path.read_bytes(), config)

    def test_export_rejects_target_inside_linked_nova_directory(self):
        workspace = self.root / "linked-workspace"
        backing = self.root / "linked-data"
        workspace.mkdir()
        backing.mkdir()
        anchor = workspace / ".nova"
        if os.name == "nt":
            result = subprocess.run(["cmd.exe", "/d", "/c", "mklink", "/J", str(anchor), str(backing)],
                                    capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            anchor.symlink_to(backing, target_is_directory=True)
        try:
            self.assertEqual(anchor.resolve(), backing.resolve())
            engine = NovaEngine(workspace)
            engine.init("linked")
            config = engine.store.config_path.read_bytes()
            with self.assertRaises(ValueError):
                engine.store.export_zip(engine.store.config_path)
            self.assertEqual(engine.store.config_path.read_bytes(), config)
        finally:
            # The link and target are both inside this test's owned temp root.
            if os.name == "nt":
                os.rmdir(anchor)
            else:
                anchor.unlink()

    def test_live_writer_is_not_reclaimed_by_age(self):
        with self.engine.store.write_lock():
            old = time.time() - 3600
            os.utime(self.engine.store.lock_path, (old, old))
            with self.assertRaisesRegex(RuntimeError, "WORKSPACE_BUSY"):
                with NovaStore(self.root).write_lock(timeout=0.05, stale_after=0.01):
                    pass

    def test_process_death_releases_lock_without_deleting_lock_file(self):
        code = ("import os,sys; from halveth_nova.store import NovaStore; "
                "s=NovaStore(sys.argv[1]); "
                "\nwith s.write_lock():\n print('LOCKED',flush=True)\n sys.stdin.readline()\n os._exit(0)\n")
        proc = subprocess.Popen([sys.executable, "-c", code, str(self.root)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
        self.assertEqual(proc.stdout.readline().strip(), "LOCKED")
        output, error = proc.communicate("exit\n", timeout=10)
        self.assertEqual(proc.returncode, 0, error)
        with self.engine.store.write_lock(timeout=0.2):
            self.assertTrue(self.engine.store.lock_path.exists())

    def test_aged_live_lock_blocks_a_separate_process(self):
        code = ("import sys; from halveth_nova.store import NovaStore; "
                "\ntry:\n with NovaStore(sys.argv[1]).write_lock(timeout=0.1,stale_after=0):\n  print('ENTERED')\n"
                "except RuntimeError as e:\n print(str(e))\n")
        with self.engine.store.write_lock():
            old = time.time() - 3600
            os.utime(self.engine.store.lock_path, (old, old))
            result = subprocess.run([sys.executable, "-c", code, str(self.root)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "WORKSPACE_BUSY")

    def test_ingest_bounds_reads_and_continues_with_smaller_files(self):
        folder = self.root / "input"
        folder.mkdir()
        large = folder / "large.bin"
        small = folder / "small.txt"
        large.write_bytes(b"X" * 1000)
        small.write_bytes(b"alpha")
        original = Path.read_bytes
        def guard(path):
            if path == large:
                raise AssertionError("unbounded read of oversized source")
            return original(path)
        with patch.object(Path, "read_bytes", guard):
            rows = self.engine.ingest(folder, max_bytes=16)
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(row.get("skipped") == "MAX_BYTES" for row in rows))
        self.assertEqual(self.engine.search("alpha")[0]["locator"], "input/small.txt")

    def test_ingest_also_bounds_a_read_if_file_grows_after_stat(self):
        source = self.root / "grow.txt"
        source.write_bytes(b"a")
        original = Path.open
        class BoundedReader(io.BytesIO):
            def read(reader, size=-1):
                self.assertEqual(size, 17)
                return super().read(size)
        def growing_read(path, *args, **kwargs):
            if path == source and args and args[0] == "rb":
                return BoundedReader(b"x" * 1000)
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", growing_read):
            rows = self.engine.ingest(source, max_bytes=16)
        self.assertEqual(rows[0]["skipped"], "MAX_BYTES")

    def test_invalid_ingest_limits_do_not_mutate_source_inventory(self):
        source = self.root / "input.txt"
        source.write_bytes(b"alpha")
        for value in (-1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.engine.ingest(source, max_bytes=value)
        self.assertEqual(self.engine.store.sources(), [])

    def test_verify_rejects_lost_receipt_sources_and_export(self):
        row = self.source()
        self.engine.run("alpha")
        self.engine.store.sources_path.unlink()
        (self.engine.store.objects / row["digest"]).unlink()
        result = self.engine.store.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("missing source" in error for error in result["errors"]))
        with self.assertRaises(RuntimeError):
            self.engine.store.export_zip(self.root / "incomplete.zip")

    def test_verify_rejects_lost_claim_only_evidence(self):
        row = self.source("evidence")
        self.engine.run("no lexical match", claims=[Claim("candidate", "HYPOTHESIS", [row["source_id"]])])
        self.engine.store.sources_path.unlink()
        self.assertFalse(self.engine.store.verify()["ok"])

    def test_verify_rejects_lost_relation_evidence_without_receipts(self):
        row = self.source()
        self.engine.store.add_relation("A", "SUPPORTS", "B", "hypothesis", [row["source_id"]])
        self.engine.store.sources_path.unlink()
        self.assertFalse(self.engine.store.verify()["ok"])

    def test_verify_rejects_receipt_digest_mismatch_even_with_valid_hash_chain(self):
        self.source()
        self.engine.run("alpha")
        self.rewrite_receipt(lambda receipt: receipt["input_sources"][0].update(digest="0"*64))
        self.assertFalse(self.engine.store.verify()["ok"])

    def test_verify_rejects_missing_visible_relation(self):
        self.engine.store.add_relation("A", "SUPPORTS", "B", "hypothesis", [])
        self.engine.run("alpha")
        self.engine.store.relations_path.unlink()
        self.assertFalse(self.engine.store.verify()["ok"])

    def test_historical_receipts_remain_valid_after_source_retraction(self):
        row = self.source()
        receipt = self.engine.run("alpha")
        self.engine.store.set_status(row["source_id"], "retracted", note="later correction")
        self.assertTrue(self.engine.store.verify()["ok"])
        self.assertEqual(self.engine.store.ledger()[0], receipt)


if __name__ == "__main__":
    unittest.main()
