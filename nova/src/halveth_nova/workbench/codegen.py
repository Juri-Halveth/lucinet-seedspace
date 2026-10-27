"""Generate a pure JSON function against previously bound, withheld test cases."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from ..jsonutil import canonical_json, sha256_bytes, sha256_json, strict_loads
from .local_model import BASE, local_profile, record
from .pure_vm import validate, SAFE, MATH


def evaluate(code: str, cases: list[dict], *, timeout: int = 5) -> dict:
    validate(code)
    if not 1 <= len(cases) <= 32:
        raise ValueError("PURE_TEST_COUNT")
    raw = canonical_json({"code": code, "cases": cases}).encode("utf-8")
    if len(raw) > 500000:
        raise ValueError("PURE_REQUEST_LIMIT")
    env = {k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ}
    try:
        process = subprocess.run([sys.executable, "-I", "-S", str(Path(__file__).with_name("pure_vm.py"))],
                                 input=raw, capture_output=True, timeout=timeout, env=env, shell=False)
    except subprocess.TimeoutExpired:
        return {"contract": "nova.pure-json-function.v1", "passed": False, "error": "TIME_LIMIT"}
    if len(process.stdout) > 2000000:
        raise ValueError("PURE_RESPONSE_LIMIT")
    if not process.stdout:
        return {"contract": "nova.pure-json-function.v1", "passed": False, "error": "CHILD_RESOURCE_OR_EXECUTION_STOP", "exit_code": process.returncode}
    return strict_loads(process.stdout.decode("utf-8"))


def build_function(target: Path, spec: dict, *, model: str, max_attempts: int = 3) -> dict:
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 3:
        raise ValueError("CODEGEN_ATTEMPT_LIMIT")
    if not isinstance(spec, dict) or set(spec) != {"contract", "description", "cases"} or spec["contract"] != "nova.pure-build-spec.v1":
        raise ValueError("PURE_BUILD_SPEC_CONTRACT")
    if not isinstance(spec["description"], str) or not 1 <= len(spec["description"]) <= 4000:
        raise ValueError("PURE_BUILD_DESCRIPTION")
    if not isinstance(spec["cases"], list) or not 1 <= len(spec["cases"]) <= 32:
        raise ValueError("PURE_TEST_COUNT")
    ids = set()
    for case in spec["cases"]:
        if not isinstance(case, dict) or set(case) != {"id", "input", "expected"} or not isinstance(case["id"], str) or case["id"] in ids:
            raise ValueError("PURE_TEST_CONTRACT")
        ids.add(case["id"])
    spec_digest = sha256_json(spec)  # Bound before generating; tests are withheld from the model.
    profile = local_profile(model)
    system = ("Implement the requested pure JSON-to-JSON function. Return one JSON object with a code string. "
              "After JSON decoding, the code must be valid Python with real line breaks and ordinary quotes. "
              "Top level must contain only function definitions, including def solve(data). Never call solve at module level. "
              "No imports, classes, decorators, annotations, default arguments, IO, reflection, underscore-prefixed names, "
              "attribute/method calls, or string formatting. Use loops, comprehensions, indexing, conditionals and pure expressions. "
              "Use set/list/dict comprehensions to collect values; object.add, object.append and object.get are forbidden. "
              "For example, distinct values can be formed with {item for item in data}. "
              "You may define helper functions. Allowed builtins: " + ", ".join(sorted(SAFE)) +
              ". Named math calls allowed: " + ", ".join("math." + name for name in sorted(MATH)) + ".")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    target.mkdir(parents=True, exist_ok=False)
    (target / "SPEC.json").write_bytes((canonical_json(spec) + "\n").encode("utf-8"))
    messages = [{"role": "system", "content": system}, {"role": "user", "content": spec["description"]}]
    attempts, selected_code = [], None
    for number in range(1, max_attempts + 1):
        body = {"model": model, "stream": False,
                "format": record({"code": {"type": "string", "minLength": 1, "maxLength": 12000}}),
                "options": {"temperature": 0, "num_predict": 2000}, "messages": messages}
        request_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(BASE + "/api/chat", data=request_bytes, headers={"Content-Type": "application/json"})
        attempt = {"number": number, "request_digest": sha256_bytes(request_bytes), "response_digest": None,
                   "source_digest": None, "model_saw_test_cases": False}
        feedback = "The candidate did not pass the previously bound tests. Re-read the description and correct the algorithm."
        code, raw = None, b""
        try:
            with opener.open(req, timeout=120) as response:
                raw = response.read(1000001)
            if len(raw) > 1000000:
                raise ValueError("CODEGEN_RESPONSE_LIMIT")
            attempt["response_digest"] = sha256_bytes(raw)
            (target / ("attempt-%02d-response.json" % number)).write_bytes(raw)
            envelope = strict_loads(raw.decode("utf-8"))
            value = strict_loads(envelope["message"]["content"])
            if not isinstance(value, dict) or set(value) != {"code"} or not isinstance(value["code"], str):
                raise ValueError("CODEGEN_OUTPUT_CONTRACT")
            code = value["code"]
            code_bytes = code.encode("utf-8")
            attempt["source_digest"] = sha256_bytes(code_bytes)
            attempt["source_file"] = "attempt-%02d.py" % number
            (target / attempt["source_file"]).write_bytes(code_bytes)
            selected_code = code
            outcome = evaluate(code, spec["cases"])
        except (ValueError, SyntaxError, KeyError, OSError, RuntimeError) as error:
            outcome = {"passed": False, "error": type(error).__name__ + ":" + str(error)[:200]}
            # No inputs, expected results or test outputs enter repair prompts.
            feedback = "The candidate failed syntax/language/response validation: " + type(error).__name__
            if isinstance(error, SyntaxError):
                feedback += ": " + error.msg
            elif isinstance(error, ValueError):
                kind = str(error).split(":", 1)[0]
                feedback += ": " + kind[:80]
                if kind in {"PURE_CALL_REJECTED", "PURE_ATTRIBUTE_REJECTED"}:
                    feedback += ". Remove object methods, including set.add, list.append and dict.get. Use comprehensions and indexing"
                if kind == "PURE_TOP_LEVEL_FUNCTIONS_ONLY":
                    feedback += ". Remove module-level calls and assignments; only function definitions may be at top level"
            feedback += ". Generate a corrected complete function. Do not double-escape Python line breaks."
        attempt["outcome"] = outcome
        attempts.append(attempt)
        if outcome.get("passed"):
            break
        if code is not None:
            messages.append({"role": "assistant", "content": json.dumps({"code": code})})
        messages.append({"role": "user", "content": feedback})
    if selected_code is not None:
        (target / "candidate.py").write_bytes(selected_code.encode("utf-8"))
    final = attempts[-1]
    receipt = {"contract": "nova.generated-function-build.v1", "model": model, "spec_digest": spec_digest,
               "description": spec["description"], "model_profile": profile, "attempts": attempts,
               "attempt_budget": max_attempts, "model_saw_test_cases": False,
               "request_digest": final["request_digest"], "response_digest": final["response_digest"],
               "source_digest": sha256_bytes(selected_code.encode("utf-8")) if selected_code is not None else None,
               "language_contract": "nova.pure-json-function.v1", "outcome": outcome,
               "state": "TESTED_CANDIDATE" if outcome.get("passed") else "HELD_FAILED_CANDIDATE",
               "deployment": "NONE", "source_corpus_execution": "NONE",
               "generated_code_execution": "RESTRICTED_LOCAL_JSON_FUNCTION_EVALUATOR"}
    (target / "BUILD_RECEIPT.json").write_bytes((canonical_json(receipt) + "\n").encode("utf-8"))
    return receipt
