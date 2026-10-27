"""Source-bound value inquiry and explicit arithmetic scenarios, without appraisal."""
from __future__ import annotations

import re
from decimal import Decimal, localcontext

from ..jsonutil import sha256_json

FACETS = ("problem", "beneficiary_role", "artifact", "comparison", "effect_metric",
          "measurement_plan", "reuse", "rights", "funding_route")
ROUTES = {"PILOT_CONTRACT", "RESEARCH_CONTRACT", "LICENSE", "GRANT", "PRIZE", "INVESTMENT", "GIFT", "UNKNOWN"}
QUESTIONS = {
    "problem": "Which concrete problem and current alternative are bound?",
    "beneficiary_role": "Who receives the useful effect and who can authorize a pilot?",
    "artifact": "Which exact usable artifact, version and digest are being assessed?",
    "comparison": "What happens with the same task and oracle without this artifact?",
    "effect_metric": "Which outcome changes, in which unit, population and time window?",
    "measurement_plan": "How will baseline, candidate, costs and adverse effects be measured?",
    "reuse": "Which second task can reuse the result, and what adaptation is needed?",
    "rights": "Which rights are controlled and what is the proposed licensing scope?",
    "funding_route": "Who could fund which concrete next deliverable under which mechanism?",
}


def assess(spec: dict) -> dict:
    if not isinstance(spec, dict) or set(spec) != {"contract", "facets", "evidence_refs", "business_case"} or spec["contract"] != "nova.value-flow-spec.v1":
        raise ValueError("VALUE_SPEC_CONTRACT")
    facets = spec["facets"]
    if not isinstance(facets, dict) or set(facets) != set(FACETS):
        raise ValueError("VALUE_FACETS_CONTRACT")
    for key, value in facets.items():
        if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 4000):
            raise ValueError("VALUE_FACET_TEXT_OR_NULL:" + key)
    if facets["funding_route"] is not None and facets["funding_route"] not in ROUTES:
        raise ValueError("VALUE_FUNDING_ROUTE")
    refs = spec["evidence_refs"]
    if not isinstance(refs, list) or len(refs) > 100:
        raise ValueError("VALUE_REFERENCE_LIMIT")
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"id", "digest", "supports_facet"} or ref["supports_facet"] not in FACETS or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", ref["id"]) or not re.fullmatch(r"[a-f0-9]{64}", ref["digest"]):
            raise ValueError("VALUE_REFERENCE_CONTRACT")
    scenario = None
    case = spec["business_case"]
    if case is not None:
        fields = {"baseline_unit_cost", "candidate_unit_cost", "units", "adoption_fraction", "integration_cost", "ongoing_cost", "currency", "period", "input_basis"}
        if not isinstance(case, dict) or set(case) != fields or case["input_basis"] != "DECLARED_SCENARIO":
            raise ValueError("VALUE_SCENARIO_CONTRACT")
        if not isinstance(case["currency"], str) or not re.fullmatch(r"[A-Z]{3}", case["currency"]):
            raise ValueError("VALUE_CURRENCY_LABEL")
        if not isinstance(case["period"], str) or not 1 <= len(case["period"]) <= 120:
            raise ValueError("VALUE_PERIOD")
        numbers = {}
        for key in fields - {"currency", "period", "input_basis"}:
            value = case[key]
            if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,13}(\.[0-9]{1,6})?", value):
                raise ValueError("VALUE_DECIMAL_STRING:" + key)
            numbers[key] = Decimal(value)
        if numbers["adoption_fraction"] > 1:
            raise ValueError("VALUE_ADOPTION_RANGE")
        with localcontext() as context:
            context.prec = 80  # exceeds the maximum product precision admitted by this input contract
            gross = (numbers["baseline_unit_cost"] - numbers["candidate_unit_cost"]) * numbers["units"] * numbers["adoption_fraction"]
            net = gross - numbers["integration_cost"] - numbers["ongoing_cost"]
        scenario = {"state": "ARITHMETIC_ON_DECLARED_SCENARIO", "currency": case["currency"], "period": case["period"],
                    "gross_saving": format(gross, "f"), "net_saving": format(net, "f"),
                    "formula": "(baseline_unit_cost-candidate_unit_cost)*units*adoption_fraction-integration_cost-ongoing_cost",
                    "meaning": "conditional scenario result; realized benefit, price and financing remain separate"}
    open_facets = [key for key in FACETS if facets[key] is None or facets[key] == "UNKNOWN"]
    return {"contract": "nova.value-flow-assessment.v1", "spec_digest": sha256_json(spec),
            "state": "LOCAL_DRAFT_VALUE_INQUIRY", "facets": facets,
            "references": [{**ref, "state": "DECLARED_NOT_VERIFIED"} for ref in refs],
            "open_questions": [{"facet": key, "question": QUESTIONS[key]} for key in open_facets],
            "next_measurement": QUESTIONS[next((k for k in ("comparison", "effect_metric", "measurement_plan") if k in open_facets), "measurement_plan")],
            "business_case": scenario, "valuation": "OPEN", "price": "OPEN", "funding_decision": "OPEN",
            "creator_status_used_as_multiplier": False, "authority": "NONE"}


def declared_questions(value: dict) -> list[dict]:
    """Read questions from an assessment as declarations; grant no evidence status."""
    if (value.get("contract") != "nova.value-flow-assessment.v1" or
            value.get("state") != "LOCAL_DRAFT_VALUE_INQUIRY" or value.get("authority") != "NONE" or
            not isinstance(value.get("spec_digest"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["spec_digest"])):
        raise ValueError("VALUE_ASSESSMENT_BINDING")
    facets = value.get("facets")
    if not isinstance(facets, dict) or set(facets) != set(FACETS):
        raise ValueError("VALUE_ASSESSMENT_FACETS")
    for key, text in facets.items():
        if text is not None and (not isinstance(text, str) or not text.strip() or len(text) > 4000):
            raise ValueError("VALUE_ASSESSMENT_FACET")
    expected = [{"facet": key, "question": QUESTIONS[key]} for key in FACETS if facets[key] is None or facets[key] == "UNKNOWN"]
    if value.get("open_questions") != expected:
        raise ValueError("VALUE_ASSESSMENT_QUESTIONS")
    return [{"field": "value_" + row["facet"], "referent": "value_spec:" + value["spec_digest"],
             "scope": "declared value inquiry", "definition": "nova.value-facet." + row["facet"] + ".v1",
             "question": row["question"], "resolver": "Provide the missing value " + row["facet"].replace("_", " ") + " with its source and measurement scope.",
             "source_statement_state": "DECLARED_QUESTION_NOT_VERIFIED_BENEFIT"} for row in expected]
