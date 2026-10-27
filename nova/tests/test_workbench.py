from __future__ import annotations

import io
import importlib.util
import json
import os
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path
from unittest.mock import patch

from halveth_nova.engine import NovaEngine
from halveth_nova.jsonutil import sha256_json
from halveth_nova.workbench.adapters import MAX_BYTES, extract
from halveth_nova.workbench.controller import Workbench
from halveth_nova.workbench.graph import CONTRACT, structural_match, unknown_key, validate_graph
from halveth_nova.workbench.local_model import bind_compilation
from halveth_nova.workbench.view import render
from halveth_nova.workbench.codegen import build_function, evaluate
from halveth_nova.workbench.value_flow import assess


def graph(name="one", labels=None, domain="test"):
    labels = labels or ["A", "B", "C", "X"]
    return {"contract": CONTRACT, "id": name, "domain": domain,
            "nodes": [{"id": "n" + str(i), "kind": "ACTOR" if i < 3 else "EVENT", "label": v}
                      for i, v in enumerate(labels)],
            "edges": [{"id": "e1", "from": "n0", "to": "n3", "predicate": "OBSERVES"},
                      {"id": "e2", "from": "n1", "to": "n0", "predicate": "RELAYS"},
                      {"id": "e3", "from": "n2", "to": "n1", "predicate": "OBSERVES"}],
            "unknowns": [{"field": "sensor_identity", "referent": "scene17", "scope": "declared-scene",
                          "question": "Which authenticated instruments contributed?", "resolver": "bound sensor receipt"}]}


