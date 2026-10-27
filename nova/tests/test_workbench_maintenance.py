"""Bounded regressions for the supplied NOVA workbench review findings."""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from halveth_nova.jsonutil import sha256_json
from halveth_nova.workbench.adapters import MAX_BYTES
from halveth_nova.workbench.controller import Workbench
from halveth_nova.workbench.graph import CONTRACT


def graph(count=2):
    return {"contract": CONTRACT, "id": "scene", "domain": "test.scene",
            "nodes": [{"id": f"n{i}", "kind": "ACTOR", "label": f"scene {i}"}
                      for i in range(count)],
            "edges": [{"id": "edge", "from": "n0", "to": "n1", "predicate": "OBSERVES"}]}


class WorkbenchMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.w = Workbench(self.root)
        self.w.engine.init("maintenance-fixture")

    def tearDown(self):
        self.tmp.cleanup()

    def scene(self):
        p = self.root / "scene.json"
        p.write_text(json.dumps(graph()), encoding="utf-8")
        self.w.index([p])

    def archive(self):
        self.scene()
        p = next((self.w.home / "analyses").glob("*.json"))
        row = json.loads(p.read_text(encoding="utf-8"))
        row.pop("adapter_bundle_version")
        row.pop("analysis_digest")
        row["analysis_digest"] = sha256_json(row)
        raw = json.dumps(row, indent=3).encode("utf-8")
        p.write_bytes(raw)
        self.w.compile_sources()
        archived = self.w.home / "analysis-history" / (row["analysis_digest"] + ".json")
        self.assertEqual(archived.read_bytes(), raw)
        self.assertTrue(self.w.verify()["ok"])
        return archived

    def test_corrupt_docx_leaves_workspace_usable(self):
        p = self.root / "broken.docx"
        p.write_bytes(b"not a zip")
        report = self.w.index([p])
        self.assertEqual(report["adapter_failures"][0]["reason"], "BadZipFile")
        p.unlink()
        self.w.store.set_status(report["admitted"][0], "retracted", note="synthetic input")
        result = self.w.run("continue", mode="DEEP")["result"]
        self.assertEqual(result["graphs"], [])
        self.assertTrue(self.w.verify()["ok"])

    def test_oversized_model_pattern_is_explicit_gap_not_controller_abort(self):
        self.scene()
        for mode in ("ATLAS", "DEEP", "BUILD"):
            with self.subTest(mode=mode), patch(
                    "halveth_nova.workbench.local_model.compile_concepts",
                    return_value={"graph": graph(9), "model": "synthetic"}):
                result = self.w.run("scene", mode=mode, model="synthetic")["result"]
                self.assertEqual(result["coverage"]["task_interpretation"]["state"], "OPEN")
                self.assertEqual(result["structural_matches"], [])
        self.assertTrue(self.w.verify()["ok"])

    def test_explicit_oversized_pattern_is_rejected_before_empty_workspace_run(self):
        with self.assertRaisesRegex(ValueError, "PATTERN_NODE_LIMIT_8"):
            self.w.run("scene", mode="ATLAS", pattern=graph(9))
        self.assertEqual(self.w.store.ledger(), [])

    def test_manifest_replacement_and_loss_fail_verification(self):
        result = self.w.run("build", mode="BUILD")["result"]
        manifest = self.root / result["build"]["directory"] / "BUILD_MANIFEST.json"
        original = manifest.read_bytes()
        for data in (b'{"compile":"FAIL","files":[]}', None):
            with self.subTest(data=data):
                if data is None:
                    manifest.unlink()
                else:
                    manifest.write_bytes(data)
                self.assertFalse(self.w.verify()["ok"])
                manifest.write_bytes(original)
                self.assertTrue(self.w.verify()["ok"])

    def test_manifest_whitespace_changes_are_also_detected(self):
        result = self.w.run("build", mode="BUILD")["result"]
        manifest = self.root / result["build"]["directory"] / "BUILD_MANIFEST.json"
        manifest.write_text(json.dumps(json.loads(manifest.read_text()), indent=2), encoding="utf-8")
        self.assertFalse(self.w.verify()["ok"])

    def test_index_read_is_bounded_when_file_grows_after_stat(self):
        p = (self.root / "growing.txt").resolve()
        p.write_bytes(b"tiny")
        original_open = Path.open
        reads = []
        class GrowingReader(io.BytesIO):
            def read(self, size=-1):
                reads.append(size)
                return super().read(size)
        def opening(path, *args, **kwargs):
            if path == p and (args[0] if args else kwargs.get("mode")) == "rb":
                return GrowingReader(b"x" * (MAX_BYTES + 2))
            return original_open(path, *args, **kwargs)
        with patch.object(Path, "open", opening):
            result = self.w.index([p])
        self.assertEqual(reads, [MAX_BYTES + 1])
        self.assertEqual(result["admitted"], [])
        self.assertEqual(result["held"][0]["reason"], "MAX_BYTES_AFTER_READ")

    def test_archived_analysis_loss_fails_verification(self):
        self.archive().unlink()
        self.assertFalse(self.w.verify()["ok"])

    def test_entire_history_directory_loss_fails_verification(self):
        self.archive()
        shutil.rmtree(self.w.home / "analysis-history")
        self.assertFalse(self.w.verify()["ok"])

    def test_archived_analysis_reformatting_fails_verification(self):
        p = self.archive()
        p.write_text(json.dumps(json.loads(p.read_text()), separators=(",", ":")), encoding="utf-8")
        self.assertFalse(self.w.verify()["ok"])

    def test_new_controller_does_not_rebind_changed_archive_bytes(self):
        p = self.archive()
        p.write_text(json.dumps(json.loads(p.read_text()), indent=1), encoding="utf-8")
        w = Workbench(self.root)
        with self.assertRaisesRegex(ValueError, "HISTORICAL_ANALYSIS_(BINDING|BYTES)_CHANGED"):
            w.compile_sources()

    def test_legacy_history_snapshot_is_explicitly_bound_at_upgrade(self):
        p = self.archive()
        # Bind behavior to the accepted upstream cache-reference contract.
        refs = self.w.analyses()[0]["history_refs"]
        record = next(ref for ref in refs if ref["path"] == p.name)
        self.assertEqual(record["sha256"], hashlib.sha256(p.read_bytes()).hexdigest())
        self.assertEqual(record["bytes"], p.stat().st_size)
        self.assertEqual(len(self.w.analyses()), 1)

    def test_legacy_build_manifest_is_checked_after_upgrade(self):
        from halveth_nova.workbench.builder import finalize_kit
        def legacy_finalize(*args):
            result = finalize_kit(*args)
            result.pop("manifest", None)
            return result
        with patch("halveth_nova.workbench.controller.WORKBENCH_VERSION", "2.0.1"), patch(
                "halveth_nova.workbench.builder.finalize_kit", legacy_finalize):
            result = self.w.run("legacy build", mode="BUILD")["result"]
        self.assertTrue(self.w.verify()["ok"])
        manifest = self.root / result["build"]["directory"] / "BUILD_MANIFEST.json"
        original = manifest.read_bytes()
        manifest.write_bytes(b'{"compile":"FAIL","files":[]}\n')
        self.assertFalse(self.w.verify()["ok"])
        manifest.write_bytes(original)
        self.assertTrue(self.w.verify()["ok"])


if __name__ == "__main__":
    unittest.main()
