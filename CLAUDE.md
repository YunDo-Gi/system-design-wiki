# System Design Wiki — LLM 운영 규칙

이 디렉터리는 Alex Xu의 *System Design Interview — An Insider's Guide, 2nd Edition* 학습을 위한 **LLM 유지보수형 마크다운 위키**다. 이 문서는 위키를 운영하는 모든 LLM 세션이 매번 읽어야 하는 운영 매뉴얼이다.

설계 문서: `docs/specs/2026-05-19-llm-wiki-design.md`

## 1. 역할 분담

- **사용자**: 소스 큐레이션(어느 챕터를 언제 ingest), 질문 던지기, 결과 검토 및 피드백.
- **LLM (당신)**: 페이지 작성, 위키링크 유지, index.md/log.md 갱신, git 커밋·푸시. 사용자가 명시 승인하지 않은 파일은 만들지 않는다.

## 2. 디렉터리 규약

```
raw/                        원본 자료 (읽기 전용, 절대 수정 금지)
wiki/chapters/              챕터 요약. 파일명: chNN-kebab-slug.md
wiki/concepts/              개념·패턴 페이지. 파일명: kebab-case.md
wiki/tech/                  기술·컴포넌트 페이지. 파일명: kebab-case.md
index.md                    내용 지향 카탈로그 (query 시 가장 먼저 읽기)
log.md                      시간순 활동 로그 (append-only)
docs/specs/                 설계 문서 (수정하지 말 것)
docs/plans/                 구현 계획서 (수정하지 말 것)
```

## 3. 페이지 컨벤션

### 3-1. 공통

- **언어**: 본문은 한국어. 개념·기술 고유명사는 **영어 병기** 형식. 예: "일관된 해싱 (Consistent Hashing)".
- **크기**: 한 페이지 200~600 단어. 초과 시 사용자에게 분할 제안.
- **위키링크**: 다른 페이지 언급은 Obsidian 스타일 `[[slug]]`. 예: `[[consistent-hashing]]`, `[[redis]]`.
- **인용**: 책 출처는 인라인으로 `(ch03, p.45)` 형식.

### 3-2. Frontmatter

**chapters/chNN-*.md**

```yaml
---
chapter: 1
title_en: Scale From Zero to Millions of Users
title_ko: 0에서 수백만 사용자까지의 확장
ingested_at: YYYY-MM-DD
---
```

**concepts/*.md**

```yaml
---
type: concept
tags: [scalability, distributed-systems]   # 자유롭게
sources: [ch01, ch05]                       # 등장한 챕터들
---
```

**tech/*.md**

```yaml
---
type: tech
category: cache    # cache | db | queue | proxy | cdn | search | observability | …
sources: [ch01, ch04]
---
```

### 3-3. 페이지 내부 구조 (권장 템플릿)

**챕터 페이지**: `# 제목 (영문)` → `## 핵심 takeaway` (3-5 bullet) → `## 본문 요약` → `## 등장 개념` (`[[링크]]` 목록) → `## 등장 기술` (`[[링크]]` 목록) → `## 면접 관점 메모`.

**개념 페이지**: `# 제목` → `## 한 줄 정의` → `## 왜 필요한가` → `## 핵심 메커니즘` → `## 트레이드오프` → `## 등장 사례` (sources 기반).

**기술 페이지**: `# 제목` → `## 한 줄 정의` → `## 주요 특성` → `## 전형적 사용 사례` → `## 등장 사례`.

## 4. 워크플로

### 4-1. 세션 시작·종료

- **시작**: 작업 전에 반드시 `git pull --rebase` 실행. 변경사항 있으면 그것을 먼저 인지하고 작업.
- **종료**: 변경사항이 있으면 commit + push. push 없이 세션 종료 금지.

### 4-2. Ingest (사용자가 "chNN ingest" 요청)

1. `raw/SystemDesignInterview.pdf` 의 해당 챕터 읽기.
2. 사용자에게 **한국어로** 다음을 보고:
   - 핵심 takeaway 3-5개.
   - page화 후보 개념 목록(이름 + 한 줄 이유).
   - page화 후보 기술 목록(이름 + 한 줄 이유).
3. 사용자 피드백(강조/누락/제외) 수렴.
4. 파일 작업:
   a. `wiki/chapters/chNN-*.md` 작성.
   b. 각 개념 → `wiki/concepts/` 신규 생성 또는 기존 페이지의 `sources[]` 추가 및 본문 보강.
   c. 각 기술 → `wiki/tech/` 동일하게.
   d. `index.md` 의 해당 섹션 갱신.
   e. `log.md` 에 항목 append: `## [YYYY-MM-DD] ingest | chNN: 제목` + 변경 파일 목록.
5. `git add -A && git commit -m "ingest: chNN"` 후 사용자에게 검토 요청.
6. 사용자 수정 요청 반영 후 `git push`.

### 4-3. Query

1. 질문 받으면 `index.md` 먼저 read → 관련 페이지 식별.
2. 관련 페이지들 read → 한국어 답변 생성, 인라인 인용 포함.
3. 답변이 **새 통찰**(여러 페이지 합성, 새 비교/대조)을 담고 있다면 사용자에게:
   "이 결과를 `wiki/concepts/<slug>.md`(또는 적절 위치)로 보존할까요?" 제안.
4. 사용자 승인 시에만 페이지화 + `index.md` 갱신.
5. `log.md` 에 `## [YYYY-MM-DD] query | 질문 요약` append (페이지 만들었으면 파일 목록 포함).
6. 변경사항이 있으면 `query:` 프리픽스 commit + push.

### 4-4. Lint (사용자가 "lint" 요청 시)

위키 전체를 점검하여 다음을 사용자에게 보고:

- 페이지 간 모순.
- orphan 페이지(다른 페이지에서 백링크 0).
- 본문에서 위키링크로 언급되나 페이지가 없는 항목.
- stale 클레임(새 챕터 ingest가 기존 페이지 갱신을 요했어야 함).

수정은 사용자 승인 후. 커밋 프리픽스: `lint:`.

## 5. 커밋 컨벤션

| 프리픽스 | 용도 |
|---|---|
| `ingest:` | 챕터 ingest 결과 |
| `query:` | query에서 파생된 페이지 추가 |
| `lint:` | 정합성 정리 |
| `schema:` | CLAUDE.md 자체 갱신 |
| `raw:` | raw/ 자료 추가 |
| `docs:` | docs/ 하위 문서 |
| `chore:` | gitignore, 디렉터리 골격 등 |
| `vault:` | Obsidian Git 플러그인 자동 커밋 (LLM 사용 금지) |

## 6. 스코프 가드

- 한 ingest 사이클에서 새로 만드는 페이지가 **8개를 초과**하면 멈추고 사용자에게 우선순위 협의.
- 한 페이지가 **600단어를 초과**하면 분할 제안.
- query 결과의 페이지화는 항상 사용자 명시 승인 후.

## 7. 첫 사이클(씨앗) 정책

ch01~ch03 ingest 동안 사용자가 페이지 포맷을 적극 피드백한다. 그 결과로 본 CLAUDE.md 의 페이지 컨벤션을 `schema:` 커밋으로 갱신할 수 있다. ch04 이후부터 자율성을 늘린다.

## 8. 절대 하지 말 것

- `raw/` 안의 파일 수정.
- 사용자 승인 없이 `wiki/` 페이지 다수 생성(8개 초과 룰).
- push 없이 세션 종료.
- `vault:` 프리픽스 사용 (Obsidian 자동 커밋 전용).
- 영어 본문 작성 (병기 외에는 한국어).
