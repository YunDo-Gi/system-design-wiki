# knot — URL shortener mock for ch04 rate limiter experiments

학습용 프로젝트. 자세한 설계는 `../../docs/specs/2026-05-24-rate-limiter-design.md`.

## 빠른 시작 (사이클 0)

```bash
cd experiments/knot
docker compose up -d redis
uv sync
uv run uvicorn app.main:app --reload
```

## Obsidian 사용자

Settings → Files & Links → **Excluded files**에 `experiments/`를 추가하세요. vault 인덱싱 부하 및 탐색기 오염을 막습니다.
