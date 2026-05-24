# knot Cycle 4 — 다차원 규칙 + 핫리로드 설계

- **문서 종류**: Sub-spec (cycle 4, full)
- **상위 spec**: `docs/specs/2026-05-24-rate-limiter-design.md`
- **작성일**: 2026-05-24
- **관련 위키**: [[rate-limiting]], [[ch04-rate-limiter]]
- **상태**: 작성 직후

## 0. 목적과 학습 의도

cycle 3까지로 knot의 두 엔드포인트가 각자 적합한 알고리즘으로 운영 중. cycle 4는 **운영 측면**으로 전환 — 같은 알고리즘 위에서 **정책의 표현력을 확장**:

1. **다차원 규칙** — `endpoint`뿐 아니라 `user_tier` 등 추가 차원에 따라 정책 차등 (free 분당 5, premium 분당 50)
2. **핫리로드** — yaml 변경 시 앱 재시작 없이 정책 즉시 반영

ch04 §"기본 아키텍처"의 두 메시지를 깊이 적용:
- "규칙은 데이터로 외부화 — 코드 배포 없이 정책 변경"
- "워커가 정기적으로 캐시로 로드" (cycle 0은 시작 시 1회만 로드한 상태였음)

cycle 0에서 깐 Lyft envoy 포맷의 **본격적 확장** + cycle 2에서 부수 도입한 `KNOT_RULES_PATH` env override의 활용처.

### Lyft envoy 포맷의 다차원 표현

ch04에 인용된 Lyft 포맷은 사실 **중첩 descriptors**로 다차원 매칭을 표현:

```yaml
domain: knot
descriptors:
  - key: endpoint
    value: shorten
    descriptors:                  # ← 중첩 (cycle 0은 사용 안 함)
      - key: user_tier
        value: free
        rate_limit: { algorithm: sliding_window_log, unit: minute, requests_per_unit: 5 }
      - key: user_tier
        value: premium
        rate_limit: { algorithm: sliding_window_log, unit: minute, requests_per_unit: 50 }
    rate_limit: { algorithm: sliding_window_log, unit: minute, requests_per_unit: 10 }   # default fallback
```

매칭 우선순위: **가장 구체적인 매치 우선** (`endpoint+user_tier` > `endpoint`만 > 없음).

## 1. user_tier 차원 도입

### 1-1. 클라이언트 인터페이스

클라이언트가 `X-User-Tier` 헤더로 자기 티어 선언:

```
X-User-Tier: free       # 또는 premium / enterprise
```

**학습용 단순화**: 헤더 값을 그대로 신뢰. **실서비스에서는 절대 그러면 안 됨** — API key DB lookup으로 server-side 결정해야 함 (회고 노트에 명시).

미선언 시: `default` (또는 매칭되는 fallback rule 사용).

### 1-2. 정책 예시 (cycle 4 적용 후 rules.yaml)

```yaml
domain: knot
descriptors:
  - key: endpoint
    value: shorten
    descriptors:
      - key: user_tier
        value: premium
        rate_limit: { algorithm: sliding_window_log, unit: minute, requests_per_unit: 50 }
      - key: user_tier
        value: enterprise
        rate_limit: { algorithm: sliding_window_log, unit: minute, requests_per_unit: 500 }
    rate_limit: { algorithm: sliding_window_log, unit: minute, requests_per_unit: 10 }  # default = free
  - key: endpoint
    value: redirect
    rate_limit: { algorithm: token_bucket, unit: second, requests_per_unit: 50, burst: 100 }
```

`shorten`이 다차원 정책. `redirect`는 단차원 유지 (모든 사용자 같은 정책 — 익명 IP가 식별자라 tier 의미 약함).

## 2. Rules 데이터 모델 확장

### 2-1. 매칭 입력

```python
# middleware가 만드는 descriptor entries (순서 의미 X)
entries = [
    ("endpoint", "shorten"),
    ("user_tier", "premium"),
]
```

### 2-2. 새 lookup 알고리즘

```
lookup(domain, entries) -> Rule | None:
  현재 노드 = root (domain)
  best_match = None
  best_specificity = -1

  DFS:
    각 child descriptor (key, value)가 entries 중에 있으면:
      - 그 child가 rate_limit 있으면: 후보 (specificity = depth)
      - 그 child의 nested descriptors도 같은 방식으로 탐색
    최종: 가장 큰 specificity (= 가장 깊은 매치)를 반환
```

