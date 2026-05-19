# LLM Wiki — System Design Interview 학습용 설계 문서

- **작성일**: 2026-05-19
- **대상 도메인**: Alex Xu, *System Design Interview — An Insider's Guide, 2nd Edition* 학습
- **위치**: `~/study/system-design/`
- **원격**: `git@github.com:YunDo-Gi/system-design-wiki.git` (private)
- **패턴 출처**: Andrej Karpathy, "LLM Wiki" 패턴

## 1. 목표

System Design Interview 책 학습 내용을 RAG 방식이 아닌 **LLM이 유지보수하는 누적형 마크다운 위키**로 축적한다. 챕터를 읽을 때마다 LLM이 챕터 요약 + 등장 개념/기술 페이지를 점진적으로 갱신하여, 책을 끝낼 때쯤엔 챕터·개념·기술이 상호 링크된 companion wiki가 자연스럽게 구축되도록 한다.

## 2. 아키텍처 — 3-Layer

### 2-1. Raw Sources (`raw/`)
- 원본 자료 보관. LLM은 읽기만, 수정 금지.
- 현재: `raw/system-design-interview-v2.pdf` 한 권.

### 2-2. Wiki (`wiki/`)
- LLM이 전적으로 소유·관리하는 마크다운 페이지 디렉터리.
- 세 가지 페이지 타입:
  - `wiki/chapters/` — 챕터 요약 (파일명: `chNN-kebab-slug.md`)
  - `wiki/concepts/` — 개념·패턴 페이지 (파일명: `kebab-case.md`)
  - `wiki/tech/` — 기술·컴포넌트 페이지 (파일명: `kebab-case.md`)

### 2-3. Schema (`CLAUDE.md`)
- LLM 운영 규칙. 페이지 컨벤션·워크플로·정책을 명시.
- 사용자와 LLM이 첫 3챕터 ingest 동안 함께 다듬으며 안정화.

### 2-4. 인덱스 & 로그 (루트)
- `index.md` — 내용 지향 카탈로그. 매 ingest마다 갱신.
- `log.md` — 시간순 append-only 활동 로그.

### 2-5. 전체 디렉터리 트리

```
~/study/system-design/
├── .git/
├── .gitignore
├── .obsidian/
├── CLAUDE.md
├── README.md
├── index.md
├── log.md
├── docs/
│   └── specs/
│       └── 2026-05-19-llm-wiki-design.md   ← 이 문서
├── raw/
│   └── system-design-interview-v2.pdf
└── wiki/
    ├── chapters/
    ├── concepts/
    └── tech/
```

## 3. 페이지 컨벤션

### 3-1. 공통
- **본문 언어**: 한국어. 개념·기술 고유명사는 영어 병기 — 예: "일관된 해싱 (Consistent Hashing)".
- **크기 가이드**: 한 페이지 200~600단어. 초과 시 분할 제안.
- **위키링크**: 다른 페이지 언급은 Obsidian 스타일 `[[consistent-hashing]]`.
- **인용**: 책 출처는 인라인으로 `(ch03, p.45)`.

### 3-2. 페이지 타입별 frontmatter

**chapters/chNN-*.md**
```yaml
---
chapter: 1
title_en: Scale From Zero to Millions of Users
title_ko: 0에서 수백만 사용자까지의 확장
ingested_at: 2026-05-19
---
```

