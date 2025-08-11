import os, json, gzip, io, re, sys, time, socket
from pathlib import Path
from urllib.parse import urljoin
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import tsplib95

BASE_DIR = Path(__file__).resolve().parents[1]
# Pages 소스가 docs/면 다음 줄을 "docs/data"로 바꾸세요.
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT = DATA_DIR / "tsplib.json"

TSPLIB_BASE = "https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/"
TSP_DIR = urljoin(TSPLIB_BASE, "tsp/")

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "tsplib95-crawler/1.1"})
    retry = Retry(
        total=5,
        connect=5, read=5,
        backoff_factor=0.6,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods={"GET", "HEAD"},
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    # 프록시를 쓰는 환경이라면, 환경변수 HTTP(S)_PROXY를 자동 인식
    return s

session = make_session()

def list_tsp_gz():
    r = session.get(TSP_DIR, timeout=30)
    r.raise_for_status()
    return sorted(set(re.findall(r'href="([A-Za-z0-9_.-]+\.tsp\.gz)"', r.text)))

def url_exists_via_get(url: str) -> bool:
    # 일부 서버는 HEAD를 거부할 수 있으므로, GET + stream으로 가볍게 확인
    try:
        r = session.get(url, timeout=20, stream=True)
        return r.status_code == 200
    except requests.RequestException:
        return False

def has_opt_tour(base_name: str) -> bool:
    url = urljoin(TSP_DIR, f"{base_name}.opt.tour.gz")
    return url_exists_via_get(url)

def fetch(url: str) -> bytes:
    r = session.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def parse_tsp_gz(buf: bytes):
    with gzip.GzipFile(fileobj=io.BytesIO(buf)) as f:
        raw = f.read().decode("utf-8", errors="replace")
    prob = tsplib95.parse(raw)
    name = getattr(prob, "name", "") or ""
    return {
        "name": name,
        "type": getattr(prob, "type", "") or "",
        "dimension": int(getattr(prob, "dimension", 0) or 0),
        "edge_weight_type": getattr(prob, "edge_weight_type", "") or "",
        "edge_weight_format": getattr(prob, "edge_weight_format", "") or "",
        "symmetric": (getattr(prob, "type", "") == "TSP") and (getattr(prob, "edge_weight_format", "") != "FULL_MATRIX"),
    }

def main():
    # 네트워크 기본 확인(옵션)
    try:
        socket.gethostbyname("comopt.ifi.uni-heidelberg.de")
    except socket.gaierror as e:
        print(f"[fatal] DNS 실패: {e}. 네트워크/프록시 설정을 확인하세요.", file=sys.stderr)
        sys.exit(2)

    items = []
    try:
        tsp_files = list_tsp_gz()
    except requests.RequestException as e:
        print(f"[fatal] 디렉터리 목록 가져오기 실패: {e}", file=sys.stderr)
        sys.exit(2)

    for fname in tsp_files:
        base = fname[:-7]  # ".tsp.gz" 제거
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
        except requests.ConnectionError as e:
            print(f"[warn] 연결 오류로 스킵 {fname}: {e}", file=sys.stderr)
            continue
        except requests.Timeout as e:
            print(f"[warn] 타임아웃으로 스킵 {fname}: {e}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"[warn] 파싱 실패 {fname}: {e}", file=sys.stderr)
            continue

        time.sleep(0.05)  # 예의상 천천히

    items.sort(key=lambda d: (str(d.get("name")).lower(), d.get("dimension") or 0))
    OUT.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    print(f"[ok] wrote {OUT} ({len(items)} items)")

if __name__ == "__main__":
    main()
