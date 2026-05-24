# knot Cycle 4 — 다차원 규칙 + 핫리로드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Lyft envoy 중첩 descriptors 포맷으로 다차원 규칙 매칭 + `watchdog` 파일 watcher로 yaml 핫리로드. `shorten`이 user_tier(free/premium/enterprise)에 따라 차등 정책. 알고리즘 변경 없음, **운영 측면 사이클**.

**Architecture:** `RuleNode` 트리 + DFS 매칭 (specificity 우선). FastAPI lifespan에서 watchdog Observer 시작/정지. 미들웨어가 `X-User-Tier` 헤더 추출하여 entries 구성. atomic swap 리로드.

**Spec:** `docs/specs/2026-05-24-knot-cycle-4-multi-dim-rules-design.md` (결정 이력 12개).

**Scope (7 task)**:
1. watchdog 의존성 + 데이터 모델(RuleNode/Rules) 리팩터 + 기존 unit 갱신 (TDD)
2. 다차원 매칭 unit 5개 (TDD)
3. 핫리로드 unit 2개 (TDD) + 실제 reload 구현
4. Middleware에 user_tier 추출 + e2e 갱신
5. lifespan에 watcher start/stop
6. rules.yaml 다차원으로 확장 + integration 3개
7. wiki cycle 4 + spec status + log + push + PR

---

## File Structure

```
신규:
  tests/unit/test_rules_multidim.py
  tests/unit/test_rules_reload.py
  tests/integration/test_multidim_e2e.py

변경:
  pyproject.toml                   # watchdog
  app/rules.py                     # RuleNode 트리, DFS 매칭, reload watcher
  app/middleware.py                # user_tier 추출, entries
  app/main.py                      # lifespan watcher 시작/정지
  rules.yaml                       # shorten에 중첩 descriptors
  tests/unit/test_rules.py         # 새 인터페이스로 갱신 (lookup → entries 리스트)
```

---

## Task 1: 데이터 모델 리팩터 + watchdog 의존성

**Files:**
- Modify: `experiments/knot/pyproject.toml` (watchdog 추가)
- Modify: `experiments/knot/app/rules.py` (RuleNode/Rules 트리 + lookup(entries))
- Modify: `experiments/knot/tests/unit/test_rules.py` (새 인터페이스 적용)

기존 `test_rules.py`는 평면 `_index` 기반 — 새 트리 인터페이스로 갱신 필요. cycle 4 후 매우 다른 lookup signature.

- [ ] **Step 1: pyproject.toml dev deps에 watchdog 추가**

```toml
dev = [
    ...
    "watchdog>=4.0",
    ...
]
```

`uv sync` 실행.

- [ ] **Step 2: 기존 `test_rules.py` 두 테스트 갱신** (TDD red)

기존 `test_load_rules_parses_descriptors`와 `test_lookup_missing_returns_none`를 새 인터페이스에 맞게 수정:

```python
# experiments/knot/tests/unit/test_rules.py
import textwrap

import pytest

from app.limiter.base import Rule
from app.rules import Rules, load_rules


def test_load_rules_parses_descriptors(tmp_path):
    yaml_text = textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            rate_limit:
              algorithm: always_allow
              unit: minute
              requests_per_unit: 10
          - key: endpoint
            value: redirect
            rate_limit:
              algorithm: always_allow
              unit: second
              requests_per_unit: 50
              burst: 100
              mode: soft
    """)
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(yaml_text)

    rules = load_rules(yaml_file)

    assert rules.domain == "knot"

    shorten = rules.lookup([("endpoint", "shorten")])
    assert shorten == Rule(algorithm="always_allow", unit="minute", requests_per_unit=10)

    redirect = rules.lookup([("endpoint", "redirect")])
    assert redirect == Rule(
        algorithm="always_allow",
        unit="second",
        requests_per_unit=50,
        burst=100,
        mode="soft",
    )


def test_lookup_missing_returns_none(tmp_path):
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text("domain: knot\ndescriptors: []\n")
    rules = load_rules(yaml_file)
    assert rules.lookup([("endpoint", "nonexistent")]) is None
```

- [ ] **Step 3: 실패 확인**

Run: `cd experiments/knot && uv run pytest tests/unit/test_rules.py -v`
Expected: AttributeError 또는 TypeError (기존 평면 `_index`와 새 `entries` 리스트 시그니처 충돌).

