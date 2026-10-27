# NOVA license map

This file maps only the new material under `nova/`. It does **not** relicense pre-existing Seedspace files outside this directory.

| Paths | License |
| --- | --- |
| `src/halveth_nova/**`, `tests/**`, `contracts/**`, `examples/**`, `README.md`, `NOVA_CORE_PROMPT.md`, `pyproject.toml` | [HALVETH Public-Interest Research License 2.0](LICENSE-HALVETH-PIRL-2.0.md), to the extent the rights are controlled by Juri Janovski / Juri-Halveth. |
| `LICENSE-HALVETH-PIRL-2.0.md` | The unmodified license text may be copied for identification and review under its own terms. |

External facts, linked sources, names and third-party material keep their own status. Existing repository material outside `nova/` retains its historical rights status.

The four exact upstream modules named in `src/halveth_nova/workbench/_integrations/lagefaden/SOURCE_BINDINGS.json`
retain MIT under that directory's `LICENSE-MIT.txt`. This is an exception to the
original-material row above. The new bridge `run.mjs`,
workbench modules, tests and documentation are new HALVETH PIRL 2.0 material.
