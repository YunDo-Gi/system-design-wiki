---
chapter: 16
title_en: The Learning Continues
title_ko: 학습은 계속된다
ingested_at: 2026-05-28
---

# The Learning Continues

> 메타·레퍼런스 챕터. 새 개념·기술 페이지를 만들지 않고, 책이 제시한 실세계 자료를 **본 위키의 개념 페이지와 연결**해 다음 학습의 출발점으로 둔다 (ch16, p.264-269).

## 핵심 takeaway

- 좋은 시스템 설계 감각은 **실제 아키텍처를 깊이 읽는 것**으로 길러진다. 각 기술이 "어떤 문제를 푸는가"를 추적하는 게 핵심 (ch16, p.264).
- 책의 ch04~ch15에서 다룬 패턴은 대부분 **실제 회사 사례에서 검증**된 것 — 아래에서 위키 페이지와 실세계 사례를 잇는다.
- 면접 준비라면 지원 회사의 **engineering blog**를 읽어 그들이 채택한 기술·시스템에 익숙해지는 게 유효.

## 실세계 아키텍처 ↔ 위키 개념 매핑

ch16이 추천한 읽을거리를 본 위키 페이지로 연결한 카탈로그:

| 실세계 자료 | 연결되는 위키 페이지 | 무엇을 보강하나 |
|---|---|---|
| Dynamo: Amazon's Highly Available KV Store | [[dynamo]], [[quorum-consensus]], [[vector-clock]], [[gossip-protocol]] | AP·eventual·decentralized 원전 |
| BigTable: Distributed Storage for Structured Data | [[cassandra]], [[lsm-tree-storage-engine]] | wide-column·LSM 계보 |
| TAO: Facebook's Distributed Data Store for the Social Graph | [[graph-database]], [[fanout]] | 소셜 그래프 확장(graph DB 한계 우회) |
| Finding a needle in Haystack: Facebook's photo storage | [[blob-storage]], [[cdn]] | 대규모 미디어 저장 |
| Scaling Memcache at Facebook | [[memcached]], [[caching-strategies]] | 분산 캐시 운영 |
| Announcing Snowflake | [[snowflake-id]], [[unique-id-generation-in-distributed-systems]] | 분산 unique ID |
| Facebook Timeline: Power of Denormalization / Multifeed | [[fanout]], [[caching-strategies]] | 피드 사전 계산 |
| Erlang at Facebook / Facebook Chat / WhatsApp Architecture | [[websocket]], [[presence-and-heartbeat]], [[publish-subscribe]] | 실시간 채팅 |
| Differential Synchronization (Google Docs) | [[delta-sync]], [[sync-conflict-resolution]] | 동기화·충돌 |
| The Google File System | [[blob-storage]], [[delta-sync]] | 분산 파일 저장 |
| YouTube Architecture / Scalability | [[video-transcoding]], [[dag-task-pipeline]], [[cdn]] | 비디오 스트리밍 |
| Scaling Twitter / Timelines at Scale | [[fanout]], [[snowflake-id]] | timeline fanout(push/pull) |
| Uber Real-Time Market Platform | [[publish-subscribe]], [[consistent-hashing]] | 실시간 매칭 |
| Flickr Architecture | [[ticket-server]] | 중앙 ticket server ID |

## 학습 자료 (원문 링크는 raw 책 참조)

- **실세계 시스템**: Facebook(Timeline·Chat·Haystack·Memcache·TAO), Amazon(Dynamo), Netflix(stack·A/B·추천), Google(GFS·BigTable), YouTube, Instagram, Twitter(Snowflake·Timelines), Uber, Pinterest, LinkedIn, Flickr, Dropbox, WhatsApp.
- **엔지니어링 블로그**: Airbnb, Netflix, Stripe, Slack, Uber, Dropbox, Instagram, Pinterest, Shopify, Spotify 등. `highscalability.com`, donnemartin의 `system-design-primer`도 유용.

## 다음 단계 메모

- 본 위키는 ch01~ch16을 모두 ingest 완료. 이후는 **query 세션**에서 페이지 간 합성·비교로 새 통찰을 만들고, 필요 시 신규 개념 페이지로 보존.
- knot(`experiments/`) 같은 실서비스 프로젝트에 위키 패턴을 적용하며 검증하는 게 다음 축.

## 등장 개념

- (이 챕터는 신규 개념을 도입하지 않는다 — 기존 페이지로의 진입 카탈로그)