엔트리 순서 무관, **가장 구체적인 매치만 채택**. 동률 specificity가 여러 개면 의도된 yaml 순서 우선 (deterministic).

### 2-3. 새 dataclass

```python
@dataclass
class RuleNode:
    """yaml의 descriptor 노드 1개."""
    rate_limit: Rule | None = None       # 이 노드에서 매치 시 적용
    children: dict[tuple[str, str], RuleNode] = field(default_factory=dict)

@dataclass
class Rules:
    domain: str
    root: RuleNode

    def lookup(self, entries: list[tuple[str, str]]) -> Rule | None:
        return self._dfs(self.root, set(entries), depth=0)[0]

    def _dfs(self, node, entries_set, depth):
        best = (node.rate_limit, depth) if node.rate_limit else (None, -1)
        for (k, v), child in node.children.items():
            if (k, v) in entries_set:
                cand = self._dfs(child, entries_set, depth + 1)
                if cand[1] > best[1]:
                    best = cand
        return best
```

cycle 0의 `_index` dict 평면 매핑은 deprecated. 트리 구조로 교체.

## 3. 핫리로드 — `watchdog` 파일 watcher

### 3-1. 메커니즘

```python
# app/rules.py
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class _Reloader(FileSystemEventHandler):
    def __init__(self, path: Path, on_reload):
        self.path = path.resolve()
        self.on_reload = on_reload

    def on_modified(self, event):
        if Path(event.src_path).resolve() == self.path:
            self.on_reload()


def start_watcher(path: Path, app):
    def reload():
        try:
            app.state.rules = load_rules(path)
            logger.info("rules reloaded from %s", path)
        except Exception as e:
            logger.exception("rules reload failed — keeping previous rules")

    obs = Observer()
    obs.schedule(_Reloader(path, reload), str(path.parent), recursive=False)
    obs.start()
    return obs
```

### 3-2. 시작 시 watcher 등록

`app/main.py` lifespan 확장:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rules = load_rules(RULES_PATH)
    observer = start_watcher(RULES_PATH, app)
    try:
        yield
    finally:
        observer.stop()
        observer.join()
        await close_redis()
```

### 3-3. atomic swap

reload는 **새 Rules 객체를 만들어 통째로 교체** — partial update 없음. 실패 시 이전 객체 유지. 미들웨어가 `app.state.rules`를 매 요청 읽으므로 다음 요청부터 새 정책 즉시 반영.

### 3-4. watcher의 잘 알려진 함정

- **에디터 atomic save** — vim 등은 `tmp → rename` 패턴. `on_modified` 외 `on_moved`도 핸들. plan에서 처리.
- **macOS의 stat 잘림** — watchdog가 잘 처리하지만 폴더 monitoring으로 시작.
- **로딩 중 partial 파일 읽음** — 짧은 retry (50ms × 3) 또는 yaml.safe_load 실패 시 무시.

## 4. Middleware 확장

```python
# app/middleware.py — dispatch() 안에서
identity = ...    # cycle 0 동일
user_tier = request.headers.get("x-user-tier", "default")

