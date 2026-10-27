from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from halveth_nova.engine import NovaEngine
from halveth_nova.jsonutil import DuplicateKeyError, strict_loads
from halveth_nova.model import Claim
from halveth_nova.store import NovaStore


class NovaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = NovaEngine(self.root)
        self.engine.init("test-space")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def test_init_is_idempotent(self):
        a = self.engine.store.read_config()
        b = self.engine.init("ignored")
        self.assertEqual(a, b)

    def test_ingest_search_binds_digest_and_lines(self):
        self.write("notes/eye.txt", "erste Zeile\nAugenoptik und Gaze leben hier\ndritte Zeile\n")
        rows = self.engine.ingest(self.root / "notes")
        self.assertEqual(len(rows), 1)
        hit = self.engine.search("Augenoptik Gaze")[0]
        self.assertEqual(hit["locator"], "notes/eye.txt")
        self.assertEqual(hit["line_start"], 1)
        self.assertEqual(hit["line_end"], 3)
        self.assertEqual(len(hit["digest"]), 64)

    def test_unicode_search_keeps_source_span_stable(self):
        self.write("unicode.txt", "Null\nÄquivalenzstraße – Grüße – Ωmega\nEnde\n")
        self.engine.ingest(self.root / "unicode.txt")
        hit = self.engine.search("äquivalenzstraße grüße")[0]
        self.assertIn("Äquivalenzstraße", hit["excerpt"])
        self.assertEqual(hit["line_start"], 1)

    def test_binary_source_is_hashable_and_metadata_searchable(self):
        p = self.root / "red-star.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        row = self.engine.ingest(p, tags=["ghost", "red-star"], metadata={"description": "red thing with halo"})[0]
        hit = self.engine.search("halo ghost")[0]
        self.assertEqual(hit["source_id"], row["source_id"])
        self.assertIsNone(hit["line_start"])

    def test_same_locator_new_bytes_preserve_old_version_as_superseded(self):
        p = self.write("concept.txt", "Pulsar = Schild")
        old = self.engine.ingest(p)[0]
        p.write_text("Pulsar is a neutron star; shield remains historical metaphor", encoding="utf-8")
        new = self.engine.ingest(p)[0]
        self.assertNotEqual(old["source_id"], new["source_id"])
        statuses = self.engine.store.status_map()
        self.assertEqual(statuses[old["source_id"]]["status"], "superseded")
        self.assertEqual(statuses[old["source_id"]]["superseded_by"], new["source_id"])
        self.assertEqual(statuses[new["source_id"]]["status"], "active")

    def test_retracted_high_text_match_remains_visible_but_not_current(self):
        p = self.write("old.txt", "rotes Ding mit Stern rotes Ding mit Stern rotes Ding mit Stern")
        sid = self.engine.ingest(p)[0]["source_id"]
        self.engine.store.set_status(sid, "retracted", note="user corrected interpretation")
        hit = self.engine.search("rotes Ding mit Stern")[0]
        self.assertEqual(hit["status"], "retracted")
        self.assertFalse(hit["usable_as_current"])
        self.assertEqual(self.engine.search("rotes Ding mit Stern", include_retracted=False), [])

    def test_relation_requires_known_evidence_and_typed_predicate(self):
        sid = self.engine.ingest(self.write("a.txt", "A"))[0]["source_id"]
        rel = self.engine.store.add_relation("A", "CONTRADICTS", "B", "hypothesis", [sid])
        self.assertEqual(rel["predicate"], "CONTRADICTS")
        with self.assertRaises(ValueError):
            self.engine.store.add_relation("A", "MAGIC_LINK", "B", "hypothesis", [sid])
        with self.assertRaises(ValueError):
            self.engine.store.add_relation("A", "SUPPORTS", "B", "supported", ["src_missing"])

    def test_run_receipt_binds_sources_claims_open_questions_and_seed(self):
        sid = self.engine.ingest(self.write("source.txt", "distributed witness provenance"))[0]["source_id"]
        env = self.engine.run(
            "distributed witness",
            mode="ATLAS",
            claims=[Claim("provenance appears relevant", "HYPOTHESIS", [sid])],
            open_questions=["where is the original drone source?"],
            artifacts=["map.json"],
            next_seed="reintegrate C-DROHNE",
        )
        receipt = env["receipt"]
        self.assertEqual(receipt["mode"], "ATLAS")
        self.assertEqual(receipt["claims"][0]["state"], "HYPOTHESIS")
        self.assertEqual(receipt["next_seed"], "reintegrate C-DROHNE")
        self.assertEqual(env["sequence"], 1)
        self.assertEqual(len(env["entry_hash"]), 64)

    def test_resume_survives_multiple_runs_and_points_to_latest(self):
        self.engine.ingest(self.write("x.txt", "alpha beta gamma"))
        first = self.engine.run("alpha", next_seed="beta")
        second = self.engine.run("beta", next_seed="gamma", expected_previous_hash=first["entry_hash"])
        resume = self.engine.resume()
        self.assertEqual(resume["sequence"], 2)
        self.assertEqual(resume["entry_hash"], second["entry_hash"])
        self.assertEqual(resume["next_seed"], "gamma")
        self.assertEqual(resume["predecessor_run_id"], first["receipt"]["run_id"])

    def test_stale_predecessor_is_rejected(self):
        self.engine.ingest(self.write("x.txt", "alpha"))
        self.engine.run("alpha")
        with self.assertRaisesRegex(RuntimeError, "STALE_PREDECESSOR"):
            self.engine.run("alpha", expected_previous_hash="0" * 64)

    def test_tampered_ledger_is_detected(self):
        self.engine.ingest(self.write("x.txt", "alpha"))
        self.engine.run("alpha")
        lines = self.engine.store.ledger_path.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[0])
        row["receipt"]["query"] = "tampered"
        self.engine.store.ledger_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
        result = self.engine.store.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("entry hash mismatch" in x for x in result["errors"]))

    def test_tampered_source_object_is_detected(self):
        rec = self.engine.ingest(self.write("x.txt", "alpha"))[0]
        (self.engine.store.objects / rec["digest"]).write_bytes(b"evil")
        result = self.engine.store.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("digest mismatch" in x for x in result["errors"]))

    def test_stale_resume_is_detected(self):
        self.engine.ingest(self.write("x.txt", "alpha"))
        self.engine.run("alpha")
        resume = json.loads(self.engine.store.resume_path.read_text(encoding="utf-8"))
        resume["sequence"] = 999
        self.engine.store.resume_path.write_text(json.dumps(resume), encoding="utf-8")
        result = self.engine.store.verify()
        self.assertFalse(result["ok"])
        self.assertIn("resume is stale", result["errors"])
        with self.assertRaises(RuntimeError):
            self.engine.resume()

    def test_strict_json_rejects_duplicate_keys(self):
        with self.assertRaises(DuplicateKeyError):
            strict_loads('{"x":1,"x":2}')

    def test_export_contains_manifest_and_exact_state(self):
        self.engine.ingest(self.write("x.txt", "alpha"))
        self.engine.run("alpha", next_seed="continue")
        target = self.root / "export.zip"
        result = self.engine.store.export_zip(target)
        second = self.root / "export-2.zip"
        result2 = self.engine.store.export_zip(second)
        self.assertEqual(result["sha256"], result2["sha256"])
        self.assertEqual(result["files"], len(result["manifest"]["files"]))
        with zipfile.ZipFile(target) as z:
            self.assertIn("NOVA_EXPORT_MANIFEST.json", z.namelist())
            manifest = json.loads(z.read("NOVA_EXPORT_MANIFEST.json"))
            self.assertEqual(manifest["workspace"], "test-space")
            self.assertIn(".nova/ledger.jsonl", [x["path"] for x in manifest["files"]])

    def test_directory_ingest_skips_oversized_file_without_losing_small_one(self):
        d = self.root / "bulk"; d.mkdir()
        (d / "small.txt").write_text("small searchable", encoding="utf-8")
        (d / "large.bin").write_bytes(b"x" * 100)
        rows = self.engine.ingest(d, max_bytes=50)
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(r.get("skipped") == "MAX_BYTES" for r in rows))
        self.assertEqual(self.engine.search("searchable")[0]["locator"], "bulk/small.txt")

    def test_source_status_requires_existing_source(self):
        with self.assertRaises(KeyError):
            self.engine.store.set_status("src_missing", "retracted")

    def test_invalid_claim_state_is_rejected(self):
        self.engine.ingest(self.write("x.txt", "alpha"))
        with self.assertRaises(ValueError):
            self.engine.run("alpha", claims=[Claim("bad", "CERTAIN_TRUTH", [])])

    def test_search_ranks_active_above_retracted_when_text_is_equal(self):
        a = self.engine.store.ingest_bytes("a.txt", b"same exact concept same exact concept")
        b = self.engine.store.ingest_bytes("b.txt", b"same exact concept same exact concept")
        self.engine.store.set_status(a["source_id"], "retracted")
        hits = self.engine.search("same exact concept")
        self.assertEqual(hits[0]["source_id"], b["source_id"])
        self.assertEqual(hits[-1]["source_id"], a["source_id"])

    def test_external_ingest_does_not_leak_absolute_parent_path(self):
        outside_tmp = tempfile.TemporaryDirectory()
        try:
            p = Path(outside_tmp.name) / "secret-machine-path.txt"
            p.write_text("portable source", encoding="utf-8")
            row = self.engine.ingest(p)[0]
            self.assertTrue(row["locator"].startswith("external/"))
            self.assertNotIn(outside_tmp.name, row["locator"])
            self.assertIn("secret-machine-path.txt", row["locator"])
        finally:
            outside_tmp.cleanup()

    def test_receipt_predecessor_binding_rejects_race_even_without_explicit_expected_hash(self):
        self.engine.ingest(self.write("x.txt", "alpha"))
        first = self.engine.run("alpha")
        stale_receipt = dict(first["receipt"])
        stale_receipt["run_id"] = "run_stale"
        stale_receipt["created_at"] = "2026-10-27T00:00:00Z"
        stale_receipt["predecessor_entry_hash"] = None
        with self.assertRaisesRegex(RuntimeError, "STALE_PREDECESSOR"):
            self.engine.store.append_receipt(stale_receipt)

    def test_verify_healthy_workspace(self):
        self.engine.ingest(self.write("x.txt", "alpha"))
        self.engine.run("alpha")
        result = self.engine.store.verify()
        self.assertTrue(result["ok"], result["errors"])
        self.assertEqual(result["source_count"], 1)
        self.assertEqual(result["ledger_count"], 1)


if __name__ == "__main__":
    unittest.main()
