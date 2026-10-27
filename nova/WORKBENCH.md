# NOVA 2.1.0: from source collection to reusable work

NOVA combines the existing exact-byte source store and receipt ledger with
bounded source consumers, structural queries, work controllers and executable
builds. A generated result becomes a searchable source for the next run.

## Start with a real offline run

From the repository root, with Python 3.11 or newer:

```bash
python nova/nova.py --workspace ./nova-demo demo
```

Choose a fresh directory for each demonstration. This command creates three
synthetic graphs with different names/domains, executes all four controllers,
builds a portable graph-analysis program, compiles it, runs its self-check and
prints the offline HTML viewer path. Open that `index.html` in a browser.
The viewer has source filtering, a graph selector, open questions and actual
execution results. It has no remote assets or automatic scrolling.

For your own bounded collection:

```bash
python nova/nova.py --workspace ./research init --name research
python nova/nova.py --workspace ./research index ./notes ./code --limit 500
python nova/nova.py --workspace ./research work "previous observations and open origin questions" --mode ATLAS
python nova/nova.py --workspace ./research work "build the reusable analysis" --mode BUILD
python nova/nova.py --workspace ./research resume
python nova/nova.py --workspace ./research verify
python nova/nova.py --workspace ./research export ./research-state.zip
```

`run` is the original receipt-writing command. `work` executes these controllers:

| Mode | Additional work actually executed |
| --- | --- |
| FLOW | Compile source consumers; retrieve up to three source hits. |
| ATLAS | Also inspect active graphs, structurally match a supplied pattern, bind relation endpoints, recover prior work and retain unknown lineage. |
| DEEP | Also select a recurring unknown and reverse the query's edges as a finite structural countertest. |
| BUILD | Also generate a portable analysis program, compile it and run its self-check. An explicit function specification enables the separate function builder. |

The structural matcher ignores names but requires injective node mapping,
matching functional kinds/definitions and directed predicate edges. It searches
within declared graphs. Cross-domain matches are model structure matches; they
do not establish physical equivalence or causal identity. Query patterns have
at most eight nodes; target graphs at most 256; search budgets remain visible.
Use `--pattern path/to/concept-graph.json` for an explicit structural query.

## Association expansion and essence farming

```bash
python nova/nova.py --workspace ./essence-demo init --name essence-demo
python nova/nova.py --workspace ./essence-demo essence-farm nova/examples/essence-nova.json --local-model qwen2.5:14b
python nova/nova.py --workspace ./essence-demo work "NOVA erinnert mich an frühere Spuren" --mode DEEP
python nova/nova.py --workspace ./essence-demo verify
```

The first command after initialization compiles supplied source cards into
quoted readings with an explicitly selected, already installed local model.
It generates a portable HTML view, compares every branch pair and computes
candidate analogies from shared adjacent role IDs. The source-card input,
exact model response and expanded request are retained separately. Invalid
model quotes are rejected and the rejected response remains historical.
Without `--local-model`, only supplied branches are compared; empty branches
produce an explicit research plan. The runtime does not browse or fetch URLs.
An agent can research primary sources, add cards and continue from that plan.

`work` recognizes a bounded lexical association cue in German or English and
opens fifteen axes, even when no matching source cards exist. This is a routing
heuristic rather than a claim about the user's intention. Explicit selection
uses `work QUERY --essence-source SOURCE_ID`. Retracted or superseded parents
cannot reenter as current input. New questions and request references enter
the normal receipt and continuation seed; previous results remain searchable.

Each quote binds all exact UTF-16 occurrences in a supplied card, its text
digest and JSON field address. The card's origin URL remains a declared
pointer; a user or agent must separately verify its source. Identical role IDs
are declared abstractions and do not prove a shared mechanism, common origin,
semantic correctness or independent evidence. Domain differences, direction
controls, missing axes and falsifiers stay in the viewer and JSON result.

The included NOVA example contains short editorial source cards for NASA,
Blizzard and the committed project prompt. Its empty branch list is deliberate:
the actual local compiler proposes readings instead of receiving a prefilled
answer. Other words and domains use the same request contract.

