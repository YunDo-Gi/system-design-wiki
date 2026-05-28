---
type: concept
tags: [data-structure, algorithm, search, prefix]
sources: [ch13]
---

# Trie (Prefix Tree)

## 한 줄 정의 / 동기

문자열을 **공통 prefix를 공유하는 트리**로 압축 저장하는 자료구조(이름은 re**trie**val에서). prefix로 시작하는 모든 단어를 트리 경로 따라가기로 찾을 수 있어 **자동완성·top-k 검색**에 최적이다 (ch13, p.204-209).

## 동작

### 기본 구조

- 루트 = 빈 문자열.
- 각 노드는 한 글자를 저장, 최대 26개 자식(영어 소문자). 빈 링크는 생략해 공간 절약.
- 루트→노드 경로 = 하나의 prefix 또는 완성 단어.

```
        (root)
       /      \
      t        w
     / \        \
    r   o        i
   /|\   \      / \
  e i u   y    s   n
  e e e            h
```
(tree, try, true, toy, wish, win을 담은 trie)

### top-k 자동완성 (순진한 버전)

용어: p=prefix 길이, n=전체 노드 수, c=노드의 자식 수.

1. prefix 노드 찾기 — **O(p)**
2. 서브트리 순회로 유효 자식(완성 가능 단어) 수집 — **O(c)**
3. 빈도순 정렬 후 top-k — **O(c·log c)**

합 O(p)+O(c)+O(c·log c). worst-case에 서브트리 전체 순회라 느리다.

### 두 최적화 → O(1)

| 최적화 | 효과 |
|---|---|
| **prefix 최대 길이 제한**(예 50자) | 1단계 O(p)→O(1) (작은 상수) |
| **노드마다 top-k 미리 캐시** | 2·3단계 제거 — prefix 노드에서 바로 top-k 반환 → O(1) |

노드 `be`에 `[best:35, bet:29, bee:20, be:15, beer:10]`를 저장해 두면 순회·정렬 없이 즉답.

## 파라미터 · 튜닝 포인트

- **k**: 보통 5~10이면 충분 → 노드당 저장 부담이 작다.
- **prefix max length**: 사용자는 긴 질의를 거의 안 쳐 50 정도면 안전.
- **노드 top-k 캐시 vs 공간**: 모든 노드에 top-k 저장은 공간을 크게 먹는다. fast response가 중요하면 가치 있는 거래.

## 트레이드오프

- **Pros**: prefix 검색이 자연스럽고 빠름, 공통 prefix 공유로 문자열 집합을 압축, top-k 캐시로 O(1).
- **Cons**: 메모리 사용 큼(특히 노드별 top-k 캐시), 갱신 비용(노드 갱신 시 조상의 top-k까지 root로 전파), 단일 서버 용량 초과 시 샤딩이 까다로움(prefix 분포 불균형).
- **선택 기준**: prefix 매칭·자동완성·사전류엔 trie. 정확 일치만 필요하면 hash가 더 가볍고, 범위 질의엔 B-tree/정렬 인덱스가 낫다.

## 다른 알고리즘과의 위치

| 자료구조 | prefix 검색 | 정확 일치 | 범위 질의 | 메모리 |
|---|---|---|---|---|
| **Trie** | **빠름** | 빠름 | 약함 | 큼 |
| Hash table | 불가 | **O(1)** | 불가 | 중간 |
| B-tree / 정렬 인덱스 | 가능(느림) | O(log n) | **강함** | 중간 |

## 실무 적용 시 고려사항

- 실서비스는 trie를 **주기적 batch로 빌드**해 캐시·DB로 서빙하고, 질의마다 갱신하지 않는다(빌드/서빙 분리). 갱신은 전체 교체가 개별 노드 갱신보다 단순.
- 직렬화해 [[document-database]]에 스냅샷 저장하거나, prefix→node를 [[nosql-database]] KV로 매핑해 저장.
- 샤딩은 첫 글자 기준이 출발점이나 분포 불균형('c'≫'x') → shard map manager로 보정 ([[sharding]]).
- 다국어는 노드에 Unicode 저장. compressed trie(radix tree)로 메모리를 더 줄일 수 있다.

## 등장 사례

- ch13 — 검색 자동완성의 핵심 자료구조, 노드별 top-k 캐시
- Google/Facebook typeahead — trie 기반 prefix 검색 + browser 캐시
- IP 라우팅 테이블·사전·맞춤법 검사 — prefix 매칭 일반 활용
