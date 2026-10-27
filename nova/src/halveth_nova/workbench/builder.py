"""A real, finite builder: portable graph-analysis program, compile and self-check.

Only this trusted template is executed. Ingested or model-generated code is data.
Other requested builds remain explicit executor requests rather than false success.
"""
from __future__ import annotations

import compileall
import copy
import json
import subprocess
import sys
from pathlib import Path

from ..jsonutil import canonical_json, sha256_bytes
from . import graph
from .view import render

RUNNER = '''"""Portable NOVA analysis kit. No source code from the corpus is executed."""
import argparse, json
from pathlib import Path
from halveth_nova.workbench.graph import structural_match

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--self-check', action='store_true')
    p.add_argument('--pattern')
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    data = json.loads((root / 'analysis.json').read_text(encoding='utf-8'))
    graphs = data['graphs']
    if args.self_check:
        assert data['contract'] == 'nova.workbench-result.v1'
        for row in graphs:
            g = row['graph']
            if len(g['nodes']) <= 8:
                assert structural_match(g, g)['mappings']
        print(json.dumps({'self_check':'PASS','graphs':len(graphs)}))
    elif args.pattern:
        pattern = json.loads(Path(args.pattern).read_text(encoding='utf-8'))
        print(json.dumps([{'source_id':r['source_id'], **structural_match(pattern,r['graph'])} for r in graphs]))
    else:
        print(json.dumps({'task':data['task'], 'graphs':len(graphs), 'unknowns':len(data['unknowns'])},ensure_ascii=False))
if __name__ == '__main__':
    main()
'''


def build_kit(target: Path, result: dict, pattern: dict | None) -> dict:
    if target.exists():
        raise FileExistsError("BUILD_TARGET_EXISTS")
    target.mkdir(parents=True)
    package = target / "halveth_nova" / "workbench"
    package.mkdir(parents=True)
    (target / "halveth_nova" / "__init__.py").write_bytes(b"")
    (package / "__init__.py").write_bytes(b"")
    (package / "graph.py").write_bytes(Path(graph.__file__).read_bytes())
    (target / "halveth_nova" / "jsonutil.py").write_bytes((Path(graph.__file__).parent.parent / "jsonutil.py").read_bytes())
    (target / "runner.py").write_bytes(RUNNER.encode("utf-8"))
    (target / "analysis.json").write_bytes((canonical_json(result) + "\n").encode("utf-8"))
    (target / "index.html").write_bytes(render(result).encode("utf-8"))
    if pattern is not None:
        (target / "pattern.json").write_bytes((canonical_json(pattern) + "\n").encode("utf-8"))
    compiled = compileall.compile_dir(target, quiet=2)
    if not compiled:
        raise RuntimeError("GENERATED_KIT_COMPILE_FAILED")
    # -I removes the ambient Python path. Add only the just-generated kit.
    # Fixed code and argv; source/model text is never interpolated into code.
    bootstrap = "import runpy,sys;p=sys.argv[1];sys.path.insert(0,p);sys.argv=['runner.py','--self-check'];runpy.run_path(p+'/runner.py',run_name='__main__')"
    process = subprocess.run([sys.executable, "-I", "-c", bootstrap, str(target)], cwd=target,
                             capture_output=True, timeout=20, shell=False)
    if process.returncode:
        raise RuntimeError("GENERATED_KIT_SELF_CHECK_FAILED")
    check = json.loads(process.stdout.decode("utf-8"))
    (target / "index.html").write_bytes(render({**result, "build": {"compile": "PASS", "execution": check}}).encode("utf-8"))
    files = [{"path": p.relative_to(target).as_posix(), "sha256": sha256_bytes(p.read_bytes()), "bytes": p.stat().st_size}
             for p in sorted(target.rglob("*")) if p.is_file() and "__pycache__" not in p.parts]
    manifest = {"contract": "nova.build-kit.v1", "recipe": "portable-graph-analysis-program-v1",
                "files": files, "compile": "PASS", "execution": check, "source_execution": "NONE",
                "scope": "generated trusted analysis program; not arbitrary application implementation"}
    (target / "BUILD_MANIFEST.json").write_bytes((canonical_json(manifest) + "\n").encode("utf-8"))
    return {**manifest, "directory": str(target), "viewer": str(target / "index.html")}


def finalize_kit(target: Path, result: dict) -> dict:
    """Refresh the viewer after generation. Do not embed its own content hash."""
    display = copy.deepcopy(result)
    display["build"].pop("files", None)
    display["artifacts"] = []
    (target / "index.html").write_bytes(render(display).encode("utf-8"))
    files = [{"path": p.relative_to(target).as_posix(), "sha256": sha256_bytes(p.read_bytes()),
              "bytes": p.stat().st_size} for p in sorted(target.rglob("*"))
             if p.is_file() and "__pycache__" not in p.parts and p.name != "BUILD_MANIFEST.json"]
    manifest = {**result["build"], "files": files}
    manifest.pop("directory", None); manifest.pop("viewer", None)
    manifest_bytes = (canonical_json(manifest) + "\n").encode("utf-8")
    (target / "BUILD_MANIFEST.json").write_bytes(manifest_bytes)
    return {**result["build"], "files": files,
            "manifest": {"path": "BUILD_MANIFEST.json", "sha256": sha256_bytes(manifest_bytes),
                         "bytes": len(manifest_bytes)}}
