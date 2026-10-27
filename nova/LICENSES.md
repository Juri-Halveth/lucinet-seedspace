# NOVA license map

This file maps only the new material under `nova/`. It does **not** relicense pre-existing Seedspace files outside this directory.

| Paths | License |
| --- | --- |
| `src/halveth_nova/**`, `tests/**`, `contracts/**`, `examples/**`, `labs/molecular-lineage/**` (except the external source data described below), `README.md`, `WORKBENCH.md`, `MAINTENANCE_2_0_3.md`, `NOVA_CORE_PROMPT.md`, `pyproject.toml` | [HALVETH Public-Interest Research License 2.0](LICENSE-HALVETH-PIRL-2.0.md), to the extent the rights are controlled by Juri Janovski / Juri-Halveth. |
| `LICENSE-HALVETH-PIRL-2.0.md` | The unmodified license text may be copied for identification and review under its own terms. |

External facts, linked sources, names and third-party material keep their own status. Existing repository material outside `nova/` retains its historical rights status.

`labs/molecular-lineage/data/pubchem-*.json` are exact public PubChem response
bodies with upstream attributions preserved. The derived `data/sources.json`
identifies acquisition URLs, dates, byte lengths and SHA-256 values. Chemical
facts and the Rhea/IUBMB reaction equation retain their source status; the
HALVETH license does not assert ownership of those facts or relicense upstream
material. The selected atom mapping, model engine, interface and bridge are
new HALVETH material.

The four exact upstream modules named in `src/halveth_nova/workbench/_integrations/lagefaden/SOURCE_BINDINGS.json`
retain MIT under that directory's `LICENSE-MIT.txt`. This is an exception to the
original-material row above. The new bridge `run.mjs`,
workbench modules, tests and documentation are new HALVETH PIRL 2.0 material.
