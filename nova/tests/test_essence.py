from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

from halveth_nova.workbench.controller import Workbench
from halveth_nova.workbench.graph import unknown_key
from halveth_nova.workbench.essence import AXES, REQUEST, detect_association, expand_with_local_model, harvest, plan


def fixture():
    def branch(key, domain, roles):
        return {"id": key, "axis": "cultural_uses" if key == "a" else "scientific_uses",
                "label": "NOVA", "domain": domain, "reading_type": "STRUCTURAL_ANALOGY",
                "statement": "A supplied record, with a separate abstract reading.",
                "evidence": [{"source": key, "quote": "old becomes visible"}], "roles": roles,
                "abstraction_basis": "Explicit example role assignment, requiring semantic review.",
                "differences": ["These domains use different mechanisms."],
                "questions": ["Which source clause would falsify this mapping?"]}
    return {"contract": REQUEST, "seed": {"text": "NOVA", "kind": "NAME", "context": "🌌 NOVA erinnert mich an zwei Dinge"},
            "sources": [{"id": key, "title": key, "origin": "declared:" + key,
                         "text": "🌌 old becomes visible; old becomes visible"} for key in ("a", "b", "c")],
            "branches": [branch("a", "fiction", ["PREEXISTING", "VISIBLE"]),
                         branch("b", "astronomy", ["PREEXISTING", "VISIBLE"]),
                         branch("c", "unrelated", ["INPUT", "OUTPUT"])]}


