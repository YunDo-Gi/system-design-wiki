# Activity Log

> Append-only. 각 항목 헤더 포맷: `## [YYYY-MM-DD] {ingest|query|lint|schema} | 짧은 제목`
> 최근 활동만 보고 싶으면: `grep "^## \[" log.md | tail -10`

## [2026-05-19] schema | 위키 골격 셋업

- raw/, wiki/{chapters,concepts,tech}/ 디렉터리 생성
- CLAUDE.md, README.md, index.md, log.md 초기 작성
- raw/SystemDesignInterview.pdf 추가
- GitHub: github.com/YunDo-Gi/system-design-wiki 동기화 시작

## [2026-05-19] ingest | ch01: Scale From Zero to Millions of Users

사용자 승인하에 8개 룰 일시 해제, 후보 전체(15개) ingest.

- `wiki/chapters/ch01-scale-zero-to-millions.md`
- concepts (8):
  - `wiki/concepts/vertical-vs-horizontal-scaling.md`
  - `wiki/concepts/database-replication.md`
  - `wiki/concepts/stateless-web-tier.md`
  - `wiki/concepts/caching-strategies.md`
  - `wiki/concepts/sharding.md`
  - `wiki/concepts/single-point-of-failure.md`
  - `wiki/concepts/multi-data-center.md`
  - `wiki/concepts/decoupling-with-message-queue.md`
- tech (7):
  - `wiki/tech/load-balancer.md`
  - `wiki/tech/cdn.md`
  - `wiki/tech/memcached.md`
  - `wiki/tech/relational-database.md`
  - `wiki/tech/nosql-database.md`
  - `wiki/tech/message-queue.md`
  - `wiki/tech/dns.md`
- `index.md` 갱신 (Chapters/Concepts/Tech 섹션 채움)
- 미해결 위키링크: [[consistent-hashing]] (ch05 ingest 시 생성 예정)

## [2026-05-19] ingest | ch02: Back-of-the-Envelope Estimation

사용자 승인하에 5개 페이지 ingest (chapter 1 + concepts 4, 새 기술 없음).

- `wiki/chapters/ch02-back-of-the-envelope-estimation.md`
- concepts (4):
  - `wiki/concepts/back-of-the-envelope-estimation.md`
  - `wiki/concepts/power-of-two-data-units.md`
  - `wiki/concepts/latency-numbers.md`
  - `wiki/concepts/availability-sla-nines.md`
- `index.md` 갱신 (Chapters/Concepts)

## [2026-05-19] ingest | ch03: A Framework for System Design Interviews

메타/프로세스 장 — 새 기술 컴포넌트 없음. 2개 페이지 ingest.

- `wiki/chapters/ch03-framework-for-interviews.md`
- `wiki/concepts/four-step-interview-framework.md`
- `index.md` 갱신 (Chapters/Concepts)

## [2026-05-19] ingest | ch04: Design a Rate Limiter

8개 페이지 ingest (chapter 1 + concepts 6 + tech 2). 본격 기술 챕터 — 알고리즘 5개를 각각 별도 페이지로.

- `wiki/chapters/ch04-rate-limiter.md`
- concepts (6):
  - `wiki/concepts/rate-limiting.md` (총론)
  - `wiki/concepts/token-bucket-algorithm.md`
  - `wiki/concepts/leaking-bucket-algorithm.md`
  - `wiki/concepts/fixed-window-counter-algorithm.md`
  - `wiki/concepts/sliding-window-log-algorithm.md`
  - `wiki/concepts/sliding-window-counter-algorithm.md`
- tech (2):
  - `wiki/tech/redis.md` (이후 챕터에서 재등장 예상)
  - `wiki/tech/api-gateway.md`
- `index.md` 갱신

## [2026-05-19] lint | ch04 후속 정합성 보강

ch04에서 새로 만든 [[redis]] 페이지로 향하는 위키링크가 기존 ch01 페이지들에 누락 → 보강.

- `wiki/tech/memcached.md`: "비교: Redis는…" → `[[redis]]` 링크
- `wiki/concepts/caching-strategies.md`: 등장 사례에 `[[redis]]` 추가, ch04 사례 라인 추가
- `wiki/concepts/stateless-web-tier.md`: 세션 저장소 옵션 `Redis` → `[[redis]]`

미해결 링크 `[[consistent-hashing]]`은 ch05 ingest 시 해소 예정. `[[slug]]`는 index.md 코드블록 내 placeholder로 의도된 것 (실제 링크 아님).

