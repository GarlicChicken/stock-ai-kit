"""네이버 뉴스 검색.

- 새 방식: NAVER API HUB (네이버 클라우드 콘솔에서 발급, 2026-06부터)
  GET https://naverapihub.apigw.ntruss.com/search/v1/news
  헤더 X-NCP-APIGW-API-KEY-ID / X-NCP-APIGW-API-KEY, 하루 25,000회
- 기존 방식: 네이버 개발자센터 키 (openapi.naver.com, 헤더 X-Naver-Client-Id / Secret). 2027-06-30까지.
  두 방식의 키는 서로 바꿔 쓸 수 없다. 새 방식 키가 있으면 그것을 먼저 쓴다.
- 한 검색어로 최근 기사 최대 1,000개까지 받을 수 있다 (display 100 × start 1~1000).
- 이용 약관(검색 결과 이용 범위)은 네이버 공지를 따른다. 기사 본문 수집 · 재배포 용도로 쓰지 않는다.

설정: VS Code 터미널에서 직접 `uv run kit keys set NAVER_HUB_CLIENT_ID` · `NAVER_HUB_CLIENT_SECRET`
"""

import html
import re
from email.utils import parsedate_to_datetime

import pandas as pd

from ..console import KitError
from .base import get_key, request

HUB_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
OLD_URL = "https://openapi.naver.com/v1/search/news.json"


def _endpoint():
    hub_id, hub_secret = get_key("NAVER_HUB_CLIENT_ID", False), get_key("NAVER_HUB_CLIENT_SECRET", False)
    if hub_id and hub_secret:
        return HUB_URL, {"X-NCP-APIGW-API-KEY-ID": hub_id, "X-NCP-APIGW-API-KEY": hub_secret}
    old_id, old_secret = get_key("NAVER_CLIENT_ID", False), get_key("NAVER_CLIENT_SECRET", False)
    if old_id and old_secret:
        return OLD_URL, {"X-Naver-Client-Id": old_id, "X-Naver-Client-Secret": old_secret}
    get_key("NAVER_HUB_CLIENT_ID")  # 없다는 안내를 띄운다
    raise KitError("네이버 검색 키가 없습니다.")


def _clean(text):
    return html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def _kst(text):
    try:
        ts = pd.Timestamp(parsedate_to_datetime(text))
        return ts.tz_convert("Asia/Seoul").tz_localize(None)
    except (TypeError, ValueError):
        return pd.NaT


def search(query, count=100, sort="date"):
    """뉴스 검색. sort: "date"(최신순, 기본) · "sim"(정확도순). count: 최대 1,000.

    돌려주는 열: published(한국 시각), title, description, originallink, link, query
    """
    url, headers = _endpoint()
    count = max(1, min(int(count), 1000))
    items, start = [], 1
    while len(items) < count and start <= 1000:
        display = min(100, count - len(items), 1001 - start)
        r = request("GET", url, headers=headers, host_key="naver-news", min_interval=0.12,
                    params={"query": query, "display": display, "start": start, "sort": sort})
        got = r.json().get("items", [])
        if not got:
            break
        items.extend(got)
        start += len(got)
        if len(got) < display:
            break
    df = pd.DataFrame({
        "published": [_kst(i.get("pubDate")) for i in items],
        "title": [_clean(i.get("title")) for i in items],
        "description": [_clean(i.get("description")) for i in items],
        "originallink": [i.get("originallink", "") for i in items],
        "link": [i.get("link", "") for i in items],
    })
    df["query"] = query
    return df


def daily_counts(query, count=1000):
    """검색어의 날짜별 기사 수 (최근 기사 최대 1,000개 기준). 관심도 추이를 볼 때 쓴다."""
    df = search(query, count=count, sort="date")
    if df.empty:
        return pd.DataFrame(columns=["date", "articles"])
    out = df.groupby(df["published"].dt.normalize()).size().rename("articles").reset_index()
    return out.rename(columns={"published": "date"}).sort_values("date").reset_index(drop=True)


def ping():
    """키가 맞는지 확인 (기사 1개만 받는다)."""
    df = search("코스피", count=1)
    return f"{len(df)}건 받음 ({'API HUB' if get_key('NAVER_HUB_CLIENT_ID', False) else '개발자센터'} 방식)"
