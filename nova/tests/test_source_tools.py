from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from halveth_nova.cli import main
from halveth_nova.engine import NovaEngine
from halveth_nova.network_search import compact_network_result, network_search
from halveth_nova.source_tools import NovaSourceTools, source_tool_definitions
from test_network_search import public_document, public_index


class SourceToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = NovaEngine(self.root)
        self.engine.init("source-tool-test")
        self.source = self.engine.store.ingest_bytes("gg24.txt", b"GG24 exact local evidence")
        self.loader = Mock(return_value=public_index())
        self.tools = NovaSourceTools(self.engine, loader=self.loader)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_search_then_exact_local_read_through_host_dispatch(self):
        before = self.snapshot()
        result = self.tools.dispatch("nova_search_sources", json.dumps({"query":"GG24", "limit":5, "include_historical":False}))
        self.assertEqual(result["state"], "OK")
        hit = next(h for h in result["hits"] if h["source_scope"] == "local_source")
        self.loader.reset_mock()
        detail = self.tools.dispatch("nova_read_source", json.dumps({"identifier":hit["id"], "expected_digest":hit["digest"],
            "include_historical":False, "offset":0, "max_chars":6000}))
        self.assertEqual(detail["state"], "OK")
        self.assertEqual(detail["content"]["text"], "GG24 exact local evidence")
        self.loader.assert_not_called()
        self.assertEqual(before, self.snapshot())

    def test_strict_definitions_are_fresh_and_match_dispatch(self):
        definitions = source_tool_definitions()
        self.assertEqual({d["name"] for d in definitions}, {"nova_search_sources", "nova_read_source"})
        for d in definitions:
            self.assertTrue(d["strict"])
            self.assertFalse(d["parameters"]["additionalProperties"])
            self.assertEqual(set(d["parameters"]["required"]), set(d["parameters"]["properties"]))
        definitions[0]["parameters"]["properties"].clear()
        self.assertTrue(source_tool_definitions()[0]["parameters"]["properties"])

    def test_invalid_or_unknown_calls_do_not_read_sources(self):
        cases = [("exec", '{}'), ([], '{}'), ("nova_search_sources", '[]'),
                 ("nova_search_sources", '{"query":"first","query":"second","limit":5,"include_historical":false}'),
                 ("nova_search_sources", '{"query":"GG24","limit":true,"include_historical":false}'),
                 ("nova_search_sources", '{"query":"GG24","limit":5,"include_historical":false,"workspace":"/tmp"}'),
                 ("nova_search_sources", '{"query":"GG24"}'), ("nova_search_sources", 'x' * 9000)]
        with patch.object(self.engine.store, "sources", side_effect=AssertionError("unexpected IO")):
            for name, args in cases:
                with self.subTest(name=name, args=args[:100]):
                    result = self.tools.dispatch(name, args)
                    self.assertEqual(result["state"], "ERROR")
        self.loader.assert_not_called()

    def test_compact_projection_keeps_identity_order_and_partial_scope_failures(self):
        doc=public_document();doc["summary"]["de"]="GG24 " + "description " * 250
        full=network_search(self.engine, "GG24", loader=lambda:public_index([doc]))
        original=json.dumps(full,sort_keys=True)
        small=compact_network_result(full)
        self.assertEqual([h["id"] for h in small["hits"]], [h["id"] for h in full["hits"]])
        for a,b in zip(full["hits"],small["hits"]):
            for key in ["id","digest","digest_scope","status","source_scope","usable_as_current","score"]:
                self.assertEqual(a[key],b[key])
        self.assertTrue(small["hits"][-1]["excerpt_truncated"])
        self.assertLess(len(json.dumps(small)),len(json.dumps(full)))
        self.assertEqual(original,json.dumps(full,sort_keys=True))
        partial=network_search(self.engine,"GG24",loader=Mock(side_effect=OSError("offline")))
        projected=compact_network_result(partial)
        self.assertEqual(projected["state"],"PARTIAL")
        self.assertEqual(projected["scopes"],partial["scopes"])
        self.assertEqual(len(projected["hits"]),1)

    def test_cli_compact_and_definitions_do_not_initialize_missing_workspace(self):
        missing=self.root/'not-created'
        with patch("halveth_nova.network_search._load_public_index",return_value=public_index()):
            capture=io.StringIO()
            with redirect_stdout(capture):
                code=main(["--workspace",str(missing),"network-search","GG24","--compact"])
            self.assertEqual(code,2)
            result=json.loads(capture.getvalue())
            self.assertEqual(result["contract"],"nova.network-search.compact.v1")
            self.assertEqual(result["state"],"PARTIAL")
        capture=io.StringIO()
        with redirect_stdout(capture):
            code=main(["--workspace",str(missing),"source-tools"])
        self.assertEqual(code,0)
        self.assertEqual(len(json.loads(capture.getvalue())),2)
        self.assertFalse(missing.exists())

    def test_cli_model_inventory_distinguishes_empty_from_unavailable(self):
        for outcome,state in [([],"OK"),(OSError("private endpoint details"),"ERROR")]:
            with patch("halveth_nova.workbench.local_model.available_models",side_effect=outcome if isinstance(outcome,Exception) else None,
                       return_value=[]), patch("halveth_nova.workbench.adapters.capabilities",return_value={}):
                capture=io.StringIO()
                with redirect_stdout(capture):code=main(["--workspace",str(self.root),"capabilities"])
            self.assertEqual(code,0)
            result=json.loads(capture.getvalue())
            self.assertEqual(result["local_models"],[])
            self.assertEqual(result["local_model_inventory"]["state"],state)
            self.assertNotIn("private endpoint details",capture.getvalue())

    def test_cli_exact_read_exit_codes_and_public_read_without_workspace(self):
        identifier = "local:" + self.source["source_id"]
        before = self.snapshot()
        for digest, expected_code, state in [(self.source["digest"], 0, "OK"), ("0" * 64, 2, "CHANGED")]:
            capture = io.StringIO()
            with redirect_stdout(capture):
                code = main(["--workspace", str(self.root), "network-read", identifier,
                             "--expect-digest", digest, "--max-chars", "4"])
            result = json.loads(capture.getvalue())
            self.assertEqual((code, result["state"]), (expected_code, state))
            self.assertEqual("content" in result, state == "OK")
        self.assertEqual(before, self.snapshot())
        hit = next(h for h in network_search(self.engine, "GG24", loader=self.loader)["hits"]
                   if h["source_scope"] == "public_description")
        missing = self.root / "not-created"
        with patch("halveth_nova.network_read._load_public_index", return_value=public_index()):
            capture = io.StringIO()
            with redirect_stdout(capture):
                code = main(["--workspace", str(missing), "network-read", hit["id"],
                             "--expect-digest", hit["digest"]])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(capture.getvalue())["state"], "OK")
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