## [2026-05-19] schema | 씨앗 사이클 회고 결과 반영

ch01~04 ingest 후 사용자 회고 인터뷰 결과 CLAUDE.md 개정:

- 섹션 0 신설: 위키 목적을 학습·설계 적용 중심으로 명문화
- 페이지 단어 수 상한 폐지, "자족성"이 평가 기준 (3-1)
- 챕터 페이지는 개념 기반 섹션으로 구성, 책의 Step 1/2/3/4 답습 금지 (3-3)
- 챕터 페이지 등장 개념/기술 섹션은 한 줄 요약 동반 (3-3)
- 개념·기술 페이지에 실무 적용·함정 섹션 신설 (3-3)
- 알고리즘·기법 페이지 전용 템플릿 신설 (3-3)
- 인용은 PDF 페이지 번호 기준임을 명시 (3-1)
- 등장 사례 포맷 표준화 (3-4)
- Stub 점검 절차 추가 (4-5)
- 스코프 가드 8개 → 12개

## [2026-05-19] lint | schema retrofit 1차 - 챕터·알고리즘 페이지

신 컨벤션을 ch01~04에 retrofit. 1차로 챕터 4개 + ch04 알고리즘 5개 = 9개 페이지 재작성.

- 챕터 4개: 책의 Step 1/2/3/4 분절을 제거하고 개념 기반 섹션 구조로 (위치·알고리즘·분산 난제·운영 등). ch02·ch03은 메타 성격으로 간결 유지.
- 알고리즘 5개: 알고리즘 전용 8섹션 템플릿 적용. 의사코드 + 파라미터/튜닝 + 다른 알고리즘과의 위치 + 실무 적용 시 고려사항 추가.
- 챕터 페이지 등장 개념/기술 섹션은 한 줄 요약 동반 형태로 통일.

2차(개념·기술 페이지 보강)는 별도 lint 커밋 예정.

## [2026-05-19] lint | schema retrofit 2차 - 개념·기술 페이지 보강

신 컨벤션의 누락 섹션을 ch01-04의 모든 개념·기술 페이지에 추가. 총 23개 페이지.

- 개념 페이지 14개에 `실무 적용 시 고려사항` 섹션 추가
- 기술 페이지 9개에 `언제 선택하는가 / 대안 비교` + `실무 함정` 섹션 추가
- 일부 페이지엔 비교 표·관련 패턴 표(예: caching 패턴, sharding 전략) 함께 추가

대상:
- concepts: vertical-vs-horizontal-scaling, database-replication, stateless-web-tier, caching-strategies, sharding, single-point-of-failure, multi-data-center, decoupling-with-message-queue, back-of-the-envelope-estimation, power-of-two-data-units, latency-numbers, availability-sla-nines, four-step-interview-framework, rate-limiting
- tech: load-balancer, cdn, memcached, relational-database, nosql-database, message-queue, dns, redis, api-gateway

씨앗 사이클(ch01-04) retrofit 종료. ch05부터는 신 컨벤션 적용.

## [2026-05-19] ingest | ch05: Design Consistent Hashing

2개 페이지 ingest. forward reference로 ch01·ch04에 걸려 있던 `[[consistent-hashing]]` 해소.

- `wiki/chapters/ch05-consistent-hashing.md` — 챕터 페이지 (짧음, 큰 그림 위주)
- `wiki/concepts/consistent-hashing.md` — 알고리즘 전용 8섹션 템플릿 적용, hash ring·virtual nodes·실무 적용까지 깊이
- Mermaid hash ring 다이어그램 추가 (양쪽 페이지)
- `index.md` 갱신

Dynamo·Cassandra 같은 실제 시스템은 ch06에서 본격 도입 예정. virtual-nodes 별도 페이지화는 보류 (현재는 consistent-hashing 섹션으로 충분).

## [2026-05-19] schema | Mermaid 다이어그램 컨벤션 추가

3-4 신설, 3-4 등장 사례 포맷은 3-5로 번호 이동. 책 figure 직접 사용 금지·재작성 원칙 명시.

## [2026-05-19] lint | ch01-04 대표 다이어그램 9개 추가

시각화 가치가 큰 지점에 Mermaid 다이어그램을 신규 삽입:

- `wiki/chapters/ch01-scale-zero-to-millions.md` — 최종 청사진 (web/cache/DB master-slave/queue/workers/NoSQL)
- `wiki/concepts/database-replication.md` — master 1 / slave N 데이터 흐름
- `wiki/concepts/caching-strategies.md` — cache aside 시퀀스 다이어그램
- `wiki/concepts/decoupling-with-message-queue.md` — producer / queue / consumer
- `wiki/concepts/multi-data-center.md` — geoDNS + 두 DC + 양방향 복제
- `wiki/concepts/token-bucket-algorithm.md` — refiller / bucket / decision 흐름
- `wiki/concepts/leaking-bucket-algorithm.md` — FIFO + worker fixed rate
- `wiki/concepts/sliding-window-counter-algorithm.md` — prev/current window 가중 ASCII 다이어그램
- `wiki/chapters/ch04-rate-limiter.md` — rate limiter 미들웨어 + Redis + 규칙 워커

나머지 페이지는 ch05+ 진행 중에 자연스럽게 추가.

## [2026-05-22] ingest | ch06: Design a Key-Value Store

본 위키 첫 종합 시스템 설계 챕터. 12개 페이지 ingest (chapter 1 + concepts 9 + tech 2).

- `wiki/chapters/ch06-design-key-value-store.md` — CAP·quorum·vector clock·gossip·Merkle·LSM의 종합편
- concepts (9):
  - `wiki/concepts/cap-theorem.md` — CP vs AP의 분기, CA는 환상
  - `wiki/concepts/consistency-models.md` — strong/weak/eventual 스펙트럼
  - `wiki/concepts/quorum-consensus.md` — N/W/R, `W+R>N`이면 strong
  - `wiki/concepts/vector-clock.md` — [server, version], ancestor/sibling 판정
  - `wiki/concepts/gossip-protocol.md` — 분산 멤버십·장애 전파
  - `wiki/concepts/sloppy-quorum-hinted-handoff.md` — 임시 장애 + hand-back
  - `wiki/concepts/merkle-tree.md` — 영구 장애 anti-entropy
  - `wiki/concepts/lsm-tree-storage-engine.md` — Commit log + Memtable + SSTable
  - `wiki/concepts/bloom-filter.md` — LSM read의 1차 필터
- tech (2):
  - `wiki/tech/dynamo.md` — Amazon Dynamo paper (DynamoDB와 구분)
  - `wiki/tech/cassandra.md` — Dynamo + BigTable storage 융합
- `index.md` 갱신 (Chapters/Concepts/Tech)

ch06은 ch01~05의 누적된 기법들이 하나의 시스템 안에서 종합되는 인플렉션 포인트. Mermaid 다이어그램 다수 포함 (CAP 분기, write/read path, sloppy quorum 흐름, Merkle tree 비교 등). 본 위키 페이지 수 47개 도달.

## [2026-05-24] design | knot: ch04 rate limiter 학습 프로젝트 spec

ch04의 모든 핵심 개념과 추가 토픽을 직접 구현해 검증하기 위한 학습용 코드 베이스 설계. 가상 서비스 `knot`(URL 단축 SaaS)을 캐리어로 깔고 사이클 0~9로 점진 진행. 5개 알고리즘을 동일 인터페이스 plug-in으로 구성, Redis 단일 저장소, Lyft envoy 포맷 YAML 규칙, k6 부하 + matplotlib 리포트. 코드 위치는 `experiments/knot/` (위키 컨벤션과 분리).

- `docs/specs/2026-05-24-rate-limiter-design.md` — 본 spec
- `CLAUDE.md` — §8 "실험 코드 (`experiments/`)" 신설, 커밋 프리픽스 `experiment:` 추가
- 구현은 후속 commit (사이클 0부터)
- 위키 cross-link 대상: [[ch04-rate-limiter]], 5개 알고리즘 페이지, [[rate-limiting]], [[redis]], [[api-gateway]]

## [2026-05-24] experiment | knot cycle 0: Foundation

FastAPI 앱·미들웨어 셸·규칙 로더·AlwaysAllow dummy limiter·Redis docker-compose·테스트 골격 완성. 사이클 1(token bucket)부터는 limiter 모듈 추가만으로 동작. 10개 task 완료, 10개 테스트 통과 (unit 6 + integration 4).

- `experiments/knot/` 전체 신규 (9 commits)
- `wiki/projects/knot.md` 신규 — 사이클별 ch04 매핑·결정 사유·발견된 함정 (TDD가 잡은 Starlette/ASGI lifespan 함정 포함)
- `CLAUDE.md` §3-6 신설 — wiki/projects/ 카테고리 운영 규칙
- `docs/specs/2026-05-24-rate-limiter-design.md` §7 cycle 0 status → done