- [ ] **Step 4: app/rules.py 트리로 교체**

```python
# experiments/knot/app/rules.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.limiter.base import Rule

logger = logging.getLogger(__name__)


@dataclass
class RuleNode:
    rate_limit: Rule | None = None
    children: dict[tuple[str, str], "RuleNode"] = field(default_factory=dict)


@dataclass
class Rules:
    domain: str
    root: RuleNode = field(default_factory=RuleNode)

    def lookup(self, entries: list[tuple[str, str]]) -> Rule | None:
        """가장 구체적인 (depth 큰) 매치 반환. 없으면 None."""
        entries_set = set(entries)
        rule, _depth = self._dfs(self.root, entries_set, depth=0)
        return rule

    def _dfs(self, node: RuleNode, entries_set, depth):
        # 현재 노드가 rule 있으면 후보. root는 보통 없음.
        best = (node.rate_limit, depth if node.rate_limit else -1)
        for kv, child in node.children.items():
            if kv in entries_set:
                cand = self._dfs(child, entries_set, depth + 1)
                if cand[1] > best[1]:
                    best = cand
        return best


def _build_node(data: dict | None) -> RuleNode:
    """yaml 노드 dict → RuleNode."""
    node = RuleNode()
    if not data:
        return node

    rl = data.get("rate_limit")
    if rl:
        node.rate_limit = Rule(
            algorithm=rl["algorithm"],
            unit=rl["unit"],
            requests_per_unit=rl["requests_per_unit"],
            burst=rl.get("burst"),
            mode=rl.get("mode", "hard"),
        )

    for child_data in data.get("descriptors") or []:
        key = child_data["key"]
        value = child_data["value"]
        node.children[(key, value)] = _build_node(child_data)

    return node


def load_rules(path: Path) -> Rules:
    data = yaml.safe_load(Path(path).read_text())
    return Rules(
        domain=data["domain"],
        root=_build_node({"descriptors": data.get("descriptors") or []}),
    )
```

- [ ] **Step 5: test_rules 통과**

Run: `cd experiments/knot && uv run pytest tests/unit/test_rules.py -v`
Expected: 2 passed.

- [ ] **Step 6: middleware.py가 깨졌는지 확인 — 임시 호환 처리**

`middleware.py`는 cycle 0에서 `rules.lookup("endpoint", endpoint)` 두 인자 형식 사용. 새 인터페이스는 `lookup(entries)` 리스트. 미들웨어 임시 호환:

```python
# app/middleware.py에서
rule = rules.lookup([("endpoint", endpoint_name)]) if rules and endpoint else None
```

(Task 4에서 user_tier도 entries에 추가 예정.)

전체 테스트 실행:

```bash
docker compose up -d redis
cd experiments/knot && REDIS_AVAILABLE=1 uv run pytest -v
```

Expected: 28 passed (cycle 0-3의 모든 테스트, 새 시그니처에서도 유지).

- [ ] **Step 7: 커밋**

```bash
git add experiments/knot/pyproject.toml experiments/knot/uv.lock \
        experiments/knot/app/rules.py experiments/knot/app/middleware.py \
        experiments/knot/tests/unit/test_rules.py
git commit -m "experiment: knot cycle 4 - Rules 트리 모델로 리팩터 + watchdog 의존성"
```

---

## Task 2: 다차원 매칭 unit 5개 (TDD)

**Files:**
- Test: `experiments/knot/tests/unit/test_rules_multidim.py`

- [ ] **Step 1: 5개 테스트 작성**