**concepts/*.md**
```yaml
---
type: concept
tags: [scalability, distributed-systems]
sources: [ch01, ch05]
---
```

**tech/*.md**
```yaml
---
type: tech
category: cache         # cache | db | queue | proxy | cdn | …
sources: [ch01, ch04]
---
```

### 3-3. 페이지 내부 구조 (권장 템플릿)

- **챕터 페이지**: 핵심 takeaway 3-5개 → 본문 요약 → 등장 개념/기술 위키링크 목록 → 면접 관점 메모.
- **개념 페이지**: 한 문장 정의 → 왜 필요한가 → 핵심 메커니즘 → 트레이드오프 → 등장 사례(`sources`).
- **기술 페이지**: 한 문장 정의 → 주요 특성 → 전형적 사용 사례 → 등장 사례(`sources`).

## 4. 운영 워크플로

### 4-1. Ingest (챕터 1개당)

1. 사용자: `"chNN ingest"`
2. LLM: 해당 챕터 PDF 읽기 → 핵심 takeaway 3-5개 + page화 후보 개념/기술 목록을 한국어 대화로 제시.
3. 사용자: 강조/누락/제외 피드백.
4. LLM:
   a. `wiki/chapters/chNN-*.md` 작성.
   b. 등장한 각 개념 → `wiki/concepts/` 에서 신규 생성 또는 기존 페이지의 `sources[]` 갱신 및 본문 보강.
   c. 등장한 각 기술 → `wiki/tech/` 에서 동일하게.
   d. `index.md` 갱신.
   e. `log.md` 에 `## [YYYY-MM-DD] ingest | chNN: 제목` 항목 append.
   f. `git add -A && git commit -m "ingest: chNN"`.
5. 사용자: Obsidian에서 결과 검토 → 수정 요청 또는 OK.
6. LLM: 수정 반영 후 `git push`.

### 4-2. Query

1. 사용자 질문 → LLM이 `index.md` 먼저 읽고 관련 페이지 식별.
2. 관련 페이지 read → 답변 생성 (citations 포함).
3. 답변이 새 통찰을 담고 있으면 LLM이 "이 결과를 `wiki/concepts/X.md` 로 보존할까요?" 제안.
4. 사용자 승인 시 페이지화 + `index.md` 갱신.
5. `log.md` 에 `## [YYYY-MM-DD] query | 질문 요약` append.
6. 변경사항 있으면 `query:` 프리픽스로 commit + push.

### 4-3. Lint (월 1회 또는 사용자 요청 시)

LLM이 위키 전체를 점검하여 다음을 보고:
- 페이지 간 모순.
- orphan 페이지(백링크 0).
- 본문에서 언급되지만 페이지가 없는 개념·기술.
- stale 클레임(새 챕터가 기존 페이지 내용을 갱신해야 함).
- `lint:` 프리픽스로 commit.

### 4-4. 스코프 가드

- 한 ingest 사이클이 새 페이지 **8개**를 초과하면 LLM이 멈추고 우선순위 협의.
- 한 페이지가 **600단어**를 초과하면 분할 제안.
- Query → 페이지화는 항상 사용자 명시 승인 후.

## 5. Sync 전략

### 5-1. 멀티 디바이스 시나리오
- 회사 맥, 집 맥, 아이폰(Obsidian iOS + Working Copy).
- 모두 같은 GitHub repo를 단일 진실 원천으로 사용.

### 5-2. Obsidian Git 설정
- `auto pull on startup` = ON.
- `auto push interval` = 10분 (또는 수동).
- Commit message template: `vault: {{date}} {{numFiles}} files` (Obsidian 자동 커밋 전용; LLM 커밋은 별도 프리픽스 사용).

### 5-3. 황금 규칙
- 디바이스 전환 시 작업 종료 측에서 반드시 push 확인.
- LLM 세션 시작 시 `git pull --rebase`, 종료 시 commit + push를 CLAUDE.md 에 명시.
- 커밋 프리픽스: `ingest:`, `query:`, `lint:`, `schema:`, `vault:` (Obsidian 자동).

## 6. 첫 사이클(씨앗 사이클) 정책

- 첫 3챕터는 페이지 포맷을 확정짓는 본보기. 사용자가 적극 피드백.
- 매 ingest 후 CLAUDE.md 의 페이지 컨벤션을 필요 시 갱신.
- ch04 이후부터는 LLM 자율성을 점진적으로 늘림.

## 7. 비목표 (Out of scope)

- 임베딩 기반 RAG·벡터 DB 구축. (index.md + Obsidian 검색으로 충분.)
- 자동 PDF 텍스트 추출 파이프라인. (LLM이 ingest 시점에 직접 PDF 읽음.)
- 슬라이드·차트 등 출력 포맷. (필요해질 때 별도 도입.)
- 다국어 본문. (한국어 + 영어 병기 단일 정책.)
- 옛 `~/study/system-design-interview/` 의 bilingual.md 마이그레이션. (전량 버림.)

## 8. 향후 확장 가능성

- Building AI Agents 책에도 같은 패턴을 별도 디렉터리(`~/study/building-ai-agents/`)로 복제.
- 두 책을 가로지르는 통찰이 누적되면 `_shared/meta-wiki/` 도입 검토.
- 위키 규모가 커지면 [qmd](https://github.com/tobi/qmd) 같은 로컬 검색 엔진 도입 검토.

## 9. 성공 기준

- ch01~ch03 ingest 완료 시점에 챕터·개념·기술 페이지가 위키링크로 상호 연결되고, Obsidian graph view가 의미 있는 클러스터를 형성.
- 회사·집·아이폰 세 디바이스에서 충돌 없이 7일 연속 동기화 유지.
- 책 절반 시점에 사용자가 임의의 면접식 질문을 던졌을 때, LLM이 위키만으로 출처 인용된 답변을 5분 내 생성.
