---
type: concept
tags: [encoding, url-shortener, algorithm]
sources: [ch08]
---

# Base62 인코딩 (Base62 Encoding)

## 한 줄 정의 / 동기

정수 ID를 `[0-9a-zA-Z]` 62개 문자로 표현하는 진법 변환. URL 단축기에서 **unique ID를 사람이 다룰 만한 짧은 문자열로 압축**하는 데 쓴다 (ch08, p.131-133). 충돌이 구조적으로 불가능한 단축 코드를 만든다 — 입력 ID가 unique하면 출력도 unique.

## 왜 필요한가

[[ch08-url-shortener]] 설계에서 단축 코드 생성 전략은 둘로 갈린다:

1. **hash + 충돌 해소**: 긴 URL을 MD5/SHA로 해시 → 앞 7자. 충돌 시 salt 덧붙여 재해시. 매 충돌마다 DB나 [[bloom-filter]] 조회 → **비결정적 쓰기 비용**.
2. **base62 변환**: [[snowflake-id]] 같은 generator가 발급한 unique ID를 62진수로 인코딩. ID가 unique라 **충돌 자체가 없고**, 변환은 산술 연산 1회로 결정적.

base62를 쓰는 이유는 **62 = 10(숫자) + 26(소문자) + 26(대문자)** 이 URL-safe하면서 가장 조밀한 문자 집합이기 때문. base64는 `+`·`/`가 URL에서 escape를 유발해 부적합.

## 동작

```
ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"  # len 62

def encode(id: int) -> str:
    if id == 0:
        return ALPHABET[0]
    s = []
    while id > 0:
        s.append(ALPHABET[id % 62])
        id //= 62
    return ''.join(reversed(s))

def decode(code: str) -> int:
    id = 0
    for ch in code:
        id = id * 62 + ALPHABET.index(ch)
    return id
```

예: id = 11157 → `11157 = 2·62² + 59·62 + 59` → `2`, `X`, `X` (인덱스 59 = 'X') → **"2XX"**.

## 파라미터 · 튜닝 포인트

| 파라미터 | 의미 | 튜닝 방향 |
|---|---|---|
| 코드 길이 n | 표현 가능 수 = 62^n | 62^7 ≈ 3.5조면 10년 규모 커버 |
| ALPHABET 순서 | 인코딩 매핑 | 셔플하면 순차 ID의 예측을 약화 |
| 입력 ID 소스 | base62의 입력 | [[snowflake-id]]·auto_increment·[[ticket-server]] |

**길이 산정**: 필요한 총 URL 수 T에 대해 62^n ≥ T인 최소 n. T=3,650억 → 62^6≈568억(부족), 62^7≈3.5조(충분) → **n=7**.

## 트레이드오프

**Pros**
- 충돌 0 (입력 ID가 unique한 한). 충돌 검사·재시도 로직 불필요.
- 변환이 O(log id) 산술 연산, DB 조회 없음 → 결정적·빠름.
- 코드↔ID 양방향 변환 가능 (decode로 역산).

**Cons**
- **예측 가능성**: 순차 ID면 id+1의 코드도 쉽게 추측 → URL enumerate(스크래핑·정보 유출) 위험. ALPHABET 셔플·난수 ID·hash 방식으로 완화.
- 길이 가변: ID가 커질수록 코드도 길어짐 (hash 방식은 고정 길이).
- 외부 unique ID generator에 의존 → 그 가용성이 SPOF가 될 수 있음.

## 다른 알고리즘과의 위치

| 방식 | 충돌 | 길이 | 예측 | 의존성 |
|---|---|---|---|---|
| **base62 변환** | 없음 | 가변 | 쉬움(순차 시) | unique ID generator |
| hash 앞 N자 + 재시도 | 있음 → 검사 | 고정 | 어려움 | 해시 함수 + [[bloom-filter]] |
| 랜덤 코드 + 검사 | 있음 → 검사 | 고정 | 어려움 | 난수 + 충돌 검사 |

보안(예측 불가)이 핵심이면 hash/랜덤, 단순·결정성이 핵심이면 base62.

## 실무 적용 시 고려사항

- **순차 노출 방어**: 가장 흔한 함정. 생산 단축기는 base62에 더해 ALPHABET 셔플 또는 ID에 난수 비트를 섞는다. snowflake는 timestamp 상위 비트라 어느 정도 예측 가능 → 보안 필요 시 추가 난수.
- **대소문자 구분 매체**: 일부 시스템(대소문자 무시 URL)에서 62자 중 대/소문자 충돌 위험 → base36(`[0-9a-z]`)로 다운그레이드 고려.
- **decode 의존 여부**: 코드↔ID 역산이 필요 없으면 ALPHABET을 마음껏 셔플해도 됨. 역산이 필요하면 매핑 테이블 고정 보관.
- **knot 적용**: knot의 단축 코드 생성은 ch07 [[snowflake-id]] → base62 체인으로 구성 가능 (ch08 적용 후보).

## 등장 사례

- ch08 — URL 단축기의 두 코드 생성 전략 중 채택안. 충돌 없는 결정적 생성.
- Bit.ly·TinyURL — 단축 코드에 base62 계열 인코딩 사용 (순차 노출 방어 위해 변형).
- knot — ch07 snowflake ID를 base62로 변환해 단축 코드 생성 (적용 예정).