```python
# experiments/knot/tests/unit/test_rules_multidim.py
import textwrap

import pytest

from app.limiter.base import Rule
from app.rules import load_rules


@pytest.fixture
def rules(tmp_path):
    yaml_text = textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            descriptors:
              - key: user_tier
                value: premium
                rate_limit:
                  algorithm: sliding_window_log
                  unit: minute
                  requests_per_unit: 50
              - key: user_tier
                value: enterprise
                rate_limit:
                  algorithm: sliding_window_log
                  unit: minute
                  requests_per_unit: 500
            rate_limit:
              algorithm: sliding_window_log
              unit: minute
              requests_per_unit: 10
          - key: endpoint
            value: redirect
            rate_limit:
              algorithm: token_bucket
              unit: second
              requests_per_unit: 50
              burst: 100
    """)
    yaml_file = tmp_path / "rules.yaml"
    yaml_file.write_text(yaml_text)
    return load_rules(yaml_file)


def test_endpoint_only_match(rules):
    """user_tier 미선언 시 endpoint default rule 매치."""
    rule = rules.lookup([("endpoint", "shorten")])
    assert rule is not None
    assert rule.requests_per_unit == 10  # default


def test_endpoint_plus_tier_match(rules):
    """endpoint+tier 둘 다 매치되면 tier rule (더 구체적) 선택."""
    rule = rules.lookup([("endpoint", "shorten"), ("user_tier", "premium")])
    assert rule.requests_per_unit == 50

    rule_ent = rules.lookup([("endpoint", "shorten"), ("user_tier", "enterprise")])
    assert rule_ent.requests_per_unit == 500


def test_specificity_priority(rules):
    """depth 큰 매치가 항상 우선 — 입력 순서 무관."""
    # 순서 바꿔도 결과 동일
    rule1 = rules.lookup([("user_tier", "premium"), ("endpoint", "shorten")])
    rule2 = rules.lookup([("endpoint", "shorten"), ("user_tier", "premium")])
    assert rule1 == rule2
    assert rule1.requests_per_unit == 50


def test_unknown_tier_fallback(rules):
    """미정의 tier (예: 'unknown') 보내면 endpoint default."""
    rule = rules.lookup([("endpoint", "shorten"), ("user_tier", "unknown")])
    assert rule.requests_per_unit == 10  # endpoint default


def test_unknown_endpoint_returns_none(rules):
    """정의되지 않은 endpoint → None."""
    rule = rules.lookup([("endpoint", "nonexistent"), ("user_tier", "premium")])
    assert rule is None
```

- [ ] **Step 2: 실행 → 통과 확인** (Task 1에서 트리 구현했으므로 바로 통과해야 함)

Run: `uv run pytest tests/unit/test_rules_multidim.py -v`
Expected: 5 passed.

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/tests/unit/test_rules_multidim.py
git commit -m "experiment: knot cycle 4 - 다차원 매칭 unit 5개 (specificity 우선)"
```

---

## Task 3: 핫리로드 (rules.py에 watcher 추가) + unit 2개

**Files:**
- Modify: `experiments/knot/app/rules.py` (start_watcher 함수 추가)
- Test: `experiments/knot/tests/unit/test_rules_reload.py`

- [ ] **Step 1: rules.py에 watcher 추가**

```python
# 기존 코드 아래에 추가
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class _RulesReloader(FileSystemEventHandler):
    def __init__(self, path: Path, on_reload):
        self._path = path.resolve()
        self._on_reload = on_reload

    def _is_target(self, src: str) -> bool:
        try:
            return Path(src).resolve() == self._path
        except Exception:
            return False

    def on_modified(self, event):
        if not event.is_directory and self._is_target(event.src_path):
            self._on_reload()

    def on_moved(self, event):
        # vim/emacs atomic save: tmp → rename
        if not event.is_directory and self._is_target(event.dest_path):
            self._on_reload()


def start_watcher(path: Path, on_reload) -> Observer:
    """rules.yaml 변경 시 on_reload() 호출하는 watcher 시작."""
    path = path.resolve()
    handler = _RulesReloader(path, on_reload)
    observer = Observer()
    observer.schedule(handler, str(path.parent), recursive=False)
    observer.start()
    logger.info("rules watcher started: %s", path)
    return observer
```

- [ ] **Step 2: 2개 reload 테스트**

```python
# experiments/knot/tests/unit/test_rules_reload.py
import textwrap
import time
from pathlib import Path

import pytest

from app.rules import load_rules, start_watcher


def _write(path: Path, content: str) -> None:
    path.write_text(content)
    # macOS watchdog 안정성 위한 짧은 sleep
    time.sleep(0.05)