## [2026-05-24] experiment | knot cycle 1: Token Bucket

[[token-bucket-algorithm]] plug-in 완성 + k6 부하 실측 + matplotlib 리포트 도구 chain 1회 셋업. Lua script + `redis.call('TIME')`로 atomicity 보장, asyncio.gather 200 동시 요청 race demo로 직접 증명 (passed=101/denied=99, capacity=100). cycle 2~5는 알고리즘 모듈만 추가하면 같은 도구 chain 재사용.

- `experiments/knot/app/limiter/token_bucket.py`, `scripts/token_bucket.lua` 신규
- `experiments/knot/scripts/report.py` 신규 (알고리즘 무관)
- `experiments/knot/load/token_bucket.k6.js`, `reports/token_bucket.md` 신규 (+ PNG 차트)
- `wiki/projects/knot.md` cycle 1 섹션 append — 함정 6개, 실측 결과, ch04 매핑
- 결정 이력: `docs/specs/2026-05-24-knot-cycle-1-token-bucket-design.md` §7

## [2026-05-24] experiment | knot cycle 2: Fixed Window (demo lite)

ch04 §"알고리즘 비교"의 fixed window "정확도: 낮음 (경계 burst)" 셀을 그래프로 시각화하는 demo. knot 엔드포인트 정책 변경 없음 — full cycle의 1/4 시간(4 task)으로 학습 본질만 흡수. 분 경계 직전 100통과 + 직후 100통과 = 2초 구간에 200 요청 통과 (의도 100의 2배) 그래프 확인.

- `experiments/knot/app/limiter/fixed_window.py`, `scripts/fixed_window.lua` 신규
- `experiments/knot/load/fixed_window_boundary.k6.js`, `reports/fixed_window.md` 신규
- `app/main.py` — `KNOT_RULES_PATH` env override 추가 (cycle 4 핫리로드 사전 셋업)
- `scripts/report.py` — pandas datetime bar chart 함정 수정 (cycle 1+ 모든 리포트에 적용됨)
- `wiki/projects/knot.md` cycle 2 짧은 섹션
- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-2-fixed-window-design.md` §6

## [2026-05-24] experiment | knot cycle 3: Sliding Window Log

[[sliding-window-log-algorithm]] full 사이클. `shorten` 엔드포인트를 sliding_window_log로 전환 (분당 10, mode hard). ZSET + Lua 3명령 atomic 묶음. race demo (asyncio.gather 50, limit 10) → 정확히 10 통과, 0 jitter — token bucket의 +1 jitter와 달리 timestamp 엄격 비교. boundary_burst_replay 그래프(cycle 2와 동일 시나리오)에서 spike-spike 없이 균등 throttle 시각화.

- `app/limiter/sliding_window_log.py`, `scripts/sliding_window_log.lua` 신규
- `load/sliding_window_log.k6.js` (4 시나리오) + `reports/sliding_window_log.md`
- `rules.yaml` shorten → sliding_window_log (knot 두 엔드포인트 모두 활성화 완료)
- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-3-sliding-window-log-design.md` §7

knot의 알고리즘 사이클 종료. cycle 4부터는 운영 측면(다차원 규칙·hard/soft·클라이언트 SDK·회고).

## [2026-05-24] experiment | knot cycle 4: 다차원 규칙 + 핫리로드

운영 측면 사이클 — 알고리즘 변경 없이 Lyft envoy 중첩 descriptors로 user_tier 차등 정책 (free 10 / premium 50 / enterprise 500) + watchdog 파일 watcher 핫리로드. Rules 데이터 모델을 평면 dict → 트리(RuleNode + DFS specificity matching)로 리팩터. middleware가 `X-User-Tier` 헤더 추출하여 entries 구성.

- `app/rules.py` 트리 리팩터 + start_watcher
- `app/middleware.py` user_tier 추출
- `app/main.py` lifespan watcher start/stop
- `rules.yaml` shorten 중첩 descriptors
- 새 test 10개: multidim unit 5 + reload unit 2 + integration 3 = 38 total passing
- 결정 이력: spec `docs/specs/2026-05-24-knot-cycle-4-multi-dim-rules-design.md` §6

cycle 5는 hard vs soft 정책 (같은 규칙에 enforcement 모드 토글).
