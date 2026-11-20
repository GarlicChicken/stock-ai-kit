# data

표준 데이터가 들어가는 곳입니다. 저장소에는 올리지 않습니다.

- `prices.parquet`: 일별 시세 (그날 실제 가격 · 거래량 · 거래대금 · 상장주식수)
- `universe.csv`: 매달 마지막 거래일의 시가총액 상위 200종목 (다음 달 투자 대상)
- `stocks.csv`: 종목 이름 · 시장 · 첫 거래일 · 마지막 거래일 · 상장폐지 여부 (엑셀로 열 수 있음)
- `index.csv`: 코스피 · 코스닥 지수 종가
- `manifest.json`: 만든 날 · 기간 · 데이터 지문
- `minute/`: 분봉 (`uv run kit data minute <코드>`)

채우는 방법: `uv run kit data unpack <zip>` 또는 `uv run kit data download`.
이 폴더의 파일은 직접 고치지 않습니다. 개인 연구용 데이터는 `--data research/<폴더>`로 따로 받습니다.