`essence-nova-reviewed.json` is the separate analyst-authored comparison input,
including differences and open questions. It is not presented as an autonomous
model result. Operator 1.0.1 binds question identity to seed, kind, branch/domain
and exact question; older 1.0.0 receipts retain their original verifier behavior.
Operator 1.0.2 adds an explicit recording time, timebase and relation type to
new comparison records; 1.0.0 and 1.0.1 remain separately reproducible.

## Local concept inference and a new executable function

The base workbench uses the standard library. An optional local Ollama service
at the fixed loopback endpoint can compile quoted source text into inferred
concept graphs and aliases. Select an installed model explicitly:

```bash
python nova/nova.py capabilities
python nova/nova.py --workspace ./research index ./notes --local-model qwen2.5:14b
python nova/nova.py --workspace ./research work "Which observation was only relayed?" --mode ATLAS --local-model qwen2.5:14b
python nova/nova.py --workspace ./ai-demo demo --local-model qwen2.5:14b --generate-function
```

No model is downloaded by these commands. The selected installed model's digest
and local service declaration are bound. Source text remains data. The compiler
rejects invented quotes, preserves every matching UTF-16 span for ambiguous
quotes and keeps inferred graphs separate from declared source graphs.
This is artifact-based reuse and reconstruction; it does not train model weights.

A general pure-function build uses this specification shape:

```json
{
  "contract": "nova.pure-build-spec.v1",
  "description": "Implement solve(data): return the sum of the input JSON number list.",
  "cases": [
    {"id": "empty", "input": [], "expected": 0},
    {"id": "mixed", "input": [2, -1, 4], "expected": 5}
  ]
}
```

```bash
python nova/nova.py --workspace ./research work "implement a reusable sum" --mode BUILD --local-model qwen2.5:14b --build-spec sum-spec.json
python nova/nova.py apply-function path/to/generated-function/candidate.py --input numbers.json
```

Description and cases are bound before generation. The model receives the
description, the restricted language contract and repair feedback; it never
receives the cases or their outputs. At most three attempts are allowed.
Rejected bytes remain intact. Imports, IO, reflection, arbitrary methods and
module-level execution are rejected before evaluation. An isolated child has
time and memory/process limits. This versioned pure-JSON language evaluator
is not a general Python or OS sandbox. General application builds and device
control need a separately configured executor and remain open capabilities.

Passing selected code and its specification become new sources. Failed attempts
are searchable historical sources. A later `work` run can recover the build by
its task or function description. Original inputs and the Git base remain
available. The viewer and build manifest are refreshed with the final outcome;
`verify` checks their bytes as well as source/ledger integrity.

## Media and documents

```bash
python -m pip install -r nova/requirements-media.txt
python nova/nova.py --workspace ./research index ./documents ./images ./short-media
python nova/nova.py --workspace ./research describe image.png --vision-model qwen3-vl:2b
python nova/nova.py --workspace ./research transcribe speech.wav --model-directory ./models/local-whisper --language en --seconds 30
```

Optional dependencies belong in a dedicated virtual environment. Speech and
vision model weights must already exist locally. During transcription the
speech consumer uses `local_files_only=True`; vision uses the fixed local
Ollama service. The local service's network behavior is a separate trust boundary.

| Consumer | Representation and coverage |
| --- | --- |
| UTF-8 / Python | Exact text and static AST call sites, without running discovered code. |
| DOCX | Text from document/header/footer XML; layout and embedded imagery remain gaps. |
| PDF | Optional pypdf text, first 50 pages; scanned text and layout may be absent. |
| Image | Optional Pillow dimensions and sampled pixel statistics; explicit local vision inference for objects/text. |
| WAV | Signal metadata and first 30 seconds of RMS; explicit offline transcription is separate. |
| Video | PyAV, first video stream, at most three sampled frames over ten presentation seconds. |
| Speech | First decoded audio stream resampled to 16 kHz mono float32, bounded window, inferred transcript segments. |

