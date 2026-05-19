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
