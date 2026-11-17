from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from email.message import Message
from http.client import HTTPResponse
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from halveth_nova.cli import main
from halveth_nova.engine import NovaEngine
from halveth_nova.network_search import (
    MAX_INDEX_BYTES, MAX_LOCAL_SOURCE_BYTES, PUBLIC_INDEX_URL, TIMEOUT_SECONDS, _NoRedirect, network_search,
)


def public_document(identifier="gg24", historical=False):
    return {"id": "fixture:" + identifier, "title": {"de": "GG24 Förder-Zeitspur"},
            "summary": {"de": "Öffentliche GG24-Beschreibung als synthetisches Testfixture."},
            "text": "GG24 Förderung und öffentliche Quellen", "aliases": ["Gitcoin"],
            "url": "https://juri-halveth.github.io/console-only/?spur=gg24",
            "historical": historical, "editorialState": "ARCHIVE" if historical else "CURRENT",
            "source": {"url": "https://github.com/Juri-Halveth/console-only/blob/" + "b" * 40 + "/README.md",
                       "revision": "b" * 40, "observedAt": "2026-11-17T20:00:00Z",
                       "scope": "TEST_PUBLIC_DESCRIPTION"}}


def public_index(documents=None):
    return json.dumps({"schema": "halveth.network-search.v1", "revision": "a" * 64,
                       "observedAt": "2026-11-17T21:00:00Z",
                       "documents": documents if documents is not None else [public_document()]}).encode()


class NetworkSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = NovaEngine(self.root)
        self.engine.init("synthetic-network-test")
        self.old = self.engine.store.ingest_bytes("old.txt", b"GG24 inventory: 18 entries")
        self.receipt = self.engine.run("GG24")
        self.engine.store.set_status(self.old["source_id"], "historical", note="dated snapshot")
        self.current = self.engine.store.ingest_bytes("current.txt", b"GG24 inventory: 21 entries")

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_one_query_combines_current_local_and_public_without_mutating_workspace(self):
        before = self.snapshot()
        raw = public_index([public_document(), public_document("old-public", historical=True)])
        loader = Mock(return_value=raw)
        result = network_search(self.engine, "GG24", loader=loader)
        loader.assert_called_once_with()
        self.assertEqual(result["state"], "OK")
        self.assertEqual({hit["source_scope"] for hit in result["hits"]}, {"local_source", "public_description"})
        self.assertEqual(len(result["hits"]), 2)
        local = next(hit for hit in result["hits"] if hit["source_scope"] == "local_source")
        self.assertEqual(local["source_id"], self.current["source_id"])
        self.assertIn("21 entries", local["excerpt"])
        self.assertEqual(local["digest"], hashlib.sha256(b"GG24 inventory: 21 entries").hexdigest())
        self.assertEqual(result["scopes"]["public_description"]["index_sha256"], hashlib.sha256(raw).hexdigest())
        historical = network_search(self.engine, "GG24", include_historical=True, loader=lambda: raw)
        self.assertEqual(len(historical["hits"]), 4)
        old = next(hit for hit in historical["hits"] if hit.get("source_id") == self.old["source_id"])
        self.assertFalse(old["usable_as_current"])
        self.assertEqual(old["status"], "historical")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.engine.store.ledger()[0], self.receipt)

    def test_no_hits_is_distinct_from_an_unavailable_scope(self):
        result = network_search(self.engine, "nirgendwo987xyz", loader=public_index)
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["hits"], [])
        self.assertTrue(all(scope["state"] == "OK" for scope in result["scopes"].values()))
        unavailable = network_search(self.engine, "GG24", loader=Mock(side_effect=URLError("offline")))
        self.assertEqual(unavailable["state"], "PARTIAL")
        self.assertEqual(unavailable["scopes"]["public_description"]["state"], "ERROR")
        self.assertEqual([hit["source_scope"] for hit in unavailable["hits"]], ["local_source"])

    def test_per_scope_limit_reports_truncation(self):
        self.engine.store.ingest_bytes("another.txt", b"GG24 another current inventory")
        result = network_search(self.engine, "GG24", limit=1,
                                loader=lambda: public_index([public_document(), public_document("another")]))
        self.assertEqual(len(result["hits"]), 2)
        self.assertTrue(all(scope["truncated"] for scope in result["scopes"].values()))

    def test_public_schema_size_duplicates_and_visibility_fail_closed(self):
        invalid = copy.deepcopy(public_document()); invalid["visibility"] = "private"
        malformed = copy.deepcopy(public_document()); malformed["source"]["url"] = "file:///local"
        undated = copy.deepcopy(public_document()); undated["source"]["observedAt"] = "tomorrow"
        for raw in [b"{}", b"x" * (MAX_INDEX_BYTES + 1), public_index([invalid]),
                    public_index([malformed]), public_index([undated]), public_index([public_document(), public_document()])]:
            with self.subTest(length=len(raw)):
                result = network_search(self.engine, "GG24", loader=lambda: raw)
                self.assertEqual(result["state"], "PARTIAL")
                self.assertEqual(result["scopes"]["public_description"]["state"], "ERROR")
                self.assertFalse(any(hit["source_scope"] == "public_description" for hit in result["hits"]))

    def test_changed_local_bytes_fail_that_scope_without_suppressing_public_hits(self):
        (self.engine.store.objects / self.current["digest"]).write_bytes(b"GG24 changed bytes")
        result = network_search(self.engine, "GG24", loader=public_index)
        self.assertEqual(result["state"], "PARTIAL")
        self.assertEqual(result["scopes"]["local_source"]["error"], "LOCAL_SOURCE_BYTES_CHANGED")
        self.assertEqual([hit["source_scope"] for hit in result["hits"]], ["public_description"])

    def test_local_size_limit_rejects_before_unbounded_core_search(self):
        with (self.engine.store.objects / self.current["digest"]).open("ab") as stream:
            stream.truncate(MAX_LOCAL_SOURCE_BYTES + 1)
        with patch.object(self.engine, "search", wraps=self.engine.search) as search:
            result = network_search(self.engine, "GG24", loader=public_index)
        search.assert_not_called()
        self.assertEqual(result["state"], "PARTIAL")
        self.assertEqual(result["scopes"]["local_source"]["error"], "LOCAL_SOURCE_MISSING_OR_TOO_LARGE")

    def test_transport_gets_only_fixed_index_without_query_auth_or_body(self):
        raw = public_index()
        response = Mock()
        response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False)
        response.geturl.return_value = PUBLIC_INDEX_URL; response.status = 200
        response.headers = Message(); response.headers["Content-Type"] = "application/json"
        response.read.return_value = raw
        opener = Mock(); opener.open.return_value = response
        secret_query = "nur-lokaler-suchtext-987xyz"
        with patch("halveth_nova.network_search.build_opener", return_value=opener):
            result = network_search(self.engine, secret_query)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, PUBLIC_INDEX_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertNotIn(secret_query, repr(request.header_items()))
        self.assertIsNone(request.get_header("Authorization")); self.assertIsNone(request.get_header("Cookie"))
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": TIMEOUT_SECONDS})
        response.read.assert_called_once_with(MAX_INDEX_BYTES + 1)
        self.assertEqual(result["state"], "OK")
        with self.assertRaisesRegex(ValueError, "PUBLIC_REDIRECT_REJECTED"):
            _NoRedirect().redirect_request(request, None, 302, "redirect", {}, "https://elsewhere.invalid/")

    def test_cli_returns_partial_json_and_nonzero_exit_for_remote_http_error(self):
        output = io.StringIO()
        with patch("halveth_nova.network_search._load_public_index",
                   side_effect=HTTPError(PUBLIC_INDEX_URL, 404, "missing", {}, None)), redirect_stdout(output):
            code = main(["--workspace", str(self.root), "network-search", "GG24"])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["state"], "PARTIAL")
        self.assertEqual(result["scopes"]["public_description"]["error"], "PUBLIC_HTTP_404")

    def test_truncated_chunked_response_preserves_local_hits_in_partial_cli_result(self):
        from contextlib import redirect_stderr

        before = self.snapshot()
        socket = Mock()
        socket.makefile.return_value = io.BytesIO(
            b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n5\r\nabc")
        response = HTTPResponse(socket)
        response.begin()
        response.url = PUBLIC_INDEX_URL
        opener = Mock(); opener.open.return_value = response
        output, errors = io.StringIO(), io.StringIO()
        with patch("halveth_nova.network_search.build_opener", return_value=opener), \
                redirect_stdout(output), redirect_stderr(errors):
            code = main(["--workspace", str(self.root), "network-search", "GG24"])
        self.assertEqual(code, 2)
        self.assertEqual(errors.getvalue(), "")
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "PARTIAL")
        self.assertEqual(result["scopes"]["public_description"]["error"], "IncompleteRead")
        self.assertEqual(result["scopes"]["local_source"]["state"], "OK")
        self.assertEqual([hit["source_id"] for hit in result["hits"]], [self.current["source_id"]])
        self.assertEqual(self.snapshot(), before)

    def test_invalid_query_and_limit_make_no_request(self):
        loader = Mock(return_value=public_index())
        for query, limit in [(" ", 20), ("x" * 513, 20), ("GG24", 0), ("GG24", 101)]:
            with self.assertRaises(ValueError):
                network_search(self.engine, query, limit=limit, loader=loader)
        with self.assertRaises(ValueError):
            network_search(self.engine, "GG24", include_historical="yes", loader=loader)
        loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
