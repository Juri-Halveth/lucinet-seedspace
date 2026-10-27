"""Bounded public source acquisition. Never run on application startup."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
import hashlib
import json
import time

ROOT = Path(__file__).resolve().parent / "data"


def main():
    ROOT.mkdir(exist_ok=True)
    species, receipts = {}, []
    for key, cid, name, formula in [
        ("dmt", 6089, "DMT", "C12H16N2"),
        ("peroxide", 784, "Wasserstoffperoxid", "H2O2"),
        ("water", 962, "Wasser", "H2O"),
        ("oxygen", 977, "Sauerstoff", "O2"),
    ]:
        url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/JSON?record_type=2d"
        path = ROOT / f"pubchem-{cid}.json"
        if path.exists():
            raise FileExistsError(path)
        started = datetime.now(timezone.utc).isoformat()
        with urlopen(Request(url, headers={"User-Agent": "HALVETH-Molecular-Lineage/1.0 public-source-research"}), timeout=25) as response:
            raw = response.read(500_001)
            if len(raw) > 500_000 or response.status != 200:
                raise ValueError("SOURCE_LIMIT_OR_STATUS")
        parsed = json.loads(raw)["PC_Compounds"][0]
        assert parsed["id"]["id"]["cid"] == cid
        atoms, bonds, coords = parsed["atoms"], parsed["bonds"], parsed["coords"][0]
        conformer = coords["conformers"][0]
        symbols = {1: "H", 6: "C", 7: "N", 8: "O"}
        index = {aid: i for i, aid in enumerate(coords["aid"])}
        species[key] = {"id": key, "cid": cid, "name": name, "formula": formula,
            "atoms": [{"aid": aid, "element": symbols[element],
                       "x": conformer["x"][index[aid]], "y": conformer["y"][index[aid]]}
                      for aid, element in zip(atoms["aid"], atoms["element"])],
            "bonds": [{"a": a, "b": b, "order": order}
                      for a, b, order in zip(bonds["aid1"], bonds["aid2"], bonds["order"])]}
        path.write_bytes(raw)
        receipts.append({"id": f"pubchem-{cid}", "url": url, "file": path.name,
            "startedAt": started, "receivedAt": datetime.now(timezone.utc).isoformat(),
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "scope": "PubChem 2D connectivity for this CID; not a measured trajectory"})
        time.sleep(.25)
    sources = {"schema": "molecular-sources.v1", "species": species, "receipts": receipts,
        "reaction": {"id": "rhea-20309", "url": "https://www.rhea-db.org/rhea/20309",
            "secondSource": "https://iubmb.qmul.ac.uk/enzyme/EC1/11/1/6.html",
            "equation": "2 H2O2 = 2 H2O + O2", "enzymeClass": "EC 1.11.1.6",
            "sourceCheckedAt": "2026-10-27", "atomMapping": "ANALYST_SELECTED_NOT_EXPERIMENTALLY_TRACED",
            "kinetics": "UNBOUND; model steps and poses are illustrative"}}
    (ROOT / "sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"species": len(species), "atoms": {k: len(v["atoms"]) for k, v in species.items()}}))


if __name__ == "__main__":
    main()
