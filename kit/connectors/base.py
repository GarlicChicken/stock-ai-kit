"""외부 연동 공통 도구: 키(.env) 읽기 · 쓰기, HTTP 요청(재시도 · 호출 간격), 캐시 위치.

키는 키트 폴더의 `.env` 파일에만 저장된다(저장소에 올라가지 않음). 키 값은 화면에 끝 몇 글자만 보여 준다.
"""

import json
import os
import time
from pathlib import Path

from ..console import KitError
from ..paths import CACHE, ROOT

ENV_FILE = ROOT / ".env"

# 키 이름: (설명, 발급하는 곳, 그룹)
KEYS = {
    "DART_API_KEY": ("OpenDART 인증키 (공시 · 재무제표)", "https://opendart.fss.or.kr  > 인증키 신청", "dart"),
    "NAVER_HUB_CLIENT_ID": ("NAVER API HUB Client ID (뉴스 검색, 새 방식)", "네이버 클라우드 콘솔 > NAVER API HUB > Application", "news"),
    "NAVER_HUB_CLIENT_SECRET": ("NAVER API HUB Client Secret", "위와 같은 곳의 [인증 정보]", "news"),
    "NAVER_CLIENT_ID": ("네이버 개발자센터 Client ID (기존 방식, 2027-06-30까지)", "https://developers.naver.com", "news"),
    "NAVER_CLIENT_SECRET": ("네이버 개발자센터 Client Secret (기존 방식)", "https://developers.naver.com", "news"),
    "ECOS_API_KEY": ("한국은행 ECOS 인증키 (금리 · 환율 · 물가 등)", "https://ecos.bok.or.kr/api  > 인증키 신청", "ecos"),
    "KIS_APP_KEY": ("한국투자증권 앱키 (시세 · 분봉 · 수급 조회)", "https://apiportal.koreainvestment.com  > API 신청", "kis"),
    "KIS_APP_SECRET": ("한국투자증권 앱시크릿", "위와 같은 곳", "kis"),
    "KIS_ENV": ("한국투자증권 서버: mock(모의투자, 기본) 또는 real(실전 시세)", "직접 입력", "kis"),
    "KRX_AUTH_KEY": ("KRX 정보데이터시스템 OpenAPI 인증키 (일별 전 종목 시세)", "https://openapi.krx.co.kr  > API 인증키 신청 + 서비스별 이용 신청", "krx"),
    "KIWOOM_APP_KEY": ("키움증권 REST 앱키 (시세 조회)", "https://openapi.kiwoom.com  > API 신청", "kiwoom"),
    "KIWOOM_SECRET_KEY": ("키움증권 REST 시크릿키", "위와 같은 곳", "kiwoom"),
    "KIWOOM_ENV": ("키움증권 서버: mock(모의투자, 기본) 또는 real", "직접 입력", "kiwoom"),
}


# ---------------------------------------------------------------- .env

def read_env(path=None):
    """`.env`를 {이름: 값}으로 읽는다. 따옴표 · 주석 · 빈 줄을 처리한다."""
    path = Path(path) if path else ENV_FILE
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[name] = value
    return out


def get_key(name, required=True, default=None):
    """키 값을 읽는다. 환경변수가 먼저, 없으면 `.env`."""
    value = os.environ.get(name) or read_env().get(name) or default
    if required and not value:
        desc, where, _ = KEYS.get(name, ("", "", ""))
        raise KitError(
            f"{name}({desc})가 설정되어 있지 않습니다.\n"
            f"     발급: {where}\n"
            f"     설정: VS Code 터미널에서 직접 'uv run kit keys set {name}' 실행 (키는 AI에게 알려 주지 마세요)"
        )
    return value


def write_key(name, value, path=None):
    """`.env`에 키를 저장한다(다른 줄은 그대로 둔다)."""
    path = Path(path) if path else ENV_FILE
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.strip().split("=", 1)[0].strip() == name:
            lines[i] = f"{name}={value}"
            found = True
    if not found:
        lines.append(f"{name}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def mask(value):
    if not value:
        return ""
    return ("*" * 6) + value[-3:] if len(value) > 6 else "*" * len(value)


# ---------------------------------------------------------------- HTTP

_last_call = {}


def request(method, url, *, host_key=None, min_interval=0.0, retries=3, timeout=20, ok_status=(200,), **kwargs):
    """요청을 보내고 응답을 돌려준다.

    - 같은 출처(host_key)의 호출 사이를 min_interval초 이상 띄운다 (호출 한도 보호).
    - 429 · 5xx · 네트워크 오류는 2 · 4 · 8초 기다렸다가 다시 시도한다.
    """
    import requests

    key = host_key or url.split("/")[2]
    last_error = None
    for attempt in range(retries + 1):
        wait = min_interval - (time.monotonic() - _last_call.get(key, 0.0))
        if wait > 0:
            time.sleep(wait)
        _last_call[key] = time.monotonic()
        try:
            r = requests.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as e:
            last_error = f"{type(e).__name__}"
        else:
            if r.status_code in ok_status:
                return r
            last_error = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))
    raise KitError(f"요청이 실패했습니다 ({key}): {last_error}")


# ---------------------------------------------------------------- 캐시

def cache_dir(source):
    path = CACHE / "connectors" / source
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json_cache(path, max_age_sec):
    path = Path(path)
    if path.exists() and time.time() - path.stat().st_mtime < max_age_sec:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def write_json_cache(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
