# NOVA Core 1.2 · LUCINET Research Tank

NOVA Core is a small, dependency-free Python runtime for **finding sources, preserving their exact bytes and status, writing research receipts, and resuming later without silently rewriting history**.

It is intentionally narrower than an AI model. It does not decide truth, execute discovered code, crawl the internet, or merge unrelated sources. It gives an agent or human a durable provenance layer underneath those activities.

## What it gives you

- content-addressed source storage with SHA-256;
- version history when the same locator changes;
- `active`, `historical`, `superseded`, and `retracted` source states;
- Unicode-aware local search with source line spans;
- typed relations such as `SUPPORTS`, `CONTRADICTS`, `CORRECTS`, `MIRRORS`, `SEMIBRIDGES` and `FULLBRIDGES`;
- hash-chained Research Receipts;
- verified `RESUME` / next-seed state;
- stale predecessor rejection;
- strict JSON reading that rejects duplicate object keys;
- source/object/ledger/resume verification;
- reproducible ZIP export with a byte-and-hash manifest;
- no third-party Python runtime dependencies.

A retracted interpretation can still be found, but search marks it as **not current** and lowers its rank. A changed file becomes a new source record while the old one remains as a superseded predecessor.

## Run it

### Zero-install / offline

A repository checkout plus Python 3.11+ is enough:

```bash
python nova/nova.py --version
python nova/nova.py --workspace ./my-research init --name my-research
```

Windows also has:

```bat
nova\nova.cmd --version
```

Linux/macOS:

```bash
./nova/nova.sh --version
```

### Optional CLI installation

If normal Python package build tooling is available:

```bash
python -m pip install -e ./nova
nova --version
```

There are no third-party **runtime** dependencies. The zero-install launcher avoids package installation entirely.

## Five-minute workflow

```bash
mkdir my-research
cd my-research
nova init --name my-research

# Preserve files exactly. Nothing found here is executed.
nova ingest ./notes --tag research
nova ingest ./screenshots/red-star.png --tag ghost --meta description="red symbol candidate"

nova search "red thing with star"

# Keep a correction instead of deleting the old source.
nova source-status src_... retracted --note "later user correction"

# Add a typed relation with explicit source evidence.
nova relate "claim:pulsar-shield" CONTRADICTS "claim:pulsar-neutron-star" \
  --state historical --evidence src_...

# Search, bind the current hits, write a receipt and set the continuation seed.
nova run "find the old drone provenance work" \
  --mode ATLAS \
  --open "Where is the original C-DROHNE source?" \
  --next-seed "Reintegrate LAGEFADEN with the cUxS demonstration"

nova resume
nova verify
nova export nova-state.zip
```

## Workspace format

NOVA creates a `.nova/` directory inside the chosen workspace:

```text
.nova/
  config.json
  objects/<sha256>          exact source bytes
  sources.jsonl             immutable source records
  source-events.jsonl       status history, including retractions/supersession
  relations.jsonl           typed relations
  ledger.jsonl              hash-chained Research Receipts
  resume.json               verified latest continuation seed
```

The source locator is descriptive provenance. The digest binds the bytes actually stored. A hash proves byte identity within the captured material; it does **not** authenticate an external publisher or physical observation.

## Research modes

The receipt records one of four explicit modes:

- `FLOW` — answer the current task with the smallest useful context;
- `ATLAS` — map the surrounding research space;
- `DEEP` — investigate one decisive question;
- `BUILD` — create or integrate a usable artifact.

The runtime does not change behavior magically based on the label. The mode is part of the provenance contract so another human or agent knows what kind of run produced the receipt.

## Status and contradiction handling

NOVA separates **retrieval** from **current interpretation**.

A historical or retracted source stays searchable because deleting it would destroy concept lineage. Search returns:

```json
{
  "status": "retracted",
  "usable_as_current": false
}
```

That prevents a strong lexical match from silently reviving an interpretation that was later corrected.

## Research Receipts

`nova run` writes a receipt containing:

- query and mode;
- exact source IDs, digests, status and hit spans used by the run;
- typed claims, when supplied;
- open questions;
- artifacts;
- visible relation IDs;
- predecessor run/hash;
- next seed.

The receipt is wrapped in a hash-chained ledger entry. `nova verify` recomputes the chain and refuses a stale `resume.json`.

## General-purpose integration

NOVA Core is designed to sit underneath multiple HALVETH/LUCINET projects:

```text
NOVA Core
  source continuity / receipts / resume
        ↓
LAGEFADEN
  source-time / coverage / decision-relevant gaps
        ↓
C-DROHNE / GUARDIAN
  multi-observer cUxS demonstration
```

Other projects can use only NOVA Core without importing LAGEFADEN or drone concepts.

## Deliberate non-features

NOVA Core does **not**:

- execute ingested Python, shell, JavaScript or binaries;
- infer that two sources describe the same real-world event;
- convert a citation or hash into authorization;
- treat a high search score as truth;
- call an LLM or external API by itself;
- claim operational, clinical, military, scientific or legal validity from a successful software test.

Those functions belong to explicit higher layers with their own contracts and tests.

## Tests

```bash
PYTHONPATH=nova/src python -m unittest discover -s nova/tests -v
python nova/nova.py --workspace /tmp/nova-demo init --name demo
python nova/nova.py --workspace /tmp/nova-demo verify
```

The regression suite covers source binding, Unicode search, binary metadata, retracted interpretations, version supersession, typed relations, receipt chaining, stale seeds, tamper detection, duplicate JSON keys and export integrity.

## License

Files under `nova/` are mapped in `nova/LICENSES.md`. The HALVETH Public-Interest Research License 2.0 text is included for the new original NOVA Core material. Existing Seedspace files outside this path keep their pre-existing status and are not silently relicensed by this addition.