class EssenceTests(unittest.TestCase):
    def test_cli_rejects_growth_before_ingestion_with_a_bounded_read(self):
        from halveth_nova.cli import main
        with tempfile.TemporaryDirectory() as root:
            work = Workbench(root); work.engine.init("bounded-essence")
            source = (Path(root) / "request.json").resolve()
            source.write_bytes(b"{}")
            original_open, reads = Path.open, []
            class GrowingReader(io.BytesIO):
                def read(self, size=-1):
                    reads.append(size)
                    return super().read(size)
            def opening(path, *args, **kwargs):
                if path == source and (args[0] if args else kwargs.get("mode")) == "rb":
                    return GrowingReader(b"x" * 1_000_002)
                return original_open(path, *args, **kwargs)
            error = io.StringIO()
            with patch.object(Path, "open", opening), redirect_stdout(io.StringIO()), redirect_stderr(error):
                status = main(["--workspace", root, "essence-farm", str(source)])
            self.assertEqual(status, 2)
            self.assertIn("ESSENCE_INPUT_LIMIT", error.getvalue())
            self.assertEqual(reads, [1_000_001])
            self.assertEqual(work.store.sources(), [])

    def test_complete_pair_graph_and_false_friend_control(self):
        result = harvest(fixture())
        self.assertEqual(len(result["comparisons"]), 3)
        self.assertEqual(len(result["candidate_essences"]), 1)
        self.assertEqual(result["candidate_essences"][0]["branch_ids"], ["a", "b"])
        self.assertEqual(result["comparisons"][1]["result"], "NO_SHARED_DECLARED_TRANSITION")

    def test_changed_direction_breaks_candidate(self):
        value = fixture(); value["branches"][1]["roles"].reverse()
        self.assertEqual(harvest(value)["candidate_essences"], [])

    def test_recurrence_can_return_to_an_earlier_role_without_losing_order(self):
        value = fixture(); value["branches"][0]["roles"] = ["PREEXISTING", "VISIBLE", "PREEXISTING"]
        result = harvest(value)
        self.assertEqual(result["branches"][0]["roles"], ["PREEXISTING", "VISIBLE", "PREEXISTING"])
        self.assertTrue(result["candidate_essences"][0]["countertests"][0]["reversed_present"])

    def test_rename_has_no_effect_on_structural_roles(self):
        value = fixture(); value["branches"][1]["label"] = "completely unrelated wording"
        self.assertEqual(harvest(value)["candidate_essences"][0]["branch_ids"], ["a", "b"])

    def test_no_evidence_does_not_produce_source_supported_candidate(self):
        value = fixture(); value["branches"][0]["evidence"] = []
        self.assertEqual(harvest(value)["candidate_essences"], [])

    def test_same_domain_does_not_create_cross_domain_essence(self):
        value = fixture(); value["branches"][1]["domain"] = "fiction"
        self.assertEqual(harvest(value)["candidate_essences"], [])

    def test_unicode_quotes_preserve_all_exact_utf16_spans(self):
        binding = harvest(fixture())["branches"][0]["bindings"][0]
        self.assertEqual(binding["state"], "AMBIGUOUS_SPANS_PRESERVED")
        self.assertEqual(binding["candidate_spans"][0]["start_utf16"], 3)
        self.assertEqual(len(binding["candidate_spans"]), 2)

    def test_fabricated_quote_and_unknown_source_are_rejected(self):
        for source, quote in (("a", "invented"), ("missing", "old becomes visible")):
            value = fixture(); value["branches"][0]["evidence"][0] = {"source": source, "quote": quote}
            with self.assertRaises(ValueError):
                harvest(value)

    def test_undeclared_fields_and_oversized_input_are_rejected(self):
        for mutate in (lambda v: v.update(execute="command"),
                       lambda v: v["seed"].update(context="x" * 8001),
                       lambda v: v["branches"].append(copy.deepcopy(v["branches"][0]))):
            value = fixture(); mutate(value)
            with self.assertRaises(ValueError):
                harvest(value)

    def test_open_plan_preserves_fifteen_axes_without_invented_facts(self):
        result = plan("MAV erinnert mich an MAW und .ETH")
        self.assertEqual({a["id"] for a in result["axes"]}, set(AXES))
        self.assertEqual(len(result["new_seeds"]), 15)
        self.assertEqual(result["branches"], [])
        self.assertEqual(result["coverage"]["external_fetches"], 0)

    def test_cue_is_a_routing_heuristic_not_intent(self):
        self.assertEqual(detect_association("Nova reminds me of a star")["intent"], "UNKNOWN")
        self.assertEqual(detect_association("ordinary unrelated task")["state"], "NO_LEXICAL_CUE")

    def test_different_seed_and_changed_question_do_not_merge_unknown_identity(self):
        value = fixture(); first = harvest(value)["new_seeds"][0]
        value["seed"]["text"] = "MAV"; second = harvest(value)["new_seeds"][0]
        self.assertNotEqual(unknown_key(first), unknown_key(second))
        value = fixture(); value["branches"][0]["questions"][0] = "Which different test now matters?"
        self.assertNotEqual(unknown_key(first), unknown_key(harvest(value)["new_seeds"][0]))

    def test_previous_operator_version_remains_reproducible(self):
        old = harvest(fixture(), operator_version="1.0.0")
        self.assertEqual(old["operator_version"], "1.0.0")
        self.assertNotIn("definition", old["new_seeds"][0])
        self.assertIn("definition", harvest(fixture())["new_seeds"][0])

    def test_relation_addresses_and_domain_differences_are_preserved(self):
        result = harvest(fixture(), recorded_at="2026-10-27T02:00:00Z")
        for pair in result["comparisons"]:
            self.assertEqual(pair["recorded_at"], "2026-10-27T02:00:00Z")
            self.assertEqual(pair["clock_or_timebase"], "CONTROLLER_UTC_WALL_CLOCK")
            for endpoint in (pair["left"], pair["right"]):
                self.assertEqual(len(endpoint["digest"]), 64)
                self.assertIn("field_locator", endpoint["semantic_address"])
        self.assertEqual(len(result["candidate_essences"][0]["differences"]), 2)
        self.assertTrue(all(not c["reversed_present"] for c in result["candidate_essences"][0]["countertests"]))

    def test_controller_automatic_expansion_and_reentry(self):
        with tempfile.TemporaryDirectory() as root:
            work = Workbench(root); work.engine.init("essence")
            source = work.store.ingest_bytes("essence.json", json.dumps(fixture()).encode(), tags=["essence-input"])
            first = work.run("NOVA erinnert mich an Sterne", mode="DEEP")
            farm = first["result"]["essence_farms"][0]
            self.assertEqual(farm["request_ref"]["source_id"], source["source_id"])
            self.assertEqual(len(farm["candidate_essences"]), 1)
            self.assertIn(source["source_id"], json.dumps(work.engine.resume()))
            second = work.run("NOVA erinnert mich an frühere Spuren", mode="DEEP")
            self.assertTrue(any(u["prior_occurrences"] for u in second["result"]["unknowns"]))
            self.assertTrue(work.verify()["ok"])

    def test_retracted_source_does_not_reenter_as_current_essence(self):
        with tempfile.TemporaryDirectory() as root:
            work = Workbench(root); work.engine.init("essence")
            source = work.store.ingest_bytes("essence.json", json.dumps(fixture()).encode(), tags=["essence-input"])
            work.store.set_status(source["source_id"], "retracted")
            result = work.run("NOVA erinnert mich an Sterne", mode="FLOW")["result"]
            self.assertEqual(result["essence_farms"][0]["branches"], [])
            self.assertEqual(len(result["unknowns"]), 15)
            with self.assertRaisesRegex(ValueError, "ACTIVE_ESSENCE_SOURCE_REQUIRED"):
                work.run("NOVA", essence_source=source["source_id"])

    def test_build_contains_real_essence_view_and_keeps_injected_text_as_data(self):
        with tempfile.TemporaryDirectory() as root:
            work = Workbench(root); work.engine.init("essence")
            value = fixture(); value["branches"][0]["label"] = "</script><script>bad()</script>"
            source = work.store.ingest_bytes("essence.json", json.dumps(value).encode(), tags=["essence-input"])
            result = work.run("NOVA", mode="BUILD", essence_source=source["source_id"])["result"]
            page = (Path(root) / result["build"]["viewer"]).read_text(encoding="utf-8")
            self.assertIn("Wissensbaum", page)
            self.assertNotIn("<script>bad()", page)
            self.assertTrue(work.verify()["ok"])

    def compile_response(self, proposal):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"message": {"content": json.dumps(proposal)}}).encode()
        opener = MagicMock(); opener.open.return_value = response
        with patch("halveth_nova.workbench.local_model.local_profile", return_value={"name": "test-local", "digest": "bound"}), \
             patch("halveth_nova.workbench.essence.urllib.request.build_opener", return_value=opener):
            value = fixture(); value["branches"] = []
            return expand_with_local_model(value, model="test-local")

    def test_model_readings_are_compiled_from_source_quotes_and_kept_inferred(self):
        branch = fixture()["branches"][0]; branch["id"] = "ai_a"
        result = self.compile_response({"branches": [branch]})
        self.assertEqual(result["compiler"]["state"], "MODEL_INFERRED")
        self.assertEqual(result["compiler"]["authority"], "NONE")
        self.assertEqual(result["request"]["branches"][0]["id"], "ai_a")

    def test_rejected_model_quote_keeps_exact_response_and_no_active_request(self):
        branch = fixture()["branches"][0]; branch["id"] = "ai_a"
        branch["evidence"][0]["quote"] = "invented source statement"
        result = self.compile_response({"branches": [branch]})
        self.assertIsNone(result["request"])
        self.assertEqual(result["compiler"]["state"], "REJECTED_MODEL_DERIVATION")
        self.assertIn("invented source statement", result["compiler"]["raw_response"])

    def test_missing_cards_never_invoke_a_model_or_external_origin(self):
        value = fixture(); value["branches"] = []; value["sources"] = []
        with patch("halveth_nova.workbench.local_model.local_profile") as profile:
            with self.assertRaisesRegex(ValueError, "SOURCE_CARDS"):
                expand_with_local_model(value, model="test-local")
            profile.assert_not_called()


if __name__ == "__main__":
    unittest.main()
