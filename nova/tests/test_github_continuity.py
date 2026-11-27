from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from halveth_nova.engine import NovaEngine
from halveth_nova.workbench import github_adapter


A = 'a' * 40
B = 'b' * 40
OLD = b'CONTINUITYTOKEN: OLD endpoint\n'
NEW = b'CONTINUITYTOKEN: NEW endpoint\n'


def blob(raw):
    return hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


class GitHubContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = NovaEngine(Path(self.tmp.name)/'workspace')
        self.engine.init('synthetic-github-continuity')

    def tearDown(self):
        self.tmp.cleanup()

    def capture(self, revision, body, *, ref=None, fail_blob=False, on_blob=None, unbound_head=None, returned_body=None):
        def api(path, **kwargs):
            root = 'repos/Synthetic/Example'
            if path == root:
                return {'default_branch':'main'}
            if path.startswith(root + '/commits/'):
                if path == root + '/commits/HEAD' and unbound_head:
                    return {'sha':unbound_head, 'parents':[], 'commit':{'message':'changed default branch'}}
                return {'sha':revision, 'parents':[], 'commit':{'message':'synthetic fixture'}}
            if path == root + '/git/trees/' + revision + '?recursive=1':
                return {'sha':revision, 'truncated':False, 'tree':[{'type':'blob', 'path':'README.md', 'size':len(body), 'sha':blob(body)}]}
            if path == root + '/git/blobs/' + blob(body):
                if on_blob:
                    on_blob()
                if fail_blob:
                    raise RuntimeError('SYNTHETIC_GITHUB_READ_FAILURE')
                data = body if returned_body is None else returned_body
                return {'content':base64.b64encode(data).decode(), 'encoding':'base64'}
            if path.startswith(root + '/') and any(x in path for x in ('/branches?', '/pulls?', '/issues?', '/commits?')):
                return []
            raise AssertionError(path)
        with patch.object(github_adapter, 'api', api):
            return github_adapter.inventory(self.engine.store, 'Synthetic', repo='Example', ref=ref, max_files=1)

    def file_rows(self):
        return [row for row in self.engine.store.sources() if row['locator'].endswith('/README.md')]

    def statuses(self):
        states = self.engine.store.status_map()
        return {(row['metadata'].get('github_resolved_ref'), row['metadata']['commit']):states[row['source_id']]['status'] for row in self.file_rows()}

    def test_second_head_supersedes_previous_snapshot_without_deleting_bytes(self):
        self.capture(A, OLD)
        self.capture(B, NEW)
        self.assertEqual(self.statuses(), {('main',A):'superseded', ('main',B):'active'})
        hits = [row for row in self.engine.search('CONTINUITYTOKEN') if row['locator'].endswith('/README.md')]
        self.assertEqual(len(hits),2)
        self.assertEqual(sum(row['usable_as_current'] for row in hits),1)
        self.assertEqual({(self.engine.store.objects/row['digest']).read_bytes() for row in self.file_rows()}, {OLD,NEW})
        self.assertTrue(self.engine.store.verify()['ok'])

    def test_unchanged_content_at_new_commit_retains_both_exact_revision_bindings(self):
        self.capture(A, OLD)
        self.capture(B, OLD)
        rows=self.file_rows()
        self.assertEqual(len(rows),2)
        self.assertEqual(len({r['digest'] for r in rows}),1)
        self.assertEqual({r['metadata']['commit'] for r in rows},{A,B})
        self.assertEqual(self.statuses(),{('main',A):'superseded',('main',B):'active'})

    def test_other_branch_has_a_separate_current_selection(self):
        self.capture(A, OLD, ref='feature')
        self.capture(A, OLD, ref='main')
        self.capture(B, NEW, ref='main')
        self.assertEqual(self.statuses(),{('feature',A):'active',('main',A):'superseded',('main',B):'active'})

    def test_default_head_and_explicit_branch_use_the_same_scope(self):
        first=self.capture(A,OLD)
        second=self.capture(B,NEW,ref='refs/heads/main')
        self.assertEqual(first['currentness_scope'],second['currentness_scope'])
        self.assertEqual(self.statuses(),{('main',A):'superseded',('main',B):'active'})

    def test_default_branch_change_cannot_capture_unbound_head_in_the_old_scope(self):
        result=self.capture(A,OLD,unbound_head=B)
        self.assertEqual(result['reference'],'main')
        self.assertEqual(result['commit'],A)
        self.assertEqual(self.statuses(),{('main',A):'active'})

    def test_explicit_commit_is_historical_without_replacing_branch_selection(self):
        self.capture(B,NEW)
        result=self.capture(A,OLD,ref=A)
        self.assertEqual(result['selection'],'HISTORICAL_PINNED_COMMIT')
        self.assertEqual(self.statuses(),{('main',B):'active',(A,A):'historical'})

    def test_network_failure_leaves_prior_capture_and_workspace_bytes_untouched(self):
        self.capture(A,OLD)
        base=self.engine.store.nova
        before={p.relative_to(base).as_posix():p.read_bytes() for p in base.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(RuntimeError,'SYNTHETIC_GITHUB_READ_FAILURE'):
            self.capture(B,NEW,fail_blob=True)
        after={p.relative_to(base).as_posix():p.read_bytes() for p in base.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_wrong_blob_bytes_do_not_replace_current_source(self):
        self.capture(A, OLD)
        with self.assertRaisesRegex(ValueError, 'GITHUB_BLOB_ID_MISMATCH'):
            self.capture(B, NEW, returned_body=OLD)
        self.assertEqual(self.statuses(), {('main', A): 'active'})

    def test_commit_lock_failure_preserves_retraction_and_all_workspace_bytes(self):
        self.capture(A,OLD)
        sid=self.file_rows()[0]['source_id']
        self.engine.store.set_status(sid,'retracted',note='explicit owner withdrawal')
        base=self.engine.store.nova
        before={p.relative_to(base).as_posix():p.read_bytes() for p in base.rglob('*') if p.is_file()}
        original_lock=self.engine.store.write_lock
        calls=0
        @contextmanager
        def unavailable_commit_lock():
            nonlocal calls
            calls+=1
            if calls==2:
                raise RuntimeError('WORKSPACE_BUSY')
            with original_lock():
                yield
        with patch.object(self.engine.store,'write_lock',unavailable_commit_lock):
            with self.assertRaisesRegex(RuntimeError,'WORKSPACE_BUSY'):
                self.capture(B,NEW)
        after={p.relative_to(base).as_posix():p.read_bytes() for p in base.rglob('*') if p.is_file()}
        self.assertEqual(before,after)
        self.assertEqual(self.engine.store.status_map()[sid]['status'],'retracted')

    def test_return_to_a_previous_commit_reactivates_that_capture(self):
        self.capture(A,OLD)
        self.capture(B,NEW)
        self.capture(A,OLD)
        self.assertEqual(self.statuses(),{('main',A):'active',('main',B):'superseded'})
        self.assertEqual(len(self.file_rows()),2)

    def test_retracted_source_is_not_silently_reactivated(self):
        self.capture(A,OLD)
        sid=self.file_rows()[0]['source_id']
        self.engine.store.set_status(sid,'retracted',note='explicit owner withdrawal')
        self.capture(A,OLD)
        self.assertEqual(self.engine.store.status_map()[sid]['status'],'retracted')

    def test_legacy_unscoped_source_is_retained_with_unknown_reference(self):
        legacy=self.engine.store.ingest_bytes('github/Synthetic/Example/'+A+'/README.md',OLD,
            tags=['github','source'],metadata={'commit':A,'git_blob':blob(OLD)})
        withdrawn=self.engine.store.ingest_bytes('github/Synthetic/Example/'+A+'/retired.md',OLD,
            tags=['github','source'],metadata={'commit':A,'git_blob':blob(OLD)})
        self.engine.store.set_status(withdrawn['source_id'],'retracted',note='explicit owner withdrawal')
        self.capture(B,NEW)
        self.assertEqual(self.engine.store.status_map()[legacy['source_id']]['status'],'historical')
        self.assertEqual(self.engine.store.status_map()[withdrawn['source_id']]['status'],'retracted')
        self.assertEqual((self.engine.store.objects/legacy['digest']).read_bytes(),OLD)

    def test_an_overlapping_successful_capture_requires_retry(self):
        self.capture(A,OLD)
        def advance():
            self.capture(B,NEW)
        with self.assertRaisesRegex(RuntimeError,'GITHUB_REFERENCE_CHANGED_RETRY'):
            self.capture(A,OLD,on_blob=advance)
        self.assertEqual(self.statuses(),{('main',A):'superseded',('main',B):'active'})


if __name__ == '__main__':
    unittest.main()
