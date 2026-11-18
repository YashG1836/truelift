"""Download the public randomised datasets the real-data check uses, and verify them.

    python scripts/get_data.py criteo hillstrom      # both (about 315 MB)
    python scripts/get_data.py hillstrom             # 4 MB

Each file goes to data/raw/ (not in git) and is kept only if its SHA-256 matches the one recorded
here, so everyone checks the model on exactly the same bytes. A file already present with the
right checksum is not downloaded again. Terms: Criteo's data is CC BY-NC-SA 4.0 (non-commercial);
Kevin Hillstrom published his e-mail test for anyone to analyse, without a stated licence.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DATA = {
    "criteo": {
        "url": "https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/criteo-research-uplift-v2.1.csv.gz",
        "path": "data/raw/criteo_uplift/criteo-research-uplift-v2.1.csv.gz",
        "sha256": "2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc",
        "bytes": 311_422_618,
    },
    "hillstrom": {
        "url": "http://www.minethatdata.com/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv",
        "path": "data/raw/hillstrom/Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv",
        "sha256": "0e5893329d8b93cefecc571777672028290ab69865718020c78c7284f291aece",
        "bytes": 3_964_977,
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(name: str) -> Path:
    spec = DATA[name]
    path = ROOT / spec["path"]
    if path.exists() and sha256(path) == spec["sha256"]:
        print(f"{name}: already here, checksum matches ({path.relative_to(ROOT)})")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    print(f"{name}: downloading {spec['bytes'] / 1e6:.0f} MB from {spec['url']}")
    req = urllib.request.Request(spec["url"], headers={"User-Agent": "truelift-get-data"})
    with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as out:
        while block := r.read(1 << 20):
            out.write(block)
    got = sha256(part)
    if got != spec["sha256"]:
        part.unlink()
        raise SystemExit(f"{name}: checksum {got} does not match the recorded {spec['sha256']}; file discarded")
    part.replace(path)
    print(f"{name}: saved to {path.relative_to(ROOT)}, checksum matches")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("datasets", nargs="+", choices=sorted(DATA))
    for name in ap.parse_args().datasets:
        fetch(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
