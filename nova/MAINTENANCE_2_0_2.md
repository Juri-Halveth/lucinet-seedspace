# NOVA 2.0.2 — workbench maintenance

This patch addresses the five workbench review findings on PRs #4 and #5.
The earlier 1.2.1 continuity and locking repairs remain unchanged.

## Processing and limits

- A corrupt DOCX produces a `FAILED` adapter result with a named coverage gap.
  Its retained source does not prevent later controller runs, including after
  retraction or removal of the original input file.
- Indexing reads at most `MAX_BYTES + 1` bytes per admitted read. A file growing
  after its size check cannot make this read allocate its entire new contents.
- Explicit query graphs with more than eight nodes are rejected before a run.
  A larger model-derived query remains visible as a rejected interpretation
  and an `OPEN` coverage gap; it is not sent into the eight-node matcher.
  Source graphs retain their separate, larger graph-size contract.

## Build manifest

Verification reconstructs the exact final `BUILD_MANIFEST.json` bytes from
the already bound build descriptor. Deleting, replacing or reformatting the
manifest fails verification. The manifest does not contain a hash of itself.
The same reconstruction checks existing 2.0/2.0.1 build descriptors.

## Historical derivations and time

Each archived analysis is also stored as a `workbench-history` source with its
raw byte digest, byte length, archive filename and binding time. A historical
source-status event keeps that binding visible. History records are excluded
from the workbench's active adapter and structural retrieval lanes.

After binding, verification detects deletion of one archive, loss of the
entire history folder, and byte changes that preserve canonical JSON content.
Later compilation rejects changed bound bytes instead of silently rebinding
or recreating them.

For a legacy workspace, the next `index`/`work` compilation checks existing
unbound historical analyses and records their current raw bytes with
`binding_origin=LEGACY_SNAPSHOT_AT_UPGRADE`. A direct `verify` before this
step reports an unbound history inventory. This first binding is an observed
upgrade-time snapshot: it cannot prove earlier bytes, recover an archive
already missing before the snapshot, authenticate an author, or rule out a
coordinated rewrite of the whole local store and its trust anchors.

Normal cache upgrades use `binding_origin=CACHE_UPGRADE`; source record
`added_at`, source-status event time and the later run receipt retain their
separate time addresses. Existing source bytes and earlier receipts remain.

## Scoped regression evidence

`tests/test_workbench_maintenance.py` uses only temporary workspaces, small
invalid document bytes, mocked model responses and synthetic build/cache
changes. Its eleven test methods fail on the preceding workbench and pass
after this patch. They supplement the existing regression suite; they do not
constitute an audit of arbitrary documents, live model services, or all user
workspaces.

Run the suite with the package installed or `PYTHONPATH` pointing to `nova/src`
so child-process locking tests import the same candidate as their parent.
No private research corpus is required.