Default source size is 8 MB. Indexing skips local state, common secret filenames
and symlinks and stops at its declared file budget. This filename filter is not
a complete privacy classifier. Review sources before any export. Media/PDF
parsers run locally in the host process; hostile-file containment is an open
hardening frontier. A decoded frame or transcript does not authenticate a real
event, speaker, user intention or historical interpretation.

## Existing LAGEFADEN integration

```bash
python nova/nova.py --workspace ./lage-demo demo --node node
```

This reuses four exact MIT modules from the declared source commit, checks their
digests before import, and runs six existing offline replay fixtures with 22
W-question rows per case. Source binding and MIT notice are packaged inside
`src/halveth_nova/workbench/_integrations/lagefaden/`. The bridge has no hardware
or flight/control interface. Its checklist comparison is an executable naive
baseline, not a human study or operational evaluation.

## GitHub inventory and history

An authenticated `gh` installation provides explicit GET-only input:

```bash
python nova/nova.py --workspace ./research universe --owner Juri-Halveth
python nova/nova.py --workspace ./research universe --owner Juri-Halveth --repo lucinet-seedspace --ref main --max-files 10
python nova/nova.py --workspace ./research work "prior repository decisions" --mode ATLAS
```

Content is pinned to the resolved commit. Inventory is one page of at most
100 public repositories; branches, issues, PRs and history have separate page
limits. Tree truncation, read file count and omitted eligible files are explicit.
No automatic repository-wide write, issue submission, push or merge is part of
the input adapter. Commit-pinned history metadata can still contain personal
data; the resulting workspace stays local until a separate export decision.

## Value flow

```bash
python nova/nova.py --workspace ./research value-flow nova/examples/value-flow.json
python nova/nova.py --workspace ./research work "value measurement pilot" --mode DEEP
```

The value inquiry binds a problem, beneficiary role, artifact, comparator,
effect metric, measurement plan, reuse, rights and funding route. Missing fields
become named questions. References are declared pointers until checked; a
supplied status or digest is not promoted into observed benefit.

Those questions also enter the controller's unknown lineage. DEEP selects by
current-task relevance, then prior occurrences and stable ID; unrelated recurring
questions stay present. The exact selected ID and proposed next action are bound
in the continuation seed. This does not authorize a pilot, spending or contact.
An adapter-bundle upgrade recompiles stale caches and preserves their previous
exact bytes; `verify` also checks this historical derivation layer.

An optional `business_case` uses exact decimal strings for `baseline_unit_cost`,
`candidate_unit_cost`, `units`, `adoption_fraction`, `integration_cost` and
`ongoing_cost`, plus `currency`, `period` and
`input_basis: "DECLARED_SCENARIO"`. It computes:

```text
net = (baseline unit cost - candidate unit cost) × units × adoption
      - integration cost - ongoing cost
```

Negative outcomes are retained. This is arithmetic on explicit assumptions.
Realized value, proposed price, a gift and a funding decision have separate
fields. Creator degree and social status are not accepted calculation inputs.

## Verification and next frontier

```bash
PYTHONPATH=nova/src python -m unittest discover -s nova/tests -v
```

The suite covers the original continuity contracts and new negative controls:
status propagation, invented/ambiguous quotes, relation addresses, injected HTML,
stale builds, artifact tampering, hidden cases, rejected capabilities and child
timeouts. Optional media tests skip explicitly when their packages are absent.
GitHub CI also runs the offline controller/integration demonstration.

See [SECURITY_MODEL.md](SECURITY_MODEL.md) for the execution boundary. The next
product question is measured usability and task benefit on a declared real
workflow. Synthetic fixture correctness, a generated function and source
integrity are concrete delivered capabilities; user benefit, market valuation
and general autonomous software engineering remain separate measurement work.

The dated [acceptance snapshot](verification/20261027/ACCEPTANCE.json) binds the
actual generated candidate, attempts, withheld test result and finite coverage.
The [media snapshot](verification/20261027/MEDIA_SUMMARY.json) includes the
synthetic speech reference and inferred text, so recognition errors remain visible.
Development failures are retained alongside the successful acceptance run.