def _wait_for(predicate, timeout=2.0, interval=0.05):
    """predicate가 True 되거나 timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_reload_picks_up_new_rule(tmp_path):
    yaml_path = tmp_path / "rules.yaml"
    _write(yaml_path, textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            rate_limit:
              algorithm: always_allow
              unit: minute
              requests_per_unit: 10
    """))

    state = {"rules": load_rules(yaml_path)}

    def reload():
        try:
            state["rules"] = load_rules(yaml_path)
        except Exception:
            pass

    observer = start_watcher(yaml_path, reload)
    try:
        # 새 rule로 덮어쓰기
        _write(yaml_path, textwrap.dedent("""
            domain: knot
            descriptors:
              - key: endpoint
                value: shorten
                rate_limit:
                  algorithm: always_allow
                  unit: minute
                  requests_per_unit: 99
        """))

        # rules.lookup이 새 값을 반환할 때까지 대기
        ok = _wait_for(
            lambda: state["rules"].lookup([("endpoint", "shorten")]).requests_per_unit == 99
        )
        assert ok, "watcher did not pick up new rules"
    finally:
        observer.stop()
        observer.join()


def test_reload_failure_keeps_previous(tmp_path):
    yaml_path = tmp_path / "rules.yaml"
    _write(yaml_path, textwrap.dedent("""
        domain: knot
        descriptors:
          - key: endpoint
            value: shorten
            rate_limit:
              algorithm: always_allow
              unit: minute
              requests_per_unit: 10
    """))

    state = {"rules": load_rules(yaml_path)}

    def reload():
        try:
            state["rules"] = load_rules(yaml_path)
        except Exception:
            pass  # 이전 rules 유지

    observer = start_watcher(yaml_path, reload)
    try:
        # 잘못된 yaml로 덮어쓰기
        _write(yaml_path, "not: valid: yaml: at: all: [")
        time.sleep(0.5)  # watcher trigger 시간

        # 이전 값 유지되어야 함
        rule = state["rules"].lookup([("endpoint", "shorten")])
        assert rule is not None
        assert rule.requests_per_unit == 10
    finally:
        observer.stop()
        observer.join()
```

- [ ] **Step 3: 실행**

Run: `uv run pytest tests/unit/test_rules_reload.py -v`
Expected: 2 passed (각 ~0.5-1s).

**가능한 함정**: macOS의 FSEvents가 느리거나 polling fallback 필요할 수 있음. 실패 시 `observer = Observer()` 대신 `from watchdog.observers.polling import PollingObserver as Observer`로 단순화하는 옵션이 있음 — start_watcher에 `observer = PollingObserver()` 사용. 단 polling은 1초 간격이라 테스트 timeout 조정 필요. 우선 기본 Observer로 시도, 실패하면 polling.

- [ ] **Step 4: 커밋**

```bash
git add experiments/knot/app/rules.py experiments/knot/tests/unit/test_rules_reload.py
git commit -m "experiment: knot cycle 4 - watchdog 파일 watcher + reload unit (성공/실패 fallback 검증)"
```

---

## Task 4: Middleware user_tier 추출 + e2e 확인

**Files:**
- Modify: `experiments/knot/app/middleware.py`

- [ ] **Step 1: middleware에 user_tier entry 추가**

`dispatch` 안:

```python
identity = request.headers.get("x-api-key") or (
    request.client.host if request.client else "unknown"
)
user_tier = request.headers.get("x-user-tier", "default")

entries = [
    ("endpoint", endpoint),
    ("user_tier", user_tier),
]
rule = rules.lookup(entries) if rules else None
```

기존 `lookup([("endpoint", endpoint_name)])` 한 줄을 entries 리스트로 교체.

- [ ] **Step 2: 기존 e2e 테스트 영향 확인**

`tests/integration/test_middleware_e2e.py`의 `test_shorten_returns_200_with_rate_limit_headers`는 `x-user-tier` 미선언 → entries=`[("endpoint","shorten"),("user_tier","default")]`. 현재 rules.yaml(cycle 3 상태)엔 user_tier 차원 없음 → endpoint match만 됨 → 기존과 동일 (sliding_window_log limit=10).

전체 테스트:

```bash
docker compose exec -T redis redis-cli FLUSHALL
REDIS_AVAILABLE=1 uv run pytest -v
```

Expected: 35 passed (이전 28 + 새 5 multidim + 2 reload = 35).

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/app/middleware.py
git commit -m "experiment: knot cycle 4 - middleware user_tier 헤더 entries 추가"
```

---

## Task 5: lifespan에 watcher start/stop

**Files:**
- Modify: `experiments/knot/app/main.py`

