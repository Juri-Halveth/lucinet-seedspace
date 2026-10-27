import copy
import json
import unittest
from pathlib import Path

from halveth_nova.workbench.value_flow import assess


class ValueTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((Path(__file__).resolve().parents[1] / "examples" / "value-flow.json").read_text())

    def test_missing_measurement_stays_an_actionable_question(self):
        result = assess(self.spec)
        self.assertEqual(result["open_questions"][0]["facet"], "measurement_plan")
        self.assertEqual(result["valuation"], "OPEN")
        self.assertFalse(result["creator_status_used_as_multiplier"])

    def test_declared_scenario_accounts_for_adoption_and_both_costs(self):
        self.spec["business_case"] = {"baseline_unit_cost": "10", "candidate_unit_cost": "6", "units": "1000",
            "adoption_fraction": "0.5", "integration_cost": "500", "ongoing_cost": "100", "currency": "EUR",
            "period": "synthetic month", "input_basis": "DECLARED_SCENARIO"}
        result = assess(self.spec)
        self.assertEqual(result["business_case"]["net_saving"], "1400.0")
        self.assertEqual(result["funding_decision"], "OPEN")

    def test_negative_result_is_retained(self):
        self.spec["business_case"] = {"baseline_unit_cost": "1", "candidate_unit_cost": "3", "units": "10",
            "adoption_fraction": "1", "integration_cost": "5", "ongoing_cost": "2", "currency": "EUR",
            "period": "synthetic month", "input_basis": "DECLARED_SCENARIO"}
        self.assertEqual(assess(self.spec)["business_case"]["net_saving"], "-27")

    def test_injected_title_or_observed_flag_is_not_accepted(self):
        for key in ("creator_degree", "creator_status", "observed"):
            other = copy.deepcopy(self.spec); other[key] = "professor"
            with self.assertRaises(ValueError):
                assess(other)

    def test_reference_digest_binds_input_not_verified_truth(self):
        self.spec["evidence_refs"] = [{"id": "fixture", "digest": "0" * 64, "supports_facet": "effect_metric"}]
        self.assertEqual(assess(self.spec)["references"][0]["state"], "DECLARED_NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main()