class GraphTests(unittest.TestCase):
    def test_wordless_structure_transfers_between_declared_domains(self):
        a = graph("one", ["A", "B", "C", "X"], "logical.observers")
        b = graph("two", ["Prisma", "Weitergabe", "Kamera neun", "Wetter"], "logical.messages")
        result = structural_match(a, b)
        self.assertEqual(result["mappings"], [{"n0": "n0", "n1": "n1", "n2": "n2", "n3": "n3"}])
        self.assertTrue(result["cross_domain"])
        self.assertEqual(result["meaning"], "STRUCTURE_MATCH_ONLY")

    def test_reversed_edge_is_a_discriminator(self):
        a, b = graph(), graph("counter")
        b["edges"][1].update({"from": "n0", "to": "n1"})
        self.assertEqual(structural_match(a, b)["mappings"], [])

    def test_alias_labels_never_merge_node_identity(self):
        a = graph(labels=["same", "same", "same", "same"])
        result = structural_match(a, a)
        for mapping in result["mappings"]:
            self.assertEqual(len(set(mapping.values())), 4)

    def test_definitions_and_kinds_remain_bound(self):
        a, b = graph(), graph("other")
        b["nodes"][0]["definition"] = "different-agent-contract"
        self.assertEqual(structural_match(a, b)["mappings"], [])

    def test_budget_result_is_not_reported_as_full_coverage(self):
        self.assertEqual(structural_match(graph(), graph(), budget=1)["coverage"], "FINITE_LIMIT_REACHED")

    def test_missing_endpoint_rejected(self):
        a = graph(); a["edges"][0]["to"] = "absent"
        with self.assertRaises(ValueError):
            validate_graph(a)

    def test_unknowns_do_not_merge_by_wording(self):
        a = graph()["unknowns"][0]
        self.assertNotEqual(unknown_key(a), unknown_key({**a, "referent": "different-scene"}))


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.w = Workbench(self.root); self.w.engine.init("tests")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        p = self.root / name
        p.write_bytes((json.dumps(value) if isinstance(value, dict) else value).encode("utf-8"))
        return p

    def test_modes_execute_different_controllers_and_build_runs_program(self):
        p = self.write("scene.json", graph())
        self.w.index([p])
        results = {mode: self.w.run("scene", mode=mode, pattern=graph()) for mode in ("FLOW", "ATLAS", "DEEP", "BUILD")}
        self.assertNotIn("atlas_structure_and_coverage", results["FLOW"]["result"]["stages"])
        self.assertTrue(results["ATLAS"]["result"]["structural_matches"][0]["mappings"])
        self.assertTrue(results["DEEP"]["result"]["countertests"])
        build = results["BUILD"]["result"]["build"]
        self.assertEqual(build["compile"], "PASS")
        self.assertEqual(build["execution"]["self_check"], "PASS")
        self.assertTrue((self.root / build["viewer"]).is_file())
        self.assertNotIn(str(self.root), json.dumps(results["BUILD"]))
        self.assertEqual(len(self.w.store.ledger()), 4)
        self.assertTrue(self.w.verify()["ok"])

    def test_unknown_history_and_previous_work_survive_resume(self):
        self.w.index([self.write("g.json", graph())])
        first = self.w.run("observation scene", mode="ATLAS")
        second = Workbench(self.root).run("observation", mode="DEEP")
        self.assertEqual(second["result"]["unknowns"][0]["prior_occurrences"][0]["run_id"], first["ledger"]["run_id"])
        self.assertEqual(second["result"]["recovered_runs"][0]["run_id"], first["ledger"]["run_id"])
        self.assertEqual(self.w.engine.resume()["sequence"], 2)

    def test_retracted_parent_has_no_active_structural_graph(self):
        sid = self.w.index([self.write("g.json", graph())])["admitted"][0]
        self.w.store.set_status(sid, "retracted", note="user correction")
        result = self.w.run("scene", mode="ATLAS", pattern=graph())["result"]
        self.assertEqual(result["graphs"], [])
        self.assertFalse(result["hits"][0]["usable_as_current"])

    def test_discovered_python_is_parsed_without_execution(self):
        marker = self.root / "must-not-exist"
        code = f"from pathlib import Path\nPath({str(marker)!r}).write_text('BAD')\n"
        self.w.index([self.write("code.py", code)])
        self.assertFalse(marker.exists())
        self.assertEqual(self.w.analyses()[0]["analysis"]["adapter"], "python-ast")
        self.w.run("code", mode="BUILD")
        self.assertFalse(marker.exists())

    def test_cache_tamper_is_rejected(self):
        self.w.index([self.write("g.json", graph())])
        path = next((self.w.home / "analyses").glob("*.json"))
        value = json.loads(path.read_text()); value["analysis"]["text"] = "changed"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "ANALYSIS_BINDING_CHANGED"):
            self.w.run("scene")

    def test_source_status_change_during_build_has_no_receipt_commit(self):
        sid = self.w.index([self.write("g.json", graph())])["admitted"][0]
        from halveth_nova.workbench.builder import build_kit
        def changing(*args):
            built = build_kit(*args)
            self.w.store.set_status(sid, "retracted", note="parallel correction")
            return built
        with patch("halveth_nova.workbench.builder.build_kit", changing):
            with self.assertRaisesRegex(RuntimeError, "SOURCE_STATE_CHANGED"):
                self.w.run("scene", mode="BUILD")
        self.assertEqual(self.w.store.ledger(), [])

    def test_secret_names_are_not_read(self):
        self.write(".env", "DUMMY_SECRET=synthetic")
        self.write("safe.txt", "benign")
        report = self.w.index([self.root])
        self.assertEqual(report["files_read"], 1)
        self.assertTrue(any(r["reason"] == "EXCLUDED_LOCAL_STATE_OR_SECRET_NAME" for r in report["held"]))

    def test_empty_workspace_coverage_is_explicit(self):
        report = self.w.run("unseen", mode="DEEP")["result"]
        self.assertEqual(report["coverage"]["indexed_sources"], 0)
        self.assertEqual(report["action_requests"][0]["kind"], "NEEDS_GRAPH_OR_COMPILER")

    def test_docx_text_has_derivation_and_layout_gap(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("word/document.xml", '<w:document xmlns:w="urn:test"><w:p><w:t>Hallo Ω</w:t></w:p></w:document>')
        result = extract("a.docx", buffer.getvalue())
        self.assertIn("Hallo Ω", result["text"])
        self.assertTrue(result["gaps"])

    def test_corrupt_docx_becomes_failed_analysis_without_blocking_workspace(self):
        broken = self.root / "broken.docx"
        broken.write_bytes(b"not a zip")
        receipt = self.w.index([broken])
        self.assertEqual(receipt["adapter_failures"][0]["reason"], "BadZipFile")
        self.assertEqual(self.w.analyses()[0]["analysis"]["adapter"], "FAILED")
        self.assertTrue(self.w.run("broken", mode="FLOW")["result"]["hits"])

    def test_index_read_stays_bounded_if_file_grows_after_stat(self):
        source = (self.root / "growing.txt").resolve()
        source.write_bytes(b"x")
        original = Path.open
        reads = []
        class BoundedReader(io.BytesIO):
            def read(reader, size=-1):
                reads.append(size)
                return super().read(size)
        def opening(path, *args, **kwargs):
            if path == source and args and args[0] == "rb":
                return BoundedReader(b"x" * (MAX_BYTES + 100))
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", opening):
            receipt = self.w.index([source])
        self.assertEqual(reads, [MAX_BYTES + 1])
        self.assertEqual(receipt["held"][0]["reason"], "MAX_BYTES_AFTER_READ")
        self.assertEqual(receipt["admitted"], [])

    def test_model_oversized_query_pattern_is_kept_open_not_executed(self):
        nodes = [{"id": "n" + str(i), "kind": "ACTOR", "label": "N" + str(i)} for i in range(9)]
        compiled = {"contract": "nova.local-concept-compilation.v1", "model": "fixture",
                    "provider": "TEST", "endpoint": "NONE", "input_digest": "0" * 64,
                    "response_digest": "1" * 64,
                    "graph": {"contract": CONTRACT, "id": "wide", "domain": "test",
                              "nodes": nodes, "edges": []},
                    "aliases": [], "open_questions": [], "bindings": [], "metrics": {},
                    "state": "MODEL_INFERRED", "authority": "NONE"}
        with patch("halveth_nova.workbench.local_model.compile_concepts", return_value=compiled):
            result = self.w.run("wide query", mode="ATLAS", model="fixture")["result"]
        self.assertEqual(result["coverage"]["task_interpretation"]["reason"], "PATTERN_NODE_LIMIT_8")
        self.assertEqual(result["coverage"]["task_interpretation"]["nodes"], 9)
        self.assertEqual(result["structural_matches"], [])

    def test_wav_signal_is_not_claimed_as_transcription(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as w:
            w.setparams((1, 2, 8000, 0, "NONE", "not compressed")); w.writeframes(b"\0\0" * 800)
        result = extract("a.wav", buffer.getvalue())
        self.assertEqual(result["facts"]["duration_seconds"], 0.1)
        self.assertIn("not speech", result["gaps"][0])

    def test_injected_html_is_kept_as_data(self):
        html = render({"task": "</script><script>alert(1)</script>"})
        self.assertNotIn("alert(1)", html)
        self.assertIn("textContent", html)

    def test_model_cannot_invent_source_quote(self):
        value = {"nodes": [{"id": "A", "kind": "ACTOR", "label": "A", "quote": "not present"}],
                 "edges": [], "aliases": [], "open_questions": []}
        with self.assertRaisesRegex(ValueError, "MODEL_QUOTE_NOT_IN_SOURCE"):
            bind_compilation(value, "A sees X.", model="test", response_digest="0" * 64)

    def test_model_quote_utf16_and_inference_status(self):
        value = {"nodes": [{"id": "A", "kind": "ACTOR", "label": "A", "quote": "A sees X."}],
                 "edges": [], "aliases": [], "open_questions": []}
        result = bind_compilation(value, "🌌 A sees X.", model="test", response_digest="0" * 64)
        self.assertEqual(result["bindings"][0]["start_utf16"], 3)
        self.assertEqual(result["state"], "MODEL_INFERRED")

    def test_repeated_quote_preserves_all_utf16_candidate_spans(self):
        value = {"nodes": [{"id": "A", "kind": "ACTOR", "label": "A", "quote": "A"}],
                 "edges": [], "aliases": [], "open_questions": []}
        bound = bind_compilation(value, "🌌 A A", model="test", response_digest="0" * 64)["bindings"][0]
        self.assertIsNone(bound["start_utf16"])
        self.assertEqual([s["start_utf16"] for s in bound["candidate_spans"]], [3, 5])
        self.assertEqual(bound["binding_state"], "AMBIGUOUS_OCCURRENCES_PRESERVED")

    def test_retracted_origin_also_deactivates_derived_text(self):
        parent = self.w.store.ingest_bytes("original.txt", b"original")
        self.w.store.ingest_bytes("derived.txt", b"derived needle", metadata={
            "parent_source_id": parent["source_id"], "parent_digest": parent["digest"]})
        self.w.compile_sources()
        self.w.store.set_status(parent["source_id"], "retracted", note="user correction")
        hit = self.w.run("needle")["result"]["hits"][0]
        self.assertEqual(hit["status"], "retracted")
        self.assertFalse(hit["usable_as_current"])

    def test_relation_addresses_bind_both_exact_endpoints(self):
        self.w.index([self.write("g.json", graph())])
        result = self.w.run("scene", mode="ATLAS")["result"]
        rel = result["relation_records"][0]
        self.assertEqual(rel["left"]["digest"], sha256_json(graph()["nodes"][0]))
        self.assertEqual(rel["right"]["digest"], sha256_json(graph()["nodes"][3]))
        self.assertEqual(rel["event_time"], "UNKNOWN")
        self.assertTrue(self.w.verify()["ok"])
        rel["right"]["digest"] = "0" * 64
        with patch.object(self.w, "prior_results", return_value=[result]):
            self.assertIn("RELATION_ADDRESS_BINDING_CHANGED", self.w.verify()["errors"])

    def test_generated_kit_tampering_is_detected(self):
        result = self.w.run("build", mode="BUILD")["result"]
        (self.root / result["build"]["viewer"]).write_bytes(b"changed")
        self.assertIn("BUILD_ARTIFACT_CHANGED", self.w.verify()["errors"])

    def test_generated_kit_manifest_tampering_is_detected(self):
        result = self.w.run("build", mode="BUILD")["result"]
        manifest = self.root / result["build"]["directory"] / result["build"]["manifest"]["path"]
        manifest.write_bytes(b'{"compile":"FAIL","files":[]}\n')
        self.assertIn("BUILD_MANIFEST_CHANGED", self.w.verify()["errors"])

    def test_index_budget_leaves_unvisited_tail_explicit(self):
        for n in range(5):
            self.write(str(n) + ".txt", "text")
        receipt = self.w.index([self.root], limit=2)
        self.assertEqual(receipt["files_read"], 2)
        self.assertEqual(receipt["unvisited_tail"], "UNKNOWN")

    def test_new_function_is_searchable_and_recoverable_after_build(self):
        code = "def solve(data):\n    return len(data)\n"
        def generator(target, spec, **kwargs):
            target.mkdir(); (target / "candidate.py").write_text(code)
            (target / "SPEC.json").write_text(json.dumps(spec))
            return {"state": "TESTED_CANDIDATE", "description": spec["description"],
                    "spec_digest": sha256_json(spec), "outcome": evaluate(code, spec["cases"]), "attempts": []}
        spec = {"contract": "nova.pure-build-spec.v1", "description": "cardinality reusable algorithm",
                "cases": [{"id": "one", "input": [7], "expected": 1}]}
        with patch("halveth_nova.workbench.codegen.build_function", generator), patch(
            "halveth_nova.workbench.local_model.compile_concepts", side_effect=ValueError("test no model")):
            built = self.w.run("new capability", mode="BUILD", pattern=graph(), model="fake", build_spec=spec)
        next_run = Workbench(self.root).run("cardinality", mode="ATLAS")["result"]
        self.assertIn(built["ledger"]["run_id"], [r["run_id"] for r in next_run["recovered_runs"]])
        self.assertTrue(any(h["usable_as_current"] for h in next_run["hits"]))
        self.assertTrue(self.w.verify()["ok"])

    def value_record(self):
        spec = json.loads((Path(__file__).resolve().parents[1] / "examples" / "value-flow.json").read_text())
        return self.w.store.ingest_bytes("value-assessment.json", json.dumps(assess(spec)).encode("utf-8"))

    def test_value_measurement_beats_recurring_unrelated_unknown_and_enters_next_seed(self):
        self.w.index([self.write("scene.json", graph())])
        for _ in range(3):
            self.w.run("sensor identity", mode="DEEP")
        self.value_record()
        result = self.w.run("value measurement pilot", mode="DEEP")["result"]
        self.assertEqual(result["selected_unknown"]["field"], "value_measurement_plan")
        self.assertEqual(result["next_seed"]["selected_unknown_id"], result["selected_unknown"]["unknown_id"])
        self.assertIn("measurement plan", result["next_seed"]["next_action"])
        self.assertFalse(result["next_seed"]["authority_inherited"])
        self.assertTrue(any(u["field"] == "sensor_identity" for u in result["unknowns"]))

    def test_legacy_cache_upgrade_retains_old_bytes_and_compiles_new_consumer(self):
        source = self.value_record(); self.w.compile_sources()
        path = self.w.home / "analyses" / (source["source_id"] + ".json")
        row = json.loads(path.read_text()); row.pop("adapter_bundle_version")
        row["analysis"]["adapter"] = "utf8-text"; row["analysis"].pop("unknowns")
        row.pop("analysis_digest"); row["analysis_digest"] = sha256_json(row)
        old_bytes = json.dumps(row).encode(); path.write_bytes(old_bytes)
        result = self.w.run("value measurement", mode="DEEP")["result"]
        old_file = self.w.home / "analysis-history" / (row["analysis_digest"] + ".json")
        self.assertEqual(old_file.read_bytes(), old_bytes)
        self.assertEqual(result["selected_unknown"]["field"], "value_measurement_plan")
        self.assertTrue(self.w.verify()["ok"])
        old_file.write_bytes(b"{}")
        errors = self.w.verify()["errors"]
        self.assertTrue(any(e in errors for e in ("HISTORICAL_ANALYSIS_BINDING_CHANGED",
                                                  "HISTORICAL_ANALYSIS_BYTES_CHANGED")))

    def test_legacy_analysis_archive_deletion_is_detected(self):
        source = self.value_record(); self.w.compile_sources()
        path = self.w.home / "analyses" / (source["source_id"] + ".json")
        row = json.loads(path.read_text()); row.pop("adapter_bundle_version")
        row["analysis"]["adapter"] = "utf8-text"; row["analysis"].pop("unknowns")
        row.pop("analysis_digest"); row["analysis_digest"] = sha256_json(row)
        path.write_bytes(json.dumps(row).encode())
        self.w.run("value measurement", mode="DEEP")
        old_file = self.w.home / "analysis-history" / (row["analysis_digest"] + ".json")
        self.assertTrue(old_file.is_file())
        old_file.unlink()
        self.assertIn("HISTORICAL_ANALYSIS_MISSING", self.w.verify()["errors"])

    def test_retracted_value_assessment_does_not_create_active_measurement_question(self):
        source = self.value_record()
        self.w.store.set_status(source["source_id"], "retracted", note="withdrawn scenario")
        result = self.w.run("value measurement", mode="DEEP")["result"]
        self.assertFalse(any(u["field"].startswith("value_") for u in result["unknowns"]))


class PureFunctionTests(unittest.TestCase):
    def test_real_function_and_type_sensitive_oracle(self):
        cases = [{"id": "sum", "input": [1, 2, 3], "expected": 6}]
        self.assertTrue(evaluate("def solve(data):\n    return sum(data)\n", cases)["passed"])
        self.assertFalse(evaluate("def solve(data):\n    return True\n", [{"id": "type", "input": [], "expected": 1}])["passed"])

    def test_io_import_and_reflection_rejected_before_execution(self):
        for code in ["import os\ndef solve(data): return 1", "def solve(data): return open(data)",
                     "def solve(data): return data.__class__", "def solve(data): return eval(data)"]:
            with self.subTest(code=code), self.assertRaises(ValueError):
                evaluate(code, [{"id": "blocked", "input": "marker", "expected": None}])

    def test_nonterminating_function_hits_time_limit(self):
        result = evaluate("def solve(data):\n    while True:\n        pass\n", [{"id": "loop", "input": 0, "expected": 0}], timeout=1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["error"], "TIME_LIMIT")

    def test_repair_preserves_failed_bytes_and_never_sends_cases(self):
        invalid, valid = "def solve(data):\\n return len(data)", "def solve(data):\n    return len(data)\n"
        def response(code):
            return io.BytesIO(json.dumps({"message": {"content": json.dumps({"code": code})}}).encode())
        requests = []
        def opening(req, **kwargs):
            requests.append(json.loads(req.data))
            return response(invalid if len(requests) == 1 else valid)
        spec = {"contract": "nova.pure-build-spec.v1", "description": "Return the input list length.",
                "cases": [{"id": "NEVER_SEND_THIS_CASE_ID", "input": ["WITHHELD_INPUT_MARKER"], "expected": 1}]}
        with tempfile.TemporaryDirectory() as tmp, patch("halveth_nova.workbench.codegen.local_profile", return_value={}), patch(
            "halveth_nova.workbench.codegen.urllib.request.build_opener") as opener:
            opener.return_value.open.side_effect = opening
            target = Path(tmp) / "function"
            result = build_function(target, spec, model="fixture")
            self.assertEqual(result["state"], "TESTED_CANDIDATE")
            self.assertEqual(len(result["attempts"]), 2)
            self.assertEqual((target / "attempt-01.py").read_text(), invalid)
            self.assertEqual((target / "candidate.py").read_text(), valid)
        self.assertNotIn("WITHHELD_INPUT_MARKER", json.dumps(requests))
        self.assertNotIn("NEVER_SEND_THIS_CASE_ID", json.dumps(requests))


@unittest.skipUnless(importlib.util.find_spec("PIL") and importlib.util.find_spec("av"), "optional media libraries")
class MediaTests(unittest.TestCase):
    def test_real_pixels_and_timed_frame_decoding(self):
        from PIL import Image
        import av
        from halveth_nova.workbench.media import decode
        image = Image.new("RGB", (64, 48), "red")
        buffer = io.BytesIO(); image.save(buffer, format="PNG")
        pixels = extract("red.png", buffer.getvalue())
        self.assertEqual(pixels["facts"]["mean_rgb"], [255, 0, 0])
        buffer = io.BytesIO()
        with av.open(buffer, "w", format="mp4") as container:
            stream = container.add_stream("mpeg4", rate=1)
            stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
            for color in ("red", "blue", "green"):
                for packet in stream.encode(av.VideoFrame.from_image(Image.new("RGB", (64, 48), color))):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)
        result = decode(buffer.getvalue())
        self.assertEqual([f["presentation_seconds"] for f in result["frames"]], [0, 1, 2])
        self.assertNotEqual(result["frames"][0]["sha256"], result["frames"][1]["sha256"])


if __name__ == "__main__":
    unittest.main()
