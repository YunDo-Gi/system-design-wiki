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