entries = [
    ("endpoint", endpoint_name),
    ("user_tier", user_tier),
]
rule = rules.lookup(entries)
```

`lookup`이 entries 중 매치되는 것만 사용 → user_tier 미선언이어도 endpoint-only 매치로 fallback.

## 5. 테스트 전략

### Unit — Rules 트리 매칭 (`tests/unit/test_rules_multidim.py`) 5개

| 테스트 | 검증 |
|---|---|
| `test_endpoint_only_match` | user_tier 없어도 endpoint default rule 매치 |
| `test_endpoint_plus_tier_match` | endpoint+tier 둘 다 매치되면 더 구체적인 (tier) rule 선택 |
| `test_specificity_priority` | depth 큰 매치가 항상 우선 |
| `test_unknown_tier_fallback` | 미정의 tier 보내면 endpoint default로 fallback |
| `test_unknown_endpoint_returns_none` | 정의되지 않은 endpoint는 None |

### Unit — Hot reload (`tests/unit/test_rules_reload.py`) 2개

| 테스트 | 검증 |
|---|---|
| `test_reload_picks_up_new_rule` | 파일 수정 → watcher trigger → app.state.rules 갱신 |
| `test_reload_failure_keeps_previous` | 잘못된 yaml로 수정 → 이전 rules 유지 (rollback 효과) |

watchdog는 실제 파일 시스템 이벤트 필요 — `tmp_path` 사용. 약간 시간 대기(100~500ms) 필요.

### Integration (`tests/integration/test_multidim_e2e.py`) 3개

| 테스트 | 검증 |
|---|---|
| `test_free_tier_limited_at_10` | `X-User-Tier: free`로 11회 POST → 11번째 429 |
| `test_premium_tier_limited_at_50` | `X-User-Tier: premium`로 51회 POST → 51번째 429 |
| `test_default_tier_uses_endpoint_default` | tier 헤더 없이 11회 → 11번째 429 (= free 정책) |

### 기존 테스트 영향

- `tests/integration/test_middleware_e2e.py`의 `test_shorten_returns_200_with_rate_limit_headers` — 헤더 없이 호출이므로 endpoint default rule 적용 → 기대값 변경 없음 (`limit=10, remaining=9`)
- 다른 cycle 0~3 테스트도 모두 유지

## 6. 결정 이력 (Decision Log)

| # | 결정 | 선택 | 이유 |
|---|---|---|---|
| 1 | 2번째 차원 | `user_tier` (free/premium/enterprise) | ch04 §"rate limit 사용 케이스" SaaS 차등이 가장 직관. cycle 5(hard/soft)와 결합 좋음 |
| 2 | 매칭 포맷 | Lyft envoy 중첩 descriptors | ch04 인용 포맷의 자연 확장. 트리 yaml로 정책 가시성 ↑ |
| 3 | 매칭 우선순위 | 가장 구체적인 매치 우선 (depth 큰) | Lyft envoy 동작과 동일. fallback이 자연스러움 |
| 4 | 핫리로드 | `watchdog` 파일 watcher | 즉시 반영 시연 ↑. Python ecosystem 표준 |
| 5 | reload 원자성 | 새 Rules 객체 통째 교체 (atomic swap) | partial reload 함정 회피. 실패 시 이전 유지 |
| 6 | user_tier 신뢰 모델 | 헤더 값 그대로 신뢰 (학습용) | 실서비스는 API key DB lookup 필수. 회고에 명시 |
| 7 | tier 미선언 처리 | `default` 값 사용 → endpoint default rule 매치 | 명시 안 한 사용자 차단 방지 |
| 8 | watcher 함정 | edit-rename 패턴은 `on_moved` 핸들, partial yaml 실패 시 무시 | 에디터 호환성 |
| 9 | redirect 다차원화 여부 | 단차원 유지 (모든 사용자 동일) | redirect는 익명 IP 식별자라 tier 의미 약함 |
| 10 | watcher 시작 위치 | FastAPI lifespan | shutdown 시 cleanup 보장 |
| 11 | 트리 자료구조 | dataclass RuleNode (children: dict) | DFS 단순, 타입 명확 |
| 12 | k6 시나리오 | **없음** | 운영 측면 사이클 — 테스트가 본질, 부하 그래프는 학습 가치 약함 |

## 7. 변경 파일

```
신규:
  experiments/knot/tests/unit/test_rules_multidim.py
  experiments/knot/tests/unit/test_rules_reload.py
  experiments/knot/tests/integration/test_multidim_e2e.py

변경:
  experiments/knot/app/rules.py                          # RuleNode/Rules 트리, 매칭 알고리즘
  experiments/knot/app/middleware.py                     # user_tier 헤더 추출, entries 구성
  experiments/knot/app/main.py                           # lifespan에 watcher 시작/정지
  experiments/knot/pyproject.toml                        # watchdog 의존성
  experiments/knot/rules.yaml                            # shorten에 user_tier 중첩 descriptors
  experiments/knot/tests/unit/test_rules.py              # 기존 평면 lookup 테스트 → 새 인터페이스 적용
  wiki/projects/knot.md                                  # ## Cycle 4 섹션
  docs/specs/2026-05-24-rate-limiter-design.md          # §7 cycle 4 status: todo → done
  log.md                                                 # cycle 4 항목
```

**기존 평면 `Rules._index` 제거** — `RuleNode` 트리로 완전 교체. 기존 `test_rules.py`도 갱신.

## 8. 미해결 / 후속

- **인증 없이 tier 신뢰**: 학습용 한정. cycle 7 회고에 "실서비스에서는 API key → tier resolution이 표준"으로 명시
- **watcher 부하**: yaml 변경 빈도 낮아 거의 0이지만 대용량 yaml + 잦은 변경 시 throttle 필요할 수 있음 (cycle 4 스코프 외)
- **다중 노드 동기화**: 노드마다 자체 watcher → yaml만 공유되면 동기. 실제 분산 환경에선 config service(etcd/Consul) 권장. cycle 7 회고
