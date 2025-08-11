# scripts/build_tsplib_json.py
import os, json, gzip, io, re, sys, time
from pathlib import Path
from urllib.parse import urljoin
import requests
import tsplib95

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"         # Pages 소스가 docs/면 "docs/data"로 바꾸세요
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT = DATA_DIR / "tsplib.json"

TSPLIB_BASE = "http://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/"
TSP_DIR = urljoin(TSPLIB_BASE, "tsp/")

session = requests.Session()
session.headers.update({"User-Agent": "tsplib95-crawler/1.0"})

def list_tsp_gz():
    r = session.get(TSP_DIR, timeout=30)
    r.raise_for_status()
    return sorted(set(re.findall(r'href="([A-Za-z0-9_.-]+\\.tsp\\.gz)"', r.text)))

def has_opt_tour(base_name: str) -> bool:
    url = urljoin(TSP_DIR, f"{base_name}.opt.tour.gz")
    h = session.head(url, timeout=20, allow_redirects=True)
    return h.ok

def fetch(url: str) -> bytes:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def parse_tsp_gz(buf: bytes):
    with gzip.GzipFile(fileobj=io.BytesIO(buf)) as f:
        raw = f.read().decode("utf-8", errors="replace")
    prob = tsplib95.parse(raw)
    name = getattr(prob, "name", None)
    ptype = getattr(prob, "type", None)
    dim = getattr(prob, "dimension", None)
    ewt = getattr(prob, "edge_weight_type", None)
    ewf = getattr(prob, "edge_weight_format", None)
    symmetric = (ptype == "TSP") and (getattr(prob, "edge_weight_format", "") != "FULL_MATRIX")
    return {
        "name": name or "",
        "type": ptype or "",
        "dimension": int(dim) if dim is not None else None,
        "edge_weight_type": ewt or "",
        "edge_weight_format": ewf or "",
        "symmetric": bool(symmetric),
    }

def main():
    items = []
    for fname in list_tsp_gz():
        base = fname[:-7]  # drop ".tsp.gz"
        tsp_url_gz = urljoin(TSP_DIR, fname)
        try:
            buf = fetch(tsp_url_gz)
            meta = parse_tsp_gz(buf)
            if not meta.get("dimension"):
                continue
            meta.update({
                "has_opt_tour": has_opt_tour(base),
                "files": {
                    "tsp_gz": f"{TSP_DIR}{base}.tsp.gz",
                    "opt_tour_gz": f"{TSP_DIR}{base}.opt.tour.gz",
                },
            })
            items.append(meta)
        except Exception as e:
            print(f"[warn] skip {fname}: {e}", file=sys.stderr)
        time.sleep(0.05)  # polite delay

    items.sort(key=lambda d: (str(d.get("name")).lower(), d.get("dimension") or 0))
    OUT.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    print(f"[ok] wrote {OUT} ({len(items)} items)")

if __name__ == "__main__":
    main()
