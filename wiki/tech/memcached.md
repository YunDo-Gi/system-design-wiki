---
type: tech
category: cache
sources: [ch01]
---

# Memcached

## 한 줄 정의

분산 in-memory key-value 캐시. 책에서 캐시 tier의 대표 사례로 본문에 API 코드까지 인용되는 컴포넌트 (ch01, p.22).

## 주요 특성

- **휘발성 메모리 저장**: 빠른 read/write, 그러나 재시작 시 데이터 손실 → 영속 저장은 별도 (ch01, p.23).
- **간단한 API**: `set(key, value, ttl)`, `get(key)` 수준 (책 예시 그대로).
- **분산**: 여러 노드로 키 공간 분할(클라이언트 측 해싱). 단일 노드 SPOF는 멀티 노드·여러 DC로 회피.
- **TTL·축출 정책**: 만료 기반 제거 + LRU 기반 축출.
- 비교: [[redis]]는 다양한 자료구조·영속화·pub/sub까지 — 책에선 둘을 묶어 "Memcached/Redis"로 자주 언급.

## 언제 선택하는가 / 대안 비교

| 후보 | 특성 | Memcached 대비 |
|---|---|---|
| **Memcached** | 단순 KV, 멀티스레드, 휘발 | 가장 단순·예측 가능, 메모리 효율 좋음 |
| **[[redis]]** | 자료구조 풍부, 영속화, pub/sub, Lua | 기능 ↑, 운영 복잡도 ↑ |
| **로컬 in-process 캐시** | 같은 프로세스 메모리 | 네트워크 0, 노드별 분리 |
| **Hazelcast / Apache Ignite** | 분산 컴퓨팅 그리드 | 메모리 그리드·계산 위임 |

**Memcached 선택 기준**: 단순 캐시 한 가지 용도, 멀티스레드 처리량 필요, 자료구조나 영속화 불필요. 그 외 대부분은 Redis가 일반적 선택.

## 전형적 사용 사례

- DB 결과 캐싱(read-through, [[caching-strategies]] 참조).
- [[stateless-web-tier]] 구성에서 세션 저장소.
- 짧은 TTL의 임시 계산 결과 캐싱.

## 실무 함정

- **재시작·crash 시 100% 데이터 손실**: 영속화 없음. 캐시 warm-up 절차와 DB로의 fallback이 필수.
- **클라이언트 측 해싱의 함정**: 노드 추가/제거 시 일관된 해싱(consistent hashing) 사용 안 하면 **대부분의 키가 재배치** → DB 트래픽 폭주. [[consistent-hashing]] (ch05) 도입 동기 중 하나.
- **Multi-get 부분 실패**: 여러 노드에 분산된 키를 한 번에 가져올 때 일부 노드 다운이면 응답 일부만 옴. 클라이언트는 부분 응답을 graceful하게 처리해야.
- **큰 값 저장 비효율**: 1MB 이상 객체는 메모리 단편화·네트워크 부담. 큰 객체는 [[cdn]]이나 별도 blob 스토리지로.
- **노드 추가 시 cold start**: 새 노드의 hit ratio가 낮아 DB로 트래픽 쏠림. 한 번에 한 노드씩 점진 도입.
- **TTL 동기 만료**: 여러 캐시 항목이 동시에 만료되면 thundering herd. TTL에 jitter 추가.
- **라이브러리 일관성**: 언어별 클라이언트 해싱·인코딩 방식이 달라 다언어 환경에서 키가 안 맞는 사고. 표준 클라이언트(libmemcached 호환) 고정 권장.

## 등장 사례

- ch01 — 캐시 tier의 기본 예시로 등장 (Figure 1-7, API 코드 예제). 이후 [[stateless-web-tier]] 구성의 세션 저장 옵션으로도 다시 언급. 참고 자료로 Facebook의 "Scaling Memcache at Facebook" 인용.