- [ ] **Step 1: lifespan 확장**

```python
# experiments/knot/app/main.py — lifespan 함수 교체
from app.rules import Rules, load_rules, start_watcher

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rules = load_rules(RULES_PATH)

    def _reload():
        try:
            app.state.rules = load_rules(RULES_PATH)
        except Exception:
            pass  # 실패 시 이전 rules 유지

    observer = start_watcher(RULES_PATH, _reload)
    try:
        yield
    finally:
        observer.stop()
        observer.join()
        await close_redis()
```

- [ ] **Step 2: app import 검증**

```bash
cd experiments/knot && uv run python -c "from app.main import app; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3: 커밋**

```bash
git add experiments/knot/app/main.py
git commit -m "experiment: knot cycle 4 - lifespan에 rules watcher start/stop"
```

---

## Task 6: rules.yaml 다차원 확장 + integration 3개

**Files:**
- Modify: `experiments/knot/rules.yaml`
- Test: `experiments/knot/tests/integration/test_multidim_e2e.py`

- [ ] **Step 1: rules.yaml 다차원 확장**

```yaml
domain: knot
descriptors:
  - key: endpoint
    value: shorten
    descriptors:
      - key: user_tier
        value: premium
        rate_limit:
          algorithm: sliding_window_log
          unit: minute
          requests_per_unit: 50
      - key: user_tier
        value: enterprise
        rate_limit:
          algorithm: sliding_window_log
          unit: minute
          requests_per_unit: 500
    rate_limit:
      algorithm: sliding_window_log
      unit: minute
      requests_per_unit: 10
  - key: endpoint
    value: redirect
    rate_limit:
      algorithm: token_bucket
      unit: second
      requests_per_unit: 50
      burst: 100
```

- [ ] **Step 2: integration 3개**

```python
# experiments/knot/tests/integration/test_multidim_e2e.py
import pytest


@pytest.mark.asyncio
async def test_free_tier_limited_at_10(client):
    """X-User-Tier: free (또는 미선언) → endpoint default = 10."""
    statuses = []
    for _ in range(11):
        r = await client.post(
            "/shorten",
            json={"url": "https://example.com"},
            headers={"x-api-key": "free-tier-test", "x-user-tier": "free"},
        )
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 10
    assert denied == 1


@pytest.mark.asyncio
async def test_premium_tier_limited_at_50(client):
    """premium tier → 50까지 통과."""
    statuses = []
    for _ in range(51):
        r = await client.post(
            "/shorten",
            json={"url": "https://example.com"},
            headers={"x-api-key": "premium-tier-test", "x-user-tier": "premium"},
        )
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 50
    assert denied == 1


@pytest.mark.asyncio
async def test_default_tier_uses_endpoint_default(client):
    """tier 헤더 없으면 endpoint default = 10."""
    statuses = []
    for _ in range(11):
        r = await client.post(
            "/shorten",
            json={"url": "https://example.com"},
            headers={"x-api-key": "default-tier-test"},
        )
        statuses.append(r.status_code)
    passed = sum(1 for s in statuses if s == 200)
    denied = sum(1 for s in statuses if s == 429)
    assert passed == 10
    assert denied == 1
```

- [ ] **Step 3: 실행**

```bash
docker compose exec -T redis redis-cli FLUSHALL
REDIS_AVAILABLE=1 uv run pytest tests/integration/test_multidim_e2e.py -v
```
Expected: 3 passed.

전체 suite:

```bash
docker compose exec -T redis redis-cli FLUSHALL
REDIS_AVAILABLE=1 uv run pytest -v
```
Expected: 38 passed.

- [ ] **Step 4: 커밋**

```bash
git add experiments/knot/rules.yaml experiments/knot/tests/integration/test_multidim_e2e.py
git commit -m "experiment: knot cycle 4 - rules.yaml shorten user_tier 차등 + e2e 3개"
```

---

## Task 7: wiki + spec status + log + push + PR

**Files:**
- Modify: `wiki/projects/knot.md` (Cycle 4 section append)
- Modify: `docs/specs/2026-05-24-rate-limiter-design.md` (§7 cycle 4 done)
- Modify: `log.md`

- [ ] **Step 1: wiki cycle 4 섹션**

```markdown

## Cycle 4 — 다차원 규칙 + 핫리로드

