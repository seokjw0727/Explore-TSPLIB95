# scripts/build_tsplib_json.py
import os, json, gzip, io, re, sys, time
from pathlib import Path
from urllib.parse import urljoin
import requests

# pip deps: requests tsplib95
import tsplib95

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT = DATA_DIR / "tsplib.json"

TSPLIB_BASE = "https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/"
TSP_DIR = urljoin(TSPLIB_BASE, "tsp/")

session = requests.Session()
session.headers.update({"User-Agent": "tsplib95-crawler/1.0"})

def list_tsp_gz():
    """디렉터리 인덱스 HTML에서 *.tsp.gz 목록 추출"""
    r = session.get(TSP_DIR, timeout=30)
    r.raise_for_status()
    # 간단한 정규식으로 파일명만 추출
    files = set(re.findall(r'href="([A-Za-z0-9_.-]+\.tsp\.gz)"', r.text))
    return sorted(files)

def has_opt_tour(base_name: str) -> bool:
    # opt.tour.gz 존재 여부 HEAD체크
    url = urljoin(TSP_DIR, f"{base_name}.opt.tour.gz")
    h = session.head(url, timeout=20, allow_redirects=True)
    return h.ok

def fetch(url: str) -> bytes:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def parse_tsp_gz(content: bytes):
    with gzip.GzipFile(fileobj=io.BytesIO(content)) as f:
        raw = f.read().decode("utf-8", errors="replace")
    # tsplib95는 파일 경로가 있어야 편하므로 임시 메모리 파일 흉내
    # 하지만 load problem은 파일경로/파일객체 둘 다 가능하므로 문자열 파서 사용
    problem = tsplib95.parse(raw)
    # 안전하게 속성 추출
    name = getattr(problem, "name", None)
    ptype = getattr(problem, "type", None)
    dim = getattr(problem, "dimension", None)
    ewt = getattr(problem, "edge_weight_type", None)
    ewf = getattr(problem, "edge_weight_format", None)
    symmetric = (ptype == "TSP") and (getattr(problem, "edge_weight_format", "") != "FULL_MATRIX")
    return {
        "name": name,
        "type": ptype,
        "dimension": int(dim) if dim is not None else None,
        "edge_weight_type": ewt,
        "edge_weight_format": ewf,
        "symmetric": bool(symmetric),
    }

def main():
    items = []
    tsp_files = list_tsp_gz()
    for fname in tsp_files:
        base = fname[:-7]  # remove ".tsp.gz"
        tsp_url_gz = urljoin(TSP_DIR, fname)
        try:
            buf = fetch(tsp_url_gz)
            meta = parse_tsp_gz(buf)
            # name이 파일명과 다를 수 있어도 name을 우선
            name = meta.get("name") or base
            meta.update({
                "has_opt_tour": has_opt_tour(base),
                "files": {
                    "base": base,
                    "tsp_gz": f"{TSP_DIR}{base}.tsp.gz",
                    "opt_tour_gz": f"{TSP_DIR}{base}.opt.tour.gz"
                }
            })
            # 이름/차원 없으면 스킵
            if not meta.get("dimension"):
                continue
            items.append(meta)
        except Exception as e:
            print(f"[warn] skip {fname}: {e}", file=sys.stderr)
            continue

        # 서버 예의상 잠깐 쉼
        time.sleep(0.05)

    # 정렬: 이름 → 차원
    items.sort(key=lambda d: (str(d.get("name")).lower(), d.get("dimension") or 0))

    OUT.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    print(f"[ok] wrote {OUT} ({len(items)} items)")

if __name__ == "__main__":
    main()
