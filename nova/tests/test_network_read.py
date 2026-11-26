from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from halveth_nova.engine import NovaEngine
from halveth_nova.network_read import network_read
from halveth_nova.network_search import MAX_LOCAL_SOURCE_BYTES, compact_network_result, network_search
from test_network_search import public_document, public_index


class NetworkReadTests(unittest.TestCase):
    """Contracts at the search-to-read boundary; no model or live network needed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = NovaEngine(self.root)
        self.engine.init("synthetic-network-read-test")
        self.local_text = "GG24 Quelle: Grüße 🌊 — две строки\nZweite Zeile.\n"
        self.local = self.engine.store.ingest_bytes("source.txt", self.local_text.encode("utf-8"))

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file()}

    def public_hit(self, doc=None):
        doc = public_document() if doc is None else doc
        raw = public_index([doc])
        found = network_search(self.engine, "GG24", include_historical=True, loader=lambda: raw)
        hit = next(h for h in found["hits"] if h["source_scope"] == "public_description")
        return hit, raw

    def local_read(self, source=None, **kwargs):
        source = self.local if source is None else source
        return network_read(self.engine, "local:" + source["source_id"], source["digest"], **kwargs)

    def assert_no_content(self, result):
        self.assertTrue("content" not in result or result["content"] is None, result)

    def assert_rejected(self, result, state, error):
        self.assertEqual(result["contract"], "nova.network-read.v1")
        self.assertEqual(result["state"], state)
        self.assertEqual(result["error"], error)
        self.assert_no_content(result)

    def test_exact_public_search_hit_reads_bound_description(self):
        doc = public_document()
        doc["text"] = "GG24 — genauer öffentlicher Beschreibungstext 🌱"
        hit, raw = self.public_hit(doc)
        loader = Mock(return_value=raw)
        result = network_read(self.engine, hit["id"], hit["digest"], loader=loader)
        loader.assert_called_once_with()
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["contract"], "nova.network-read.v1")
        self.assertEqual(result["id"], hit["id"])
        self.assertEqual(result["digest"], hit["digest"])
        self.assertEqual(result["source_scope"], "public_description")
        self.assertTrue(result["usable_as_current"])
        self.assertEqual(result["content"]["text"], doc["text"])
        self.assertEqual(result["content"]["total_chars"], len(doc["text"]))
        self.assertFalse(result["content"]["has_more"])

    def test_exact_local_search_hit_returns_original_utf8_bytes_as_text(self):
        found = network_search(self.engine, "GG24", loader=public_index)
        hit = next(h for h in found["hits"] if h["source_scope"] == "local_source")
        loader = Mock(side_effect=AssertionError("a local read must never load a public index"))
        result = network_read(self.engine, hit["id"], hit["digest"], loader=loader)
        self.assertEqual(result["state"], "OK")
        self.assertEqual(result["source_scope"], "local_source")
        self.assertEqual(result["content"]["text"].encode("utf-8"), self.local_text.encode("utf-8"))
        self.assertEqual(result["digest"], hashlib.sha256(self.local_text.encode("utf-8")).hexdigest())
        loader.assert_not_called()

    def test_public_read_does_not_require_an_initialized_workspace(self):
        hit, raw = self.public_hit()
        missing = self.root / "never-created-workspace"
        result = network_read(NovaEngine(missing), hit["id"], hit["digest"], loader=lambda: raw)
        self.assertEqual(result["state"], "OK")
        self.assertFalse(missing.exists())

    def test_stale_expected_digest_returns_no_content_in_either_scope(self):
        hit, raw = self.public_hit()
        public = network_read(self.engine, hit["id"], "0" * 64, loader=lambda: raw)
        local = network_read(self.engine, "local:" + self.local["source_id"], "0" * 64)
        self.assert_rejected(public, "CHANGED", "SOURCE_DIGEST_MISMATCH")
        self.assert_rejected(local, "CHANGED", "SOURCE_DIGEST_MISMATCH")

    def test_public_document_changed_after_search_is_not_returned_under_old_digest(self):
        doc = public_document()
        hit, _ = self.public_hit(doc)
        changed = copy.deepcopy(doc)
        changed["text"] = "GG24 replacement text which was never selected"
        result = network_read(self.engine, hit["id"], hit["digest"], loader=lambda: public_index([changed]))
        self.assert_rejected(result, "CHANGED", "SOURCE_DIGEST_MISMATCH")

    def test_unknown_identifiers_never_fall_back_to_similar_titles(self):
        hit, raw = self.public_hit()
        public = network_read(self.engine, "public:fixture:gg24-missing", hit["digest"], loader=lambda: raw)
        local = network_read(self.engine, "local:src_" + "0" * 20, self.local["digest"])
        self.assert_rejected(public, "NOT_FOUND", "SOURCE_NOT_FOUND")
        self.assert_rejected(local, "NOT_FOUND", "SOURCE_NOT_FOUND")

    def test_local_retraction_blocks_even_when_source_digest_still_matches(self):
        self.engine.store.set_status(self.local["source_id"], "retracted", note="withdrawn fixture")
        self.assert_rejected(self.local_read(), "NOT_CURRENT", "SOURCE_NOT_CURRENT")

    def test_explicit_historical_read_returns_retracted_bytes_as_noncurrent(self):
        self.engine.store.set_status(self.local["source_id"], "retracted", note="withdrawn fixture")
        result = self.local_read(include_historical=True)
        self.assertEqual(result["state"], "OK")
        self.assertFalse(result["usable_as_current"])
        self.assertEqual(result["effective_status"], "retracted")
        self.assertEqual(result["content"]["text"], self.local_text)

    def test_inactive_origin_blocks_a_still_active_derived_source(self):
        child = self.engine.store.ingest_bytes("derived.txt", b"GG24 derived source", metadata={
            "parent_source_id": self.local["source_id"], "parent_digest": self.local["digest"]})
        self.engine.store.set_status(self.local["source_id"], "retracted", note="origin withdrawn")
        self.assertEqual(self.engine.store.status_map()[child["source_id"]]["status"], "active")
        self.assert_rejected(self.local_read(child), "NOT_CURRENT", "SOURCE_NOT_CURRENT")
        historical = self.local_read(child, include_historical=True)
        self.assertEqual(historical["state"], "OK")
        self.assertFalse(historical["usable_as_current"])
        self.assertEqual(historical["effective_status"], "retracted")

    def test_search_applies_parent_status_before_limit_and_preserves_historical_label(self):
        child = self.engine.store.ingest_bytes("derived.txt", b"statusboundary " * 20, metadata={
            "parent_source_id": self.local["source_id"], "parent_digest": self.local["digest"]})
        independent = self.engine.store.ingest_bytes("independent.txt", b"statusboundary")
        loader = lambda: public_index([])
        before = network_search(self.engine, "statusboundary", limit=1, loader=loader)
        self.assertEqual(before["hits"][0]["id"], "local:" + child["source_id"])
        self.engine.store.set_status(self.local["source_id"], "retracted", note="origin withdrawn")
        snapshot = self.snapshot()

        current = network_search(self.engine, "statusboundary", limit=1, loader=loader)
        self.assertEqual(current["state"], "OK")
        self.assertEqual([hit["id"] for hit in current["hits"]], ["local:" + independent["source_id"]])
        self.assertTrue(current["hits"][0]["usable_as_current"])
        historical = network_search(self.engine, "statusboundary", include_historical=True, loader=loader)
        child_hit = next(hit for hit in historical["hits"] if hit["id"] == "local:" + child["source_id"])
        self.assertEqual(child_hit["status"], "active")
        self.assertEqual(child_hit["effective_status"], "retracted")
        self.assertFalse(child_hit["usable_as_current"])
        compact = compact_network_result(historical)
        compact_child = next(hit for hit in compact["hits"] if hit["id"] == child_hit["id"])
        self.assertEqual(compact_child["effective_status"], "retracted")
        self.assertFalse(compact_child["usable_as_current"])
        self.assertEqual(self.snapshot(), snapshot)

    def test_invalid_local_derivation_metadata_preserves_public_scope(self):
        rows = self.engine.store.sources()
        rows[0]["metadata"] = ["damaged-record"]
        self.engine.store.sources_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        snapshot = self.snapshot()
        result = network_search(self.engine, "GG24", loader=public_index)
        self.assertEqual(result["state"], "PARTIAL")
        self.assertEqual(result["scopes"]["local_source"]["state"], "ERROR")
        self.assertEqual(result["scopes"]["local_source"]["error"], "LOCAL_SOURCE_METADATA_INVALID")
        self.assertEqual(result["scopes"]["public_description"]["state"], "OK")
        self.assertEqual([hit["source_scope"] for hit in result["hits"]], ["public_description"])
        self.assertEqual(self.snapshot(), snapshot)

    def test_public_archive_needs_explicit_historical_selection(self):
        doc = public_document(historical=True)
        hit, raw = self.public_hit(doc)
        blocked = network_read(self.engine, hit["id"], hit["digest"], loader=lambda: raw)
        self.assert_rejected(blocked, "NOT_CURRENT", "SOURCE_NOT_CURRENT")
        result = network_read(self.engine, hit["id"], hit["digest"], include_historical=True, loader=lambda: raw)
        self.assertEqual(result["state"], "OK")
        self.assertFalse(result["usable_as_current"])
        self.assertEqual(result["content"]["text"], doc["text"])

    def test_unicode_pagination_reassembles_exact_content_in_both_scopes(self):
        doc = public_document()
        doc["text"] = "GG24 A🌊Бe\u0301\n尾🙂Z"
        hit, raw = self.public_hit(doc)
        for name, read_page, expected in [
            ("local", lambda offset: self.local_read(offset=offset, max_chars=4), self.local_text),
            ("public", lambda offset: network_read(self.engine, hit["id"], hit["digest"],
                offset=offset, max_chars=4, loader=lambda: raw), doc["text"]),
        ]:
            with self.subTest(scope=name):
                chunks = []
                offset = 0
                for _ in range(len(expected) + 1):
                    result = read_page(offset)
                    self.assertEqual(result["state"], "OK")
                    content = result["content"]
                    self.assertEqual(content["offset"], offset)
                    self.assertEqual(content["text"], expected[offset:offset + 4])
                    self.assertEqual(content["returned_chars"], len(content["text"]))
                    self.assertEqual(content["total_chars"], len(expected))
                    self.assertLessEqual(content["returned_chars"], 4)
                    chunks.append(content["text"])
                    if not content["has_more"]:
                        self.assertIsNone(content["next_offset"])
                        break
                    self.assertEqual(content["next_offset"], offset + content["returned_chars"])
                    self.assertTrue(content["truncated"])
                    offset = content["next_offset"]
                else:
                    self.fail("pagination never reached the end")
                self.assertEqual("".join(chunks), expected)

    def test_offset_at_end_is_empty_and_beyond_end_is_an_error(self):
        at_end = self.local_read(offset=len(self.local_text))
        self.assertEqual(at_end["state"], "OK")
        self.assertEqual(at_end["content"]["text"], "")
        self.assertEqual(at_end["content"]["returned_chars"], 0)
        self.assertFalse(at_end["content"]["has_more"])
        beyond = self.local_read(offset=len(self.local_text) + 1)
        self.assert_rejected(beyond, "ERROR", "OFFSET_OUT_OF_RANGE")

    def test_argument_validation_precedes_workspace_or_network_io(self):
        loader = Mock(side_effect=AssertionError("unexpected network"))
        defaults = {"identifier": "local:" + self.local["source_id"], "expected_digest": self.local["digest"]}
        cases = [
            {"identifier": ""}, {"identifier": None}, {"identifier": "https://elsewhere.invalid/source"},
            {"expected_digest": "short"}, {"expected_digest": "z" * 64}, {"expected_digest": None},
            {"include_historical": "yes"}, {"include_historical": 1},
            {"offset": -1}, {"offset": True}, {"offset": 0.5},
            {"max_chars": 0}, {"max_chars": -1}, {"max_chars": 32001},
            {"max_chars": True}, {"max_chars": 4.0},
        ]
        with patch.object(self.engine.store, "require", side_effect=AssertionError("unexpected workspace read")) as require, \
                patch.object(self.engine.store, "sources", side_effect=AssertionError("unexpected source read")) as sources:
            for changes in cases:
                with self.subTest(changes=changes):
                    with self.assertRaisesRegex(ValueError, "^NETWORK_READ_ARGUMENT_INVALID$"):
                        network_read(self.engine, **{**defaults, **changes}, loader=loader)
            require.assert_not_called()
            sources.assert_not_called()
        loader.assert_not_called()

    def test_changed_object_bytes_are_an_integrity_error_not_selected_content(self):
        path = self.engine.store.objects / self.local["digest"]
        data = bytearray(path.read_bytes())
        data[0] ^= 1
        path.write_bytes(data)
        self.assert_rejected(self.local_read(), "ERROR", "LOCAL_SOURCE_BYTES_CHANGED")

    def test_wrong_recorded_byte_length_is_rejected(self):
        rows = self.engine.store.sources()
        rows[0]["byte_length"] += 1
        self.engine.store.sources_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        self.assert_rejected(self.local_read(), "ERROR", "LOCAL_SOURCE_BYTE_LENGTH_CHANGED")

    def test_oversized_local_object_is_bounded_before_reading_content(self):
        path = self.engine.store.objects / self.local["digest"]
        with path.open("ab") as stream:
            stream.truncate(MAX_LOCAL_SOURCE_BYTES + 1)
        self.assert_rejected(self.local_read(), "ERROR", "LOCAL_SOURCE_MISSING_OR_TOO_LARGE")

    def test_symlink_object_is_rejected_even_with_matching_target_bytes(self):
        target = self.root / "matching-external.txt"
        target.write_bytes(self.local_text.encode("utf-8"))
        object_path = self.engine.store.objects / self.local["digest"]
        object_path.unlink()
        try:
            object_path.symlink_to(target)
        except (OSError, NotImplementedError) as error:
            self.skipTest("symlinks unavailable: " + type(error).__name__)
        self.assert_rejected(self.local_read(), "ERROR", "LOCAL_SOURCE_SYMLINK")

    def test_binary_source_is_not_lossily_presented_as_verified_text(self):
        binary = self.engine.store.ingest_bytes("binary.bin", b"GG24\xff\xfe\x00")
        self.assert_rejected(self.local_read(binary), "ERROR", "SOURCE_NOT_UTF8")

    def test_unknown_public_schema_and_private_document_fail_closed(self):
        hit, raw = self.public_hit()
        wrong_schema = json.loads(raw)
        wrong_schema["schema"] = "unrecognized.v99"
        private = public_document()
        private["visibility"] = "private"
        for payload, code in [
            (json.dumps(wrong_schema).encode(), "PUBLIC_INDEX_SCHEMA_INVALID"),
            (public_index([private]), "PUBLIC_VISIBILITY_INVALID"),
        ]:
            with self.subTest(code=code):
                result = network_read(self.engine, hit["id"], hit["digest"], loader=lambda: payload)
                self.assert_rejected(result, "ERROR", code)

    def test_success_and_rejections_leave_workspace_bytes_and_ledger_unchanged(self):
        self.engine.run("GG24")
        hit, raw = self.public_hit()
        before = self.snapshot()
        self.assertEqual(self.local_read()["state"], "OK")
        self.assertEqual(network_read(self.engine, hit["id"], hit["digest"], loader=lambda: raw)["state"], "OK")
        self.assertEqual(network_read(self.engine, hit["id"], "0" * 64, loader=lambda: raw)["state"], "CHANGED")
        self.assertEqual(self.local_read(offset=len(self.local_text) + 1)["state"], "ERROR")
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