**목표**: 알고리즘 변경 없이 **운영 측면** — Lyft envoy 중첩 descriptors로 user_tier 차등 정책 + watchdog 파일 watcher로 핫리로드.

**산출**: 7 task, 38개 테스트 통과 (이전 28 + multidim unit 5 + reload unit 2 + multidim e2e 3). 새 의존성 `watchdog`. 알고리즘 코드 0줄 변경.

**Sub-spec**: `docs/specs/2026-05-24-knot-cycle-4-multi-dim-rules-design.md` (결정 이력 12개).

### 무엇이 달라졌나

| | cycle 3까지 | cycle 4 |
|---|---|---|
| 매칭 차원 | `endpoint` 1개 | `endpoint` × `user_tier` 2개 |
| Rules 모델 | 평면 dict | **트리 (RuleNode)** + DFS 매칭 |
| 매칭 우선순위 | — | **가장 구체적 우선** (specificity) |
| 정책 변경 | 앱 재시작 필요 | **watchdog 핫리로드** — 즉시 반영 |
| `shorten` 정책 | 분당 10 (모든 사용자) | free 10 / premium 50 / enterprise 500 |
| `redirect` 정책 | 변경 없음 | 변경 없음 (익명 IP 식별자라 tier 의미 약함) |

### ch04 매핑 — 본 사이클의 핵심

**1. ch04 §"rules-as-data"의 본격 활용**

cycle 0에서 깐 Lyft 포맷이 사실은 **중첩 descriptors로 다차원 매칭을 표현**할 수 있음을 cycle 4에서 비로소 활용:

```yaml
descriptors:
  - key: endpoint
    value: shorten
    descriptors:                  # ← 중첩으로 2차원 표현
      - key: user_tier
        value: premium
        rate_limit: { requests_per_unit: 50 }
    rate_limit: { requests_per_unit: 10 }   # default fallback
```

ch04가 인용한 그 포맷의 정확한 확장. **트리 yaml로 정책 가시성 ↑** — "이 엔드포인트의 default + tier별 override" 구조가 한눈에.

**2. ch04 §"기본 아키텍처" — "워커가 정기적으로 캐시로 로드"의 진짜 구현**

cycle 0에서 "시작 시 1회 로드"만 했던 게 cycle 4에서 비로소 **변경 즉시 반영**으로 진화. yaml만 수정하고 저장하면 100ms 이내 새 정책 적용. 앱 재시작 없음.

**3. ch04 §"분산 환경 — 중앙 공유 저장소"의 정책 측면**

cycle 0~3은 카운터의 중앙화(Redis). cycle 4는 **정책의 중앙화의 첫 단계** — 같은 yaml 파일을 보는 모든 노드가 같은 정책 적용. 실서비스에선 etcd/Consul로 진화 (회고).

### 핵심 결정 (spec §6 일부)

- **차원 선택**: `user_tier` (vs client_type/region) — SaaS 차등이 ch04와 가장 직관
- **포맷**: Lyft envoy 중첩 descriptors (vs flat tuple) — 트리 가시성 + ch04 일관성
- **핫리로드**: watchdog 파일 watcher (vs SIGHUP/polling) — 즉시 반영
- **atomic swap**: 새 Rules 객체 통째 교체 — partial reload 함정 회피, 실패 시 이전 유지
- **user_tier 신뢰**: **학습용**은 헤더 그대로, 실서비스는 API key DB resolution 필수 (회고에 명시)

### 발견된 함정 (cycle 1~3 노트 누적의 가치 검증)

이번 사이클은 **새 함정 거의 없음** — 알고리즘 변경 안 했고 cycle 1~3 패턴(Lua, fakeredis lupa, stale Script, ASGI client.host) 재사용 0건 (rules.py·middleware.py 영역). 새로 만난 디테일:

- **watchdog 에디터 atomic save**: vim/emacs는 `tmp → rename`. `on_modified` 외 `on_moved`도 핸들 — Lyft 포맷 같은 yaml은 에디터 차이 크니까 미리 둘 다 처리
- **macOS FSEvents 지연**: 로컬 dev에선 ~50ms 즉시 반영, CI/Linux는 polling fallback도 옵션 (`watchdog.observers.polling`)

### Cycle 4 회고

