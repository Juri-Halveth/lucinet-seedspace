import unittest

from halveth_nova.workbench.bounty_impact import assess


def base_spec():
    return {
        "contract": "nova.bounty-impact-spec.v1",
        "program": {
            "name": "Synthetic Program",
            "policy_url": "https://example.invalid/policy",
            "policy_checked_at": "2026-10-27",
            "authorized_asset": "https://example.invalid/source",
            "reward_ceiling_usd": {"LOW": "100", "MEDIUM": "1000", "HIGH": "5000", "CRITICAL": "10000"},
        },
        "finding": {
            "title": "Synthetic state mismatch crosses a declared trust boundary",
            "asset": "https://example.invalid/source/module",
            "scope_state": "CONFIRMED_IN_SCOPE",
            "expected": "Mismatched state is rejected.",
            "observed": "Synthetic fixture accepts mismatched state.",
            "security_property": "INTEGRITY",
            "impact": "A protected synthetic state can be accepted under the wrong digest.",
            "action_required": "Change the validation decision and add a regression test.",
            "candidate_severity": "UNKNOWN",
            "severity_basis": "UNKNOWN",
        },
        "proof": {
            "environment": "LOCAL_FIXTURE",
            "state": "LOCAL_REPRODUCED",
            "runs": 2,
            "successes": 2,
            "negative_control": "Matched state remains accepted.",
            "remediation_control": "Patched synthetic fixture rejects the mismatch.",
        },
        "root_cause": {
            "invariant": "Referenced digest must bind the accepted state.",
            "trust_boundary": "Untrusted state input to validation decision.",
            "code_path": "synthetic/StateGate.py",
            "faulty_decision": "Decision trusts locator while omitting digest equality.",
            "minimal_fix": "Require digest equality before accepting the state.",
        },
        "known_patterns": [],
        "evidence_refs": [
            {"id": "policy", "digest": "0" * 64, "supports": "policy"},
            {"id": "scope", "digest": "1" * 64, "supports": "scope"},
            {"id": "repro", "digest": "2" * 64, "supports": "reproduction"},
            {"id": "impact", "digest": "3" * 64, "supports": "impact"},
            {"id": "root", "digest": "4" * 64, "supports": "root_cause"},
        ],
    }


class BountyImpactTests(unittest.TestCase):
    def verified_ids(self, spec):
        return {row["id"] for row in spec["evidence_refs"]}

    def test_declared_evidence_alone_does_not_reach_report_candidate(self):
        result = assess(base_spec())
        self.assertEqual(result["state"], "ROOT_CAUSE_CANDIDATE")
        self.assertFalse(result["gates"]["evidence_bound"])

    def test_complete_local_case_reaches_human_review(self):
        spec = base_spec()
        result = assess(spec, verified_evidence=self.verified_ids(spec))
        self.assertEqual(result["state"], "REPORT_CANDIDATE")
        self.assertEqual(result["submission_state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(result["informative_risk"], "LOWER_NOT_ZERO")

    def test_flag_without_reproduction_stays_flag_only(self):
        spec = base_spec()
        spec["proof"].update({"state": "NOT_REPRODUCED", "runs": 0, "successes": 0})
        self.assertEqual(assess(spec, verified_evidence=self.verified_ids(spec))["state"], "FLAG_ONLY")

    def test_missing_impact_is_not_promoted(self):
        spec = base_spec()
        spec["finding"]["impact"] = "UNKNOWN"
        result = assess(spec, verified_evidence=self.verified_ids(spec))
        self.assertEqual(result["state"], "REPRODUCED_SIGNAL")
        self.assertEqual(result["informative_risk"], "HIGH")

    def test_live_production_environment_is_held(self):
        spec = base_spec()
        spec["proof"]["environment"] = "LIVE_PRODUCTION"
        result = assess(spec, verified_evidence=self.verified_ids(spec))
        self.assertEqual(result["state"], "UNSAFE_PROOF_HOLD")
        self.assertFalse(result["gates"]["safe_environment"])

    def test_exact_root_cause_match_is_duplicate_candidate(self):
        base = base_spec()
        first = assess(base, verified_evidence=self.verified_ids(base))
        spec = base_spec()
        spec["known_patterns"] = [{"id": "prior-1", "root_cause_signature": first["root_cause_signature"]}]
        result = assess(spec, verified_evidence=self.verified_ids(spec))
        self.assertEqual(result["state"], "DUPLICATE_CANDIDATE")
        self.assertEqual(result["exact_known_pattern_matches"], ["prior-1"])

    def test_different_root_is_not_called_unique_against_private_reports(self):
        base = base_spec()
        first = assess(base, verified_evidence=self.verified_ids(base))
        spec = base_spec()
        spec["root_cause"]["faulty_decision"] = "Different synthetic decision."
        spec["known_patterns"] = [{"id": "prior-1", "root_cause_signature": first["root_cause_signature"]}]
        result = assess(spec, verified_evidence=self.verified_ids(spec))
        self.assertEqual(result["state"], "REPORT_CANDIDATE")
        self.assertEqual(result["duplicate_risk"], "LOWER_OWN_CORPUS_ONLY_NOT_ZERO")

    def test_reward_context_needs_severity_basis(self):
        spec = base_spec()
        spec["finding"]["candidate_severity"] = "HIGH"
        self.assertIsNone(assess(spec, verified_evidence=self.verified_ids(spec))["reward_context"])
        spec["finding"]["severity_basis"] = "Declared CVSS vector from separate assessment"
        reward = assess(spec, verified_evidence=self.verified_ids(spec))["reward_context"]
        self.assertEqual(reward["program_ceiling_usd"], "5000")
        self.assertEqual(reward["state"], "PROGRAM_CONTEXT_NOT_PAYOUT_PREDICTION")


if __name__ == "__main__":
    unittest.main()
