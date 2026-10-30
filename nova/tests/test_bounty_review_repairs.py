"""Regressions for the four review findings on the bounty impact gate."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from halveth_nova.store import NovaStore
from halveth_nova.workbench.bounty_impact import assess
from test_bounty_impact import base_spec


def bindings(spec):
    return {(row["id"], row["digest"]) for row in spec["evidence_refs"]}


class BountyReviewRepairs(unittest.TestCase):
    def test_padded_unknowns_do_not_pass(self):
        spec = base_spec()
        spec["finding"]["impact"] = " UNKNOWN "
        spec["proof"]["negative_control"] = " UNKNOWN "
        spec["proof"]["remediation_control"] = " UNKNOWN "
        for key in spec["root_cause"]:
            spec["root_cause"][key] = " UNKNOWN "
        result = assess(spec, verified_evidence=bindings(spec))
        self.assertNotEqual(result["state"], "REPORT_CANDIDATE")
        self.assertFalse(result["gates"]["impact_bound"])
        self.assertFalse(result["gates"]["root_cause_bound"])

    def test_id_only_does_not_verify_another_digest(self):
        spec = base_spec()
        verified = bindings(spec)
        spec["evidence_refs"][1]["id"] = spec["evidence_refs"][0]["id"]
        result = assess(spec, verified_evidence=verified)
        self.assertFalse(result["gates"]["evidence_bound"])
        self.assertEqual(result["references"][1]["state"], "DECLARED_NOT_VERIFIED")

    def test_url_path_and_authority_are_bound(self):
        for asset in (
            "https://example.invalid/source/../outside",
            "https://example.invalid/source/%2e%2e/outside",
            "https://other.invalid/source/module",
            "https://example.invalid:bad/source/module",
        ):
            with self.subTest(asset=asset):
                spec = base_spec()
                spec["finding"]["asset"] = asset
                self.assertFalse(assess(spec, verified_evidence=bindings(spec))["gates"]["scope_bound"])

    def test_cli_checks_active_intact_object_and_complete_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = NovaStore(root / "workspace")
            store.init("SYNTHETIC-REVIEW")
            spec = base_spec()
            records = [store.ingest_bytes("fixture/" + kind + ".txt", kind.encode("utf-8"))
                       for kind in ("policy", "scope", "reproduction", "impact", "root_cause")]
            for ref, row in zip(spec["evidence_refs"], records):
                ref.update(id=row["source_id"], digest=row["digest"])
            file = root / "spec.json"
            cli = Path(__file__).parents[1] / "nova.py"

            def run(value):
                file.write_text(json.dumps(value), encoding="utf-8")
                process = subprocess.run(
                    [sys.executable, "-B", str(cli), "--workspace", str(store.root),
                     "bounty-impact", str(file)],
                    capture_output=True, text=True, timeout=15,
                )
                self.assertEqual(process.returncode, 0, process.stderr)
                return json.loads(process.stdout)["result"]

            self.assertEqual(run(spec)["state"], "REPORT_CANDIDATE")
            mismatched = copy.deepcopy(spec)
            for ref in mismatched["evidence_refs"][1:]:
                ref["id"] = records[0]["source_id"]
            self.assertFalse(run(mismatched)["gates"]["evidence_bound"])
            object_path = store.objects / records[0]["digest"]
            original = object_path.read_bytes()
            object_path.write_bytes(b"corrupt")
            self.assertFalse(run(spec)["gates"]["evidence_bound"])
            object_path.write_bytes(original)
            store.set_status(records[0]["source_id"], "retracted", note="synthetic review")
            self.assertFalse(run(spec)["gates"]["evidence_bound"])


if __name__ == "__main__":
    unittest.main()
