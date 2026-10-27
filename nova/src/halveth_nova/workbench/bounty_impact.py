"""Local bug-bounty impact sharpening without exploit execution or submission."""
from __future__ import annotations

import re

from ..jsonutil import sha256_json

CONTRACT = "nova.bounty-impact-spec.v1"
ASSESSMENT = "nova.bounty-impact-assessment.v1"

SAFE_ENVIRONMENTS = {"OFFLINE_SOURCE", "LOCAL_FIXTURE", "LOCAL_FORK", "AUTHORIZED_TEST_ENV"}
PROOF_STATES = {"NOT_REPRODUCED", "LOCAL_REPRODUCED", "AUTHORIZED_REPRODUCED"}
SCOPE_STATES = {"UNKNOWN", "DECLARED_IN_SCOPE", "CONFIRMED_IN_SCOPE", "OUT_OF_SCOPE"}
SECURITY_PROPERTIES = {
    "UNKNOWN", "CONFIDENTIALITY", "INTEGRITY", "AVAILABILITY", "AUTHORIZATION",
    "CONSENSUS", "ASSET_INTEGRITY", "ACCOUNTING", "OTHER",
}
SEVERITIES = {"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
ROOT_FIELDS = ("invariant", "trust_boundary", "code_path", "faulty_decision", "minimal_fix")
EVIDENCE_FIELDS = {"policy", "scope", "reproduction", "impact", "root_cause", "remediation", "duplicate_check"}
REWARD_KEYS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _text(value, field: str, *, allow_unknown: bool = True, max_len: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_len:
        raise ValueError("BOUNTY_TEXT:" + field)
    value = value.strip()
    if not allow_unknown and value == "UNKNOWN":
        raise ValueError("BOUNTY_UNKNOWN:" + field)
    return value


def _asset_matches(asset: str, authorized: str) -> bool:
    return asset == authorized or asset.startswith(authorized.rstrip("/") + "/")


def _root_signature(root: dict) -> str | None:
    if any(root[key] == "UNKNOWN" for key in ROOT_FIELDS):
        return None
    return sha256_json({key: root[key] for key in ROOT_FIELDS})


def assess(spec: dict, *, verified_evidence: set[str] | None = None) -> dict:
    verified_evidence = set(verified_evidence or ())
    top = {"contract", "program", "finding", "proof", "root_cause", "known_patterns", "evidence_refs"}
    if not isinstance(spec, dict) or set(spec) != top or spec.get("contract") != CONTRACT:
        raise ValueError("BOUNTY_SPEC_CONTRACT")

    program = spec["program"]
    pfields = {"name", "policy_url", "policy_checked_at", "authorized_asset", "reward_ceiling_usd"}
    if not isinstance(program, dict) or set(program) != pfields:
        raise ValueError("BOUNTY_PROGRAM_CONTRACT")
    for key in ("name", "policy_url", "policy_checked_at", "authorized_asset"):
        _text(program[key], "program." + key, allow_unknown=False, max_len=1000)
    rewards = program["reward_ceiling_usd"]
    if not isinstance(rewards, dict) or set(rewards) != REWARD_KEYS:
        raise ValueError("BOUNTY_REWARD_CONTRACT")
    for key, value in rewards.items():
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,12}(\.[0-9]{1,2})?", value)):
            raise ValueError("BOUNTY_REWARD_VALUE:" + key)

    finding = spec["finding"]
    ffields = {"title", "asset", "scope_state", "expected", "observed", "security_property",
               "impact", "action_required", "candidate_severity", "severity_basis"}
    if not isinstance(finding, dict) or set(finding) != ffields:
        raise ValueError("BOUNTY_FINDING_CONTRACT")
    for key in ("title", "asset", "expected", "observed", "impact", "action_required", "severity_basis"):
        _text(finding[key], "finding." + key)
    if finding["scope_state"] not in SCOPE_STATES:
        raise ValueError("BOUNTY_SCOPE_STATE")
    if finding["security_property"] not in SECURITY_PROPERTIES:
        raise ValueError("BOUNTY_SECURITY_PROPERTY")
    if finding["candidate_severity"] not in SEVERITIES:
        raise ValueError("BOUNTY_SEVERITY")

    proof = spec["proof"]
    prfields = {"environment", "state", "runs", "successes", "negative_control", "remediation_control"}
    if not isinstance(proof, dict) or set(proof) != prfields:
        raise ValueError("BOUNTY_PROOF_CONTRACT")
    _text(proof["environment"], "proof.environment", allow_unknown=False, max_len=120)
    if proof["state"] not in PROOF_STATES:
        raise ValueError("BOUNTY_PROOF_STATE")
    if not isinstance(proof["runs"], int) or not 0 <= proof["runs"] <= 1000:
        raise ValueError("BOUNTY_PROOF_RUNS")
    if not isinstance(proof["successes"], int) or not 0 <= proof["successes"] <= proof["runs"]:
        raise ValueError("BOUNTY_PROOF_SUCCESSES")
    for key in ("negative_control", "remediation_control"):
        _text(proof[key], "proof." + key)

    root = spec["root_cause"]
    if not isinstance(root, dict) or set(root) != set(ROOT_FIELDS):
        raise ValueError("BOUNTY_ROOT_CONTRACT")
    for key in ROOT_FIELDS:
        _text(root[key], "root_cause." + key)

    patterns = spec["known_patterns"]
    if not isinstance(patterns, list) or len(patterns) > 500:
        raise ValueError("BOUNTY_PATTERN_LIMIT")
    normalized_patterns = []
    for item in patterns:
        if not isinstance(item, dict) or set(item) != {"id", "root_cause_signature"}:
            raise ValueError("BOUNTY_PATTERN_CONTRACT")
        if not isinstance(item["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", item["id"]):
            raise ValueError("BOUNTY_PATTERN_ID")
        if not isinstance(item["root_cause_signature"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["root_cause_signature"]):
            raise ValueError("BOUNTY_PATTERN_SIGNATURE")
        normalized_patterns.append(dict(item))

    refs = spec["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 200:
        raise ValueError("BOUNTY_REFERENCE_LIMIT")
    normalized_refs = []
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"id", "digest", "supports"}:
            raise ValueError("BOUNTY_REFERENCE_CONTRACT")
        if not isinstance(ref["id"], str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", ref["id"]):
            raise ValueError("BOUNTY_REFERENCE_ID")
        if not isinstance(ref["digest"], str) or not re.fullmatch(r"[a-f0-9]{64}", ref["digest"]):
            raise ValueError("BOUNTY_REFERENCE_DIGEST")
        if ref["supports"] not in EVIDENCE_FIELDS:
            raise ValueError("BOUNTY_REFERENCE_SUPPORTS")
        normalized_refs.append({**ref, "state": "BOUND_TO_NOVA_SOURCE" if ref["id"] in verified_evidence else "DECLARED_NOT_VERIFIED"})

    root_sig = _root_signature(root)
    exact_matches = [row["id"] for row in normalized_patterns if root_sig and row["root_cause_signature"] == root_sig]

    scope_bound = (
        finding["scope_state"] == "CONFIRMED_IN_SCOPE"
        and _asset_matches(finding["asset"], program["authorized_asset"])
    )
    safe_environment = proof["environment"] in SAFE_ENVIRONMENTS
    reproduced = proof["state"] != "NOT_REPRODUCED" and proof["runs"] >= 2 and proof["successes"] >= 2
    negative_control = proof["negative_control"] != "UNKNOWN"
    impact_bound = (
        finding["security_property"] != "UNKNOWN"
        and finding["impact"] != "UNKNOWN"
        and finding["action_required"] != "UNKNOWN"
    )
    root_bound = root_sig is not None
    remediation_control = proof["remediation_control"] != "UNKNOWN"
    supports = {row["supports"] for row in normalized_refs if row["state"] == "BOUND_TO_NOVA_SOURCE"}
    evidence_bound = {"policy", "scope", "reproduction", "impact", "root_cause"}.issubset(supports)

    gates = {
        "scope_bound": scope_bound,
        "safe_environment": safe_environment,
        "reproduced": reproduced,
        "negative_control": negative_control,
        "impact_bound": impact_bound,
        "root_cause_bound": root_bound,
        "remediation_control": remediation_control,
        "evidence_bound": evidence_bound,
    }

    blockers = [key for key, ok in gates.items() if not ok]
    if not safe_environment:
        stage = "UNSAFE_PROOF_HOLD"
    elif not scope_bound:
        stage = "SCOPE_HOLD"
    elif not reproduced:
        stage = "FLAG_ONLY"
    elif not negative_control or not impact_bound:
        stage = "REPRODUCED_SIGNAL"
    elif not root_bound:
        stage = "IMPACT_CANDIDATE"
    elif exact_matches:
        stage = "DUPLICATE_CANDIDATE"
    elif not remediation_control or not evidence_bound:
        stage = "ROOT_CAUSE_CANDIDATE"
    else:
        stage = "REPORT_CANDIDATE"

    if exact_matches:
        duplicate_risk = "HIGH_OWN_CORPUS_MATCH"
    elif root_bound and normalized_patterns:
        duplicate_risk = "LOWER_OWN_CORPUS_ONLY_NOT_ZERO"
    else:
        duplicate_risk = "UNKNOWN"

    if not impact_bound:
        informative_risk = "HIGH"
    elif not root_bound or not remediation_control:
        informative_risk = "MEDIUM"
    else:
        informative_risk = "LOWER_NOT_ZERO"

    reward_context = None
    sev = finding["candidate_severity"]
    if sev != "UNKNOWN" and finding["severity_basis"] != "UNKNOWN":
        reward_context = {
            "candidate_severity": sev,
            "severity_basis": finding["severity_basis"],
            "program_ceiling_usd": rewards[sev],
            "state": "PROGRAM_CONTEXT_NOT_PAYOUT_PREDICTION",
        }

    return {
        "contract": ASSESSMENT,
        "spec_digest": sha256_json(spec),
        "state": stage,
        "gates": gates,
        "blockers": blockers,
        "root_cause_signature": root_sig,
        "exact_known_pattern_matches": exact_matches,
        "duplicate_risk": duplicate_risk,
        "duplicate_visibility": "DECLARED_OWN_CORPUS_ONLY",
        "informative_risk": informative_risk,
        "submission_state": "READY_FOR_HUMAN_REVIEW" if stage == "REPORT_CANDIDATE" else "HOLD",
        "reward_context": reward_context,
        "references": normalized_refs,
        "meaning": (
            "Local evidence/readiness assessment only. It does not execute an exploit, authorize testing, "
            "submit a report, prove uniqueness against private program reports, assign final severity or predict payout."
        ),
    }
