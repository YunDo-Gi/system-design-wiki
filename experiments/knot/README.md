# knot — URL shortener mock for ch04 rate limiter experiments

학습용 프로젝트. ch04의 모든 핵심 개념과 추가 토픽을 직접 구현·검증한다.

- **설계 문서**: `../../docs/specs/2026-05-24-rate-limiter-design.md`
- **학습 노트 (사이클별 ch04 매핑·결정 사유·발견된 함정)**: `../../wiki/projects/knot.md` — Obsidian에서 `[[knot]]`으로 열림

## 빠른 시작

```bash
cd experiments/knot
docker compose up -d redis
uv sync
uv run uvicorn app.main:app --reload
```

별도 터미널에서:

```bash
curl -X POST localhost:8000/shorten \
  -H "content-type: application/json" \
  -H "x-api-key: my-key" \
  -d '{"url": "https://example.com"}'
# {"code": "abc123"}

curl -i localhost:8000/abc123
# HTTP/1.1 302
# X-Ratelimit-Limit: 50
# X-Ratelimit-Remaining: 50
# Location: https://example.com
```

## 테스트

```bash
docker compose up -d redis
REDIS_AVAILABLE=1 uv run pytest -v
```

## 디렉터리

- `app/` — FastAPI 앱, 미들웨어, 규칙 로더, limiter plug-in
- `app/limiter/` — 알고리즘 모듈 (cycle 0: always_allow만)
- `rules.yaml` — Lyft envoy 포맷 규칙
- `tests/unit/`, `tests/integration/`
- `load/` — k6 시나리오 (cycle 1+에서 추가)
- `reports/` — 부하 시험 리포트 (cycle 1+에서 추가)

## Obsidian 사용자

Settings → Files & Links → **Excluded files**에 `experiments/`를 추가하세요. `.venv/`·`__pycache__/` 등이 vault에 노출되어 인덱싱이 느려지는 것을 막습니다.
