"""예시: 종목 · 테마 검색어의 날짜별 기사 수(관심도)와 주가를 나란히 보기 (네이버 뉴스 검색)

필요한 키: NAVER_HUB_CLIENT_ID · NAVER_HUB_CLIENT_SECRET (또는 기존 NAVER_CLIENT_ID · NAVER_CLIENT_SECRET)
실행: uv run python research/examples/news_buzz.py --query "SK하이닉스" --code 000660

- 검색어 하나로 최근 기사 최대 1,000개까지만 받을 수 있다 (오래된 기간은 볼 수 없음).
- 기사가 늘 많은 대형주는 기사 수만으로 차이가 나기 쉽다. 같은 종목의 '평소 대비 몇 배'로 본다.
- 기사 시각은 한국 시각. 15:30 이후 기사는 다음 거래일 결정에 쓴다 (kit.lab.calendar.effective_day).
- 최근 기사와 맞춰 보므로 주가는 표준 데이터 대신 그 종목의 최근 일봉(FinanceDataReader)을 받아 쓴다.
"""

import argparse
from pathlib import Path

import pandas as pd

from kit import sources
from kit.connectors import naver_news
from kit.lab.calendar import effective_day

ap = argparse.ArgumentParser()
ap.add_argument("--query", default="SK하이닉스")
ap.add_argument("--code", default="000660")
ap.add_argument("--count", type=int, default=1000)
args = ap.parse_args()

news = naver_news.search(args.query, count=args.count, sort="date")
start = (pd.Timestamp(news["published"].min()) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
px = sources.get_daily(args.code, start).set_index("date")
days = pd.DatetimeIndex(px.index)
news["decide_day"] = [effective_day(days, t) for t in news["published"]]
daily = news.dropna(subset=["decide_day"]).groupby("decide_day").size().rename("articles")
table = pd.DataFrame({"articles": daily})
table["평소 대비(20일)"] = (table["articles"] / table["articles"].rolling(20, min_periods=5).mean().shift(1)).round(2)
table["종가"] = px["close"].reindex(table.index)
out = Path("research/outputs")
out.mkdir(parents=True, exist_ok=True)
table.to_csv(out / f"news_buzz_{args.code}.csv", encoding="utf-8-sig")
print(table.tail(15).to_string())
print(f"\n기사 {len(news)}건 ({news['published'].min()} ~ {news['published'].max()}) -> {out / f'news_buzz_{args.code}.csv'}")
