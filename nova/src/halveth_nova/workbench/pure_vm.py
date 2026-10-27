"""Restricted JSON function evaluator, separately authorized from source ingestion.

This is a versioned language subset, not a general Python/OS sandbox.
Imports, reflection, attributes except named math calls, IO and arbitrary calls
are absent from the accepted language. The child also has time/memory limits.
"""
from __future__ import annotations

import ast
import json
import math
import os
import sys

CONTRACT = "nova.pure-json-function.v1"
SAFE = {
    "len": len, "sum": sum, "min": min, "max": max, "abs": abs, "round": round,
    "range": range, "enumerate": enumerate, "zip": zip, "sorted": sorted,
    "all": all, "any": any, "set": set, "list": list, "tuple": tuple, "dict": dict,
    "int": int, "float": float, "str": str, "bool": bool, "isinstance": isinstance,
}
MATH = {"sqrt", "floor", "ceil", "log", "log10", "exp", "sin", "cos", "tan", "isfinite", "fabs"}
NODES = {ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign,
         ast.Expr, ast.If, ast.For, ast.While, ast.Break, ast.Continue, ast.Pass, ast.List, ast.Tuple,
         ast.Set, ast.Dict, ast.Name, ast.Load, ast.Store, ast.Constant, ast.BinOp, ast.UnaryOp,
         ast.BoolOp, ast.Compare, ast.Subscript, ast.Slice, ast.Call, ast.keyword, ast.ListComp,
         ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.IfExp, ast.Attribute,
         ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd,
         ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
         ast.In, ast.NotIn, ast.Is, ast.IsNot}


def validate(code: str) -> ast.Module:
    if not isinstance(code, str) or not 0 < len(code.encode("utf-8")) <= 12000:
        raise ValueError("PURE_CODE_SIZE")
    tree = ast.parse(code)
    if not tree.body or len(tree.body) > 8 or not all(isinstance(n, ast.FunctionDef) for n in tree.body):
        raise ValueError("PURE_TOP_LEVEL_FUNCTIONS_ONLY")
    names = {n.name for n in tree.body}
    if "solve" not in names or len(names) != len(tree.body):
        raise ValueError("PURE_SOLVE_REQUIRED")
    solve = next(n for n in tree.body if n.name == "solve")
    if len(solve.args.args) != 1 or solve.args.vararg or solve.args.kwarg or solve.args.kwonlyargs:
        raise ValueError("PURE_SOLVE_ONE_JSON_ARGUMENT")
    for node in ast.walk(tree):
        if type(node) not in NODES:
            raise ValueError("PURE_UNSUPPORTED_AST:" + type(node).__name__)
        if isinstance(node, (ast.Name, ast.arg, ast.FunctionDef)):
            name = node.id if isinstance(node, ast.Name) else node.arg if isinstance(node, ast.arg) else node.name
            if name.startswith("_") or not name.isascii():
                raise ValueError("PURE_NAME_REJECTED")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.returns or node.args.defaults or node.args.kw_defaults):
            raise ValueError("PURE_DECORATORS_ANNOTATIONS_DEFAULTS_REJECTED")
        if isinstance(node, ast.arg) and node.annotation is not None:
            raise ValueError("PURE_ANNOTATION_REJECTED")
        if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "math" and node.attr in MATH):
            raise ValueError("PURE_ATTRIBUTE_REJECTED")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in set(SAFE) | names:
                pass
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "math" and node.func.attr in MATH:
                pass
            else:
                raise ValueError("PURE_CALL_REJECTED")
    return tree


def limits() -> str:
    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
        return "POSIX_CPU_AND_ADDRESS_SPACE"
    import ctypes
    from ctypes import wintypes as w
    class Basic(ctypes.Structure):
        _fields_ = [("processTime", ctypes.c_longlong), ("jobTime", ctypes.c_longlong), ("flags", w.DWORD),
                    ("minWS", ctypes.c_size_t), ("maxWS", ctypes.c_size_t), ("processes", w.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]
    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", IO), ("processMemory", ctypes.c_size_t),
                    ("jobMemory", ctypes.c_size_t), ("peakProcess", ctypes.c_size_t), ("peakJob", ctypes.c_size_t)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.GetCurrentProcess.restype = w.HANDLE
    handle = kernel.CreateJobObjectW(None, None)
    config = Extended(); config.basic.flags = 0x100 | 0x8; config.basic.processes = 1
    config.processMemory = 512 * 1024 * 1024
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(config), ctypes.sizeof(config)) or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise RuntimeError("WINDOWS_JOB_LIMIT_UNAVAILABLE")
    globals()["job_handle"] = handle
    return "WINDOWS_JOB_MEMORY_AND_PROCESS_LIMIT"


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(500001)
        if len(raw) > 500000:
            raise ValueError("PURE_REQUEST_LIMIT")
        value = json.loads(raw.decode("utf-8"))
        tree = validate(value["code"])
        boundary = limits()
        namespace = {"__builtins__": SAFE, "math": math}
        exec(compile(tree, "<nova-generated-pure-function>", "exec"), namespace)
        outcomes = []
        for case in value["cases"]:
            result = namespace["solve"](case["input"])
            encoded = json.dumps(result, allow_nan=False)
            if len(encoded) > 100000:
                raise ValueError("PURE_RESULT_LIMIT")
            # JSON equality is type-sensitive: True does not stand in for 1.
            expected = json.dumps(case["expected"], sort_keys=True, separators=(",", ":"), allow_nan=False)
            actual = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
            outcomes.append({"id": case["id"], "passed": actual == expected, "actual": result})
        print(json.dumps({"contract": CONTRACT, "limits": boundary, "outcomes": outcomes,
                          "passed": all(o["passed"] for o in outcomes)}, allow_nan=False))
        return 0
    except Exception as error:
        print(json.dumps({"contract": CONTRACT, "passed": False, "error": type(error).__name__ + ":" + str(error)[:180]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