knot은 이제 **알고리즘 + 정책 표현력**이 모두 작동:
- 알고리즘: token_bucket (redirect) + sliding_window_log (shorten)
- 정책: endpoint × user_tier × (default fallback) 다차원, 핫리로드

cycle 5는 **정책 강도** 차원 추가 — `mode: hard` vs `mode: soft`. 같은 규칙에 enforcement 모드를 토글, soft는 throttle(지연 응답)로 완화.
```

- [ ] **Step 2: spec §7 cycle 4 status → done**

`docs/specs/2026-05-24-rate-limiter-design.md` §7 표 cycle 4 행:
```
| 4 | 다차원 규칙 + ... | 분산 동기화(중앙 저장소), rules-as-data | done (2026-05-24) |
```

- [ ] **Step 3: log.md append**

```markdown

## [2026-05-24] experiment | knot cycle 4: 다차원 규칙 + 핫리로드

운영 측면 사이클 — 알고리즘 변경 없이 Lyft envoy 중첩 descriptors로 user_tier 차등 정책 (free 10 / premium 50 / enterprise 500) + watchdog 파일 watcher 핫리로드. Rules 데이터 모델을 평면 dict → 트리(RuleNode + DFS specificity matching)로 리팩터. middleware가 `X-User-Tier` 헤더 추출하여 entries 구성.

- `app/rules.py` 트리 리팩터 + start_watcher
- `app/middleware.py` user_tier 추출
- `app/main.py` lifespan watcher start/stop
- `rules.yaml` shorten 중첩 descriptors
- 새 test 10개: multidim unit 5 + reload unit 2 + integration 3 = 38 total passing
- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-4-multi-dim-rules-design.md` §6

cycle 5는 hard vs soft 정책 (같은 규칙에 enforcement 모드 토글).
```

- [ ] **Step 4: stub + 커밋 + push + PR**

```bash
cd /Users/fetching/study/system-design
git status --short
find . -maxdepth 3 -name "*.md" -size 0 -not -path "./.git/*"

git add wiki/projects/knot.md docs/specs/2026-05-24-rate-limiter-design.md log.md
git commit -m "experiment: knot cycle 4 완료 — wiki + spec + log"
git push -u origin experiment/knot-cycle-4

gh pr create --base main --head experiment/knot-cycle-4 \
  --title "experiment: knot cycle 4 (다차원 규칙 + 핫리로드)" \
  --body "$(cat <<'EOF'
## Summary

알고리즘 변경 없는 **운영 측면 사이클**. Lyft envoy 중첩 descriptors로 user_tier 차등 정책 + watchdog 파일 watcher 핫리로드.

- Rules 데이터 모델: 평면 dict → **트리 (RuleNode + DFS specificity matching)**
- shorten 정책 분기: free 10 / premium 50 / enterprise 500 / default fallback
- middleware: `X-User-Tier` 헤더 추출 → entries 리스트 구성
- lifespan: watchdog Observer start/stop, atomic swap reload

## ch04 매핑

- §"rules-as-data"의 본격 활용 — cycle 0에서 깐 Lyft 포맷의 중첩 descriptors가 cycle 4에서 비로소 사용
- §"워커가 정기적으로 캐시로 로드"의 진짜 구현 — cycle 0은 시작 시 1회, cycle 4는 즉시 반영

## 다음 사이클

cycle 5: hard vs soft 정책 (같은 규칙에 enforcement 모드 토글, soft는 throttle(지연)).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## 검증 체크리스트

- [ ] `REDIS_AVAILABLE=1 uv run pytest -v` 38 passed
- [ ] rules.yaml 수정 → 100ms 이내 새 정책 반영 (수동 시연: app 띄우고 curl → yaml 수정 → curl 다른 응답)
- [ ] `X-User-Tier: premium` 헤더로 51회 호출 시 51번째 429
- [ ] tier 헤더 없이 11회 호출 시 11번째 429 (default fallback)
- [ ] watchdog 의존성 정확히 `pyproject.toml` dev에 등록
- [ ] PR 생성

## 다음 사이클

**Cycle 5 — hard vs soft 정책**: 같은 규칙에 enforcement 모드 토글. soft는 통과시키되 throttle(지연 응답)로 완화. cycle 4의 `Rule.mode` 필드(이미 cycle 0에 박혀있던) 활용. ~5 task.
