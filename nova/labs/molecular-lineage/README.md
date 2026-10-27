# Molecular Lineage Lab 1.0.0

A local, interactive molecular-history demonstrator connected to NOVA 2.1.2.
It distinguishes **species**, **modeled molecule instance**, **atom ID**,
**model event**, **viewed state** and **NOVA recording time**.

## Start

Requires Python 3.11+ and Node.js 22+. No package install, remote API key,
model provider or runtime network fetch is required.

From the repository root:

```powershell
python nova/labs/molecular-lineage/serve.py --workspace C:\MY_RESEARCH\molecular-state
```

The server prints its loopback URL with a free port. Open that URL. The private
workspace must be separate from the served application directory. The server
binds `127.0.0.1` only and serves a fixed asset allowlist. No workspace contents,
source files from unrelated projects or local paths are exposed by the API.

To continue an existing workspace, make an explicit, fresh local fork first:

```powershell
python nova/labs/molecular-lineage/prepare_continuity.py --predecessor C:\MY_RESEARCH\prior-state --workspace C:\MY_RESEARCH\molecular-state
```

This verifies the predecessor, copies `.nova`, checks exact journal prefixes,
migrates derived analyses in the new copy using NOVA 2.1.2, and writes a
`PREDECESSOR.json` receipt. The predecessor files remain unchanged. A fresh
directory is required; the helper never replaces an existing workspace.

## Use

1. Choose **DMT auf seinem Weg** or **Aus zwei werden drei**.
2. Start playback, pause, step, scrub, or jump to a labeled chapter.
3. Select an instance from the scene or list; select an atom in its inspector.
4. Compare the same initial configuration with only the model membrane changed.
5. Choose **In NOVA festhalten** to ingest and verify the exact checkpoint bytes,
   or download the JSON record.
6. Expand **Gebundene Forschungshistorie** and reopen a saved checkpoint. New
   checkpoints retain the selected instance and atom; older packets without a
   view selection remain readable.

Changing a model parameter creates a new run ID with a parent-run reference.
The parent reference names a local UI branch, not an authenticated external
source or a guarantee that the parent was saved. A downloaded checkpoint is
self-contained. It contains the full declared model plan plus a separately
identified viewed step; future plan events are not completed observations.
At the reaction instant, coincident product positions are fanned out only in
the renderer with leaders and a visible projection label. Their saved model
coordinates remain unchanged.

## Two complementary experiments

- **DMT journey:** three instances of the neutral species PubChem CID 6089,
  each with 30 atom IDs. Transport, schematic contact, binding and release retain
  each instance ID. Geometry and model timing are declared educational rules.
  The binding site is generic, with no receptor affinity or clinical kinetics.
- **Catalase net reaction:** `2 H2O2 = 2 H2O + O2`, sourced to Rhea:20309 and
  IUBMB EC 1.11.1.6. Two reactant instances retire; three product instances are
  created. Eight atom IDs remain, each with one current owner. The chosen atom
  mapping is a demonstrator convention, not an isotope-tracer measurement or
  an elementary reaction mechanism. The enzyme is represented as a labeled
  reaction field; enzyme/cofactor atoms are outside the net-reactant scope.

PubChem records are exact retained public response bodies. `data/sources.json`
binds each URL, acquisition time, length and hash. The 2D coordinates depict
connectivity, not measured conformational motion. Explicit hydrogens and the
selected CIDs define this model's species/protonation scope.

## Actual NOVA boundary

The browser creates a checkpoint containing the run, viewed state, audit and
fully addressed atom-transfer relations. The local server:

1. Enforces exact host/origin, JSON content type, body size and a fixed endpoint.
2. Runs the **fixed, repository-controlled** verifier with the packet on stdin.
   No supplied code, path or command is dispatched.
3. Regenerates the declared plan and snapshot; rejects changed fields/digests.
4. Binds a run ID to one plan digest and ingests exact canonical checkpoint
   bytes into NOVA, with model-source and chemical-source bindings.
5. Appends a real Workbench FLOW research receipt and verifies/readbacks it.
6. Returns source ID, source SHA-256, packet digest, previous and new ledger
   hashes and sequence. An identical completed request returns its old receipt.

The server has a 200-checkpoint local budget and a 512,000-byte request limit.
The bridge serializes writes within one server process; NOVA's own OS lock also
protects its store writes. Multiple simultaneous lab servers against the same
workspace are outside this bridge's transactional scope. An interrupted write
may leave an ingested source or completed NOVA run without a lab receipt; the
API reports an incomplete write and retains the original state for inspection.
This lab does not claim a distributed transaction or crash-atomic multi-file
commit. A receipt's hashes prove byte/ledger binding, not empirical chemistry.

## Verify

```powershell
node --test nova/labs/molecular-lineage/engine.test.mjs
python -X utf8 nova/labs/molecular-lineage/test_bridge.py
```

The bounded sweep covers both scenarios, both gate states, five seeds and all
61 view steps. The replay oracle checks current atom ownership separately from
geometric projection. Both are code paths in one provenance cluster; they do
not constitute independent experimental confirmation. The bridge tests use a
fresh local NOVA workspace, actual HTTP, ingest/readback/verify and idempotent
retry, plus malformed records, origin/host and serving-boundary countercases.

`acquire_sources.py` is an optional, explicit public-source acquisition tool.
It is never called at application startup and refuses to replace retained
files. Source metadata and data remain separate from runtime history.

License: new code and documentation use HALVETH PIRL 2.0 as mapped in
`nova/LICENSES.md`. Upstream source facts and retained records keep their own
attributions and rights.
