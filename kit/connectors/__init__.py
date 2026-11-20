"""외부 연동 모음. research 스크립트에서 불러 쓴다 (전략 파일에서는 쓸 수 없음).

    from kit.connectors import dart, naver_news, ecos, kis, krx, world

| 모듈 | 가져오는 것 | 필요한 키 |
|---|---|---|
| dart | 공시 목록 · 기업 개황 · 재무제표 | DART_API_KEY |
| naver_news | 뉴스 검색 · 날짜별 기사 수 | NAVER_HUB_CLIENT_ID/SECRET (또는 기존 NAVER_CLIENT_ID/SECRET) |
| ecos | 금리 · 환율 · 물가 · 통화량 | ECOS_API_KEY (없으면 시험용 10건) |
| kis | 현재가 · 일봉 · 분봉 · 투자자별 매매동향 (조회만) | KIS_APP_KEY/SECRET, KIS_ENV |
| krx | 하루치 전 종목 공식 시세 | KRX_AUTH_KEY |
| world | 해외 지수 · 환율 · 원자재 · 미국 경제지표 | 필요 없음 |

키 설정: VS Code 터미널에서 직접 `uv run kit keys set <키 이름>` · 확인: `uv run kit keys test`
자세한 설명: docs/connectors.md
"""

GROUPS = {
    "dart": ("kit.connectors.dart", ["DART_API_KEY"]),
    "news": ("kit.connectors.naver_news", ["NAVER_HUB_CLIENT_ID", "NAVER_HUB_CLIENT_SECRET"]),
    "ecos": ("kit.connectors.ecos", ["ECOS_API_KEY"]),
    "kis": ("kit.connectors.kis", ["KIS_APP_KEY", "KIS_APP_SECRET"]),
    "krx": ("kit.connectors.krx", ["KRX_AUTH_KEY"]),
    "world": ("kit.connectors.world", []),
}
