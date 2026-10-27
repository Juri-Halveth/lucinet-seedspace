# NOVA 2.0.3 — consolidated workbench maintenance

The accepted 2.0.2 workbench implementation at commit `801a795` already fixes
the five supplied findings from PRs #4 and #5. This follow-up retains that
implementation, its archive-reference contract, builder and regression tests.
It adds only a legacy verification edge, consistent package version metadata,
and complementary regression coverage. The earlier 1.2.1 core fixes remain.

## Retained repairs

- Corrupt DOCX input becomes a named `FAILED` analysis and coverage gap;
  subsequent controller work remains available.
- Source reads stop at `MAX_BYTES + 1`, including a source that grows after
  its size check.
- Explicit query graphs above eight nodes are rejected. Oversized model
  interpretations remain visible as an open gap instead of reaching the
  structural matcher. Source graphs retain their larger, separate contract.
- New build results bind their final `BUILD_MANIFEST.json` by raw-byte digest
  and length without requiring a self-hash.
- Cache history references bind expected archive paths, raw-byte digests and
  lengths. Deleting archives or reformatting equivalent JSON is detected;
  subsequent compilation does not silently accept changed bound bytes.

## Additional legacy build edge

Builds created before 2.0.2 lack the new separate manifest descriptor.
Their exact finalized manifest is reconstructible from their bound result.
Verification now compares those expected bytes too. A legacy kit with a
deleted, replaced or reformatted manifest therefore cannot pass merely
because it predates the descriptor field. Healthy old kits remain valid.

CLI, wheel metadata and controller now report the same version, 2.0.3.

## History and time scope

Existing receipt and source times remain separate from the later cache
migration. Legacy migration preserves the current cache bytes before binding
retained archive references. The first upgrade snapshot cannot prove earlier
bytes, recover an archive already missing before that snapshot, authenticate
an author, or rule out a coordinated rewrite of the whole local store.
Source and receipt originals remain available; verification is local integrity
checking within those trust anchors, not proof of complete history.

## Regression coverage

`tests/test_workbench_maintenance.py` supplies twelve complementary methods:
retraction after a corrupt document, model query limits across ATLAS/DEEP/BUILD,
early explicit rejection, exact read bounds, manifest loss/reformatting,
archive loss/reformatting and no silent rebinding, plus a synthetic legacy kit.
The legacy kit passes while unchanged, fails after manifest replacement and
passes after the exact original bytes are restored. On the incoming 2.0.2
source that new legacy replacement check fails; the candidate repairs it.

The growth fixture resolves its path before mocking reads, preserving the
same assertion on Windows long and short temporary paths. Run with the package
installed or `PYTHONPATH` set to `nova/src` for child-process locking tests.
The suite uses temporary synthetic workspaces, no private corpus, no live
model service and no execution of ingested code.
