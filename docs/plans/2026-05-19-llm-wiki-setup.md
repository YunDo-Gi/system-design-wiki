# LLM Wiki 셋업 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `~/study/system-design/` 에 LLM Wiki 패턴의 골격(디렉터리, schema, index, log, raw PDF)을 구축하고 GitHub와 동기화한다. 본 plan 완료 시점에는 ch01 ingest를 시작할 수 있는 상태가 된다.

**Architecture:** 3-layer (raw/wiki/schema) + index.md + log.md. 모든 파일은 마크다운, Obsidian vault로 동작, GitHub private repo로 멀티 디바이스 동기화. 본 plan은 코드를 작성하지 않고 설정 파일과 디렉터리 골격만 만든다.

**Tech Stack:** macOS, git, GitHub, Obsidian, Markdown.

**Spec:** `docs/specs/2026-05-19-llm-wiki-design.md`

**작업 디렉터리:** 모든 명령은 `~/study/system-design/` 에서 실행.

---

## File Structure

본 plan에서 생성/수정할 파일 목록:

```
~/study/system-design/
├── .gitignore                              ← Task 1 생성
├── CLAUDE.md                               ← Task 4 생성 (schema, LLM 운영 규칙)
├── README.md                               ← Task 5 생성 (사람용 안내)
├── index.md                                ← Task 6 생성 (카탈로그 스켈레톤)
├── log.md                                  ← Task 7 생성 (활동 로그 스켈레톤)
├── raw/
│   ├── .gitkeep                            ← Task 2 생성
│   └── SystemDesignInterview.pdf           ← Task 3 복사
└── wiki/
    ├── chapters/.gitkeep                   ← Task 2 생성
    ├── concepts/.gitkeep                   ← Task 2 생성
    └── tech/.gitkeep                       ← Task 2 생성
```

각 파일 책임:
- `.gitignore`: macOS·Obsidian·OS 잡파일 제외.
- `CLAUDE.md`: LLM이 매 세션 읽을 위키 운영 규칙. **가장 중요.**
- `README.md`: 사람(본인+미래의 협업자)에게 위키 사용법 안내.
- `index.md`: LLM이 query 시점 가장 먼저 읽는 카탈로그.
- `log.md`: 시간순 활동 기록(ingest/query/lint).
- `raw/`: 원본 자료. 본 plan에서는 PDF 1권만.
- `wiki/{chapters,concepts,tech}/`: LLM이 페이지를 채워나갈 빈 폴더.

---

## Task 1: .gitignore 생성

**Files:**
- Create: `~/study/system-design/.gitignore`

- [ ] **Step 1: .gitignore 작성**

파일 내용:

```gitignore
# macOS
.DS_Store
.AppleDouble
.LSOverride

# Obsidian — workspace는 디바이스마다 다르므로 동기화 제외
.obsidian/workspace
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache

# Editor backups
*.swp
*~

# Python/Node 잡파일 (혹시 모를 도구 도입 대비)
__pycache__/
node_modules/
.venv/
```

- [ ] **Step 2: 작성 확인**

```bash
cat ~/study/system-design/.gitignore
```

Expected: 위 내용 그대로 출력.

- [ ] **Step 3: 커밋**

```bash
cd ~/study/system-design
git add .gitignore
git commit -m "chore: .gitignore 추가 (macOS, Obsidian workspace 제외)"
```

---

## Task 2: 디렉터리 골격 생성

**Files:**
- Create: `~/study/system-design/raw/.gitkeep`
- Create: `~/study/system-design/wiki/chapters/.gitkeep`
- Create: `~/study/system-design/wiki/concepts/.gitkeep`
- Create: `~/study/system-design/wiki/tech/.gitkeep`

빈 디렉터리는 git이 추적하지 않으므로 `.gitkeep` 으로 골격을 잡는다.

- [ ] **Step 1: 디렉터리 생성 + .gitkeep 작성**

```bash
cd ~/study/system-design
mkdir -p raw wiki/chapters wiki/concepts wiki/tech
touch raw/.gitkeep wiki/chapters/.gitkeep wiki/concepts/.gitkeep wiki/tech/.gitkeep
```

- [ ] **Step 2: 구조 확인**

```bash
cd ~/study/system-design && find raw wiki -type f
```

Expected:
```
raw/.gitkeep
wiki/chapters/.gitkeep
wiki/concepts/.gitkeep
wiki/tech/.gitkeep
```

- [ ] **Step 3: 커밋**

```bash
cd ~/study/system-design
git add raw wiki
git commit -m "chore: raw/, wiki/{chapters,concepts,tech}/ 디렉터리 골격 생성"
```

---

## Task 3: 원본 PDF 를 raw/ 로 복사

**Files:**
- Copy: `~/Downloads/SystemDesignInterview.pdf` → `~/study/system-design/raw/SystemDesignInterview.pdf`

원본은 Downloads에 두고 위키 안으로는 **복사**. (원본 분실 방지 + 위키만으로 자립)

- [ ] **Step 1: PDF 복사**

```bash
cp ~/Downloads/SystemDesignInterview.pdf ~/study/system-design/raw/SystemDesignInterview.pdf
```

- [ ] **Step 2: 복사 확인 (크기 비교)**

```bash
ls -la ~/Downloads/SystemDesignInterview.pdf ~/study/system-design/raw/SystemDesignInterview.pdf
```

Expected: 두 파일 크기가 동일.

- [ ] **Step 3: 커밋**

```bash
cd ~/study/system-design
git add raw/SystemDesignInterview.pdf
git commit -m "raw: Alex Xu, System Design Interview 2nd ed PDF 추가"
```

⚠️ **참고**: PDF가 GitHub 100MB 제한 초과 시 push 실패할 수 있음. 그 경우 Task 12 에서 별도 처리(이 PDF는 .gitignore 추가 후 로컬에만 보관).

---

## Task 4: CLAUDE.md (schema) 작성

**Files:**
- Create: `~/study/system-design/CLAUDE.md`

이 plan에서 가장 중요한 파일. 향후 모든 LLM 세션이 이 파일을 읽고 위키를 운영한다.

- [ ] **Step 1: CLAUDE.md 작성**

파일 내용:

````markdown
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

### 4-2. Ingest (`사용자가 "chNN ingest" 요청`)

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
````

- [ ] **Step 2: 작성 확인**

```bash
wc -l ~/study/system-design/CLAUDE.md && head -20 ~/study/system-design/CLAUDE.md
```

Expected: 줄 수 100 이상, 상단에 "# System Design Wiki — LLM 운영 규칙" 헤더.

- [ ] **Step 3: 커밋**

```bash
cd ~/study/system-design
git add CLAUDE.md
git commit -m "schema: CLAUDE.md — 위키 운영 규칙 작성"
```

---

## Task 5: README.md 작성

**Files:**
- Create: `~/study/system-design/README.md`

- [ ] **Step 1: README.md 작성**

파일 내용:

```markdown
# System Design Wiki

Alex Xu, *System Design Interview — An Insider's Guide, 2nd Edition* 학습용 개인 위키.  
Andrej Karpathy 가 제안한 **LLM Wiki** 패턴 적용 — LLM이 챕터를 ingest 할 때마다 챕터 요약·개념·기술 페이지를 점진적으로 갱신하여 누적형 지식 베이스를 만든다.

## 디렉터리 구조

```
raw/           원본 자료 (PDF 등). 읽기 전용.
wiki/
  chapters/    챕터 요약 (chNN-*.md)
  concepts/    개념·패턴 페이지
  tech/        기술·컴포넌트 페이지
index.md       전체 페이지 카탈로그
log.md         시간순 활동 기록
CLAUDE.md      LLM 운영 매뉴얼 (페이지 컨벤션, 워크플로)
docs/
  specs/       설계 문서
  plans/       구현 계획
```

## 사용법

### LLM 세션 시작

이 디렉터리를 작업 디렉터리로 LLM 에이전트(Claude Code 등)를 실행하면 `CLAUDE.md` 가 자동 로드된다.

### 챕터 ingest

```
"ch01 ingest"
```

LLM이 PDF 해당 챕터를 읽고 takeaway·후보 페이지 목록을 제시 → 피드백 → 페이지 작성 → commit.

### 질문하기

```
"consistent hashing 이 면접에서 어떻게 자주 나오나"
```

LLM이 `index.md` 부터 시작해 관련 페이지를 종합해 답변. 새 통찰이면 페이지화 제안.

### 정합성 점검

```
"lint"
```

모순·orphan·누락 페이지 보고.

## Obsidian 사용

이 디렉터리 자체를 Obsidian Vault로 열면 위키링크(`[[slug]]`)·그래프 뷰·백링크가 즉시 작동. 자세한 세팅 가이드는 `docs/specs/2026-05-19-llm-wiki-design.md` 섹션 5 참고.

## 동기화

GitHub private repo(`github.com:YunDo-Gi/system-design-wiki`)로 회사·집·아이폰 동기화. 디바이스 전환 시 push 확인 필수.
```

- [ ] **Step 2: 커밋**

```bash
cd ~/study/system-design
git add README.md
git commit -m "docs: README.md — 위키 개요 및 사용법"
```

---

## Task 6: index.md 스켈레톤 작성

**Files:**
- Create: `~/study/system-design/index.md`

비어 있는 카탈로그를 만든다. 이후 ingest 때마다 LLM이 갱신.

- [ ] **Step 1: index.md 작성**

파일 내용:

```markdown
# System Design Wiki — Index

> Alex Xu, *System Design Interview 2nd ed.* 기반 개인 위키
> 마지막 갱신: 2026-05-19 (initial)

## Chapters (진도)

- [ ] ch01 — (미 ingest)
- [ ] ch02 — (미 ingest)
- [ ] ch03 — (미 ingest)

## Concepts (개념)

_아직 없음. 첫 ingest 후 채워짐._

## Tech (기술)

_아직 없음. 첫 ingest 후 채워짐._

---

## 갱신 규칙

LLM은 ingest/query/lint 후 본 파일을 갱신한다. 각 항목 포맷:

```
- [[slug]] — 한 줄 요약 (등장 챕터)
```

가나다순(한글)·알파벳순(영문) 혼합 정렬은 카테고리 안에서 LLM이 판단.
```

- [ ] **Step 2: 커밋**

```bash
cd ~/study/system-design
git add index.md
git commit -m "docs: index.md 스켈레톤 (Chapters/Concepts/Tech 빈 카탈로그)"
```

---

## Task 7: log.md 스켈레톤 작성

**Files:**
- Create: `~/study/system-design/log.md`

- [ ] **Step 1: log.md 작성**

파일 내용:

```markdown
# Activity Log

> Append-only. 각 항목 헤더 포맷: `## [YYYY-MM-DD] {ingest|query|lint|schema} | 짧은 제목`
> 최근 활동만 보고 싶으면: `grep "^## \[" log.md | tail -10`

## [2026-05-19] schema | 위키 골격 셋업

- raw/, wiki/{chapters,concepts,tech}/ 디렉터리 생성
- CLAUDE.md, README.md, index.md, log.md 초기 작성
- raw/SystemDesignInterview.pdf 추가
- GitHub: github.com/YunDo-Gi/system-design-wiki 동기화 시작
```

- [ ] **Step 2: 커밋**

```bash
cd ~/study/system-design
git add log.md
git commit -m "docs: log.md 시작 (셋업 항목 기록)"
```

---

## Task 8: 전체 구조 검증

- [ ] **Step 1: 디렉터리 트리 확인**

```bash
cd ~/study/system-design && find . -type f -not -path './.git/*' -not -path './.obsidian/*' | sort
```

Expected:
```
./.gitignore
./CLAUDE.md
./README.md
./docs/plans/2026-05-19-llm-wiki-setup.md
./docs/specs/2026-05-19-llm-wiki-design.md
./index.md
./log.md
./raw/.gitkeep
./raw/SystemDesignInterview.pdf
./wiki/chapters/.gitkeep
./wiki/concepts/.gitkeep
./wiki/tech/.gitkeep
```

- [ ] **Step 2: git 상태 확인**

```bash
cd ~/study/system-design && git status && git log --oneline
```

Expected: `working tree clean`, 그리고 8개 안팎의 커밋 로그.

---

## Task 9: GitHub 에 push (PDF 크기 분기 처리)

PDF가 GitHub 100MB 제한 안이면 그대로 push. 초과면 PDF 만 untrack 후 push.

- [ ] **Step 1: PDF 크기 확인**

```bash
ls -lh ~/study/system-design/raw/SystemDesignInterview.pdf
```

크기를 기록.

- [ ] **Step 2: push 시도**

```bash
cd ~/study/system-design && git push
```

- **성공**: Step 4 로 진행 (Task 9 종료, Task 10 으로).
- **실패 (large file 에러)**: Step 3 로 진행.

- [ ] **Step 3: PDF 가 100MB 초과인 경우 untrack 처리**

PDF는 로컬에만 두고 git 추적 제외.

```bash
cd ~/study/system-design
git rm --cached raw/SystemDesignInterview.pdf
echo "raw/SystemDesignInterview.pdf" >> .gitignore
git add .gitignore
git commit -m "chore: 대용량 PDF 는 .gitignore (각 디바이스에서 별도 배치)"
git push
```

⚠️ 이 경로를 탔다면 회사 맥·집 맥 각각에 PDF 를 수동 복사해야 한다. README.md 에 그 사실을 한 줄 추가:

```bash
cd ~/study/system-design
# README.md 의 "## 동기화" 섹션 끝에 추가:
#   참고: raw/SystemDesignInterview.pdf 는 git 미포함. 각 디바이스에 수동 복사 필요.
```

(수동 편집 후) `git add README.md && git commit -m "docs: README — PDF 수동 배치 안내" && git push`

- [ ] **Step 4: push 결과 확인**

```bash
cd ~/study/system-design && git log --oneline origin/main..HEAD
```

Expected: 빈 출력 (로컬과 원격이 동일).

---

## Task 10: Obsidian 설정 적용 (수동 단계, 사용자 액션)

이 task 는 GUI 작업이므로 사용자가 직접 수행한다. LLM은 진행 여부만 확인.

- [ ] **Step 1: Obsidian 으로 vault 열기**

이미 `.obsidian/` 폴더가 존재한다면 vault 가 등록된 상태. Obsidian 앱 실행 → "Open folder as vault" → `~/study/system-design/` 선택.

- [ ] **Step 2: 핵심 Settings 적용**

Obsidian 앱 안에서:

- Settings → **Files and links**:
  - "New link format" → `Shortest path when possible`
  - "Use [[Wikilinks]]" → **ON**
  - "Default location for new attachments" → `In subfolder under current folder`
  - "Attachment folder path" → `raw/assets`
- Settings → **Editor**:
  - "Default editing mode" → `Source mode`

- [ ] **Step 3: Community plugins 활성화 + Obsidian Git 설치**

- Settings → **Community plugins** → "Turn on community plugins".
- Browse → "**Obsidian Git**" 검색 → Install → Enable.
- Settings → Obsidian Git:
  - "Vault backup interval (minutes)" → `10` (또는 `0` 으로 두면 수동만)
  - "Auto pull on startup" → **ON**
  - "Commit message" → `vault: {{date}} {{numFiles}} files`

- [ ] **Step 4: Graph view 동작 확인**

좌측 사이드바의 그래프 아이콘 클릭 → 빈 그래프 표시되면 정상 (페이지가 아직 없음).

- [ ] **Step 5: 설정 변경분 commit + push**

Obsidian 설정 변경으로 `.obsidian/` 하위 파일이 변경됐을 수 있다.

```bash
cd ~/study/system-design && git status
```

변경 파일이 있으면:

```bash
cd ~/study/system-design
git add .obsidian
git commit -m "chore: Obsidian 기본 설정 + Obsidian Git 플러그인 활성화"
git push
```

---

## Task 11: 동기화 동작 검증 (회사·집 시나리오 시뮬)

GitHub 동기화가 실제로 작동하는지 가벼운 라운드트립 테스트.

- [ ] **Step 1: 더미 변경 + push**

```bash
cd ~/study/system-design
echo "" >> log.md
echo "## [2026-05-19] schema | sync 동작 검증" >> log.md
echo "" >> log.md
echo "- 더미 커밋으로 회사↔집 라운드트립 테스트." >> log.md
git add log.md
git commit -m "schema: sync 검증용 log 항목 추가"
git push
```

- [ ] **Step 2: GitHub 웹에서 확인**

브라우저에서 `https://github.com/YunDo-Gi/system-design-wiki` 접속 → 가장 최근 커밋이 방금 만든 것인지 확인. (이 step 은 사용자가 직접 확인.)

- [ ] **Step 3: 다른 디바이스 (집 맥 또는 회사 맥) 에서 clone 또는 pull**

신규 디바이스라면:

```bash
mkdir -p ~/study
cd ~/study
git clone git@github.com:YunDo-Gi/system-design-wiki.git system-design
```

기존 디바이스라면:

```bash
cd ~/study/system-design && git pull --rebase
```

방금 만든 log 항목이 보이면 동기화 성공.

---

## Task 12: 최종 확인 + 다음 단계 예고

- [ ] **Step 1: 최종 트리 + 커밋 로그**

```bash
cd ~/study/system-design && find . -type f -not -path './.git/*' -not -path './.obsidian/*' | sort && echo "---" && git log --oneline
```

Expected: Task 8 의 트리와 일치, 커밋이 시간순으로 정렬.

- [ ] **Step 2: CLAUDE.md 가 정상 로드되는지 한 줄 테스트**

```bash
cd ~/study/system-design && head -3 CLAUDE.md
```

Expected: `# System Design Wiki — LLM 운영 규칙` 라인이 첫 헤더.

- [ ] **Step 3: 첫 ingest 예고**

본 plan 완료 후 사용자에게 안내:

> 셋업 완료. 다음 세션에서 `~/study/system-design/` 에서 Claude Code 를 켜고  
> **"ch01 ingest"** 라고 입력하면 LLM 이 PDF ch01 을 읽고 takeaway·후보 페이지 목록을 보고합니다.  
> 첫 3챕터는 페이지 포맷 본보기 단계라 결과를 적극적으로 검토해 주세요 — 그 피드백이 CLAUDE.md 의 컨벤션 섹션을 다듬는 데 반영됩니다.

---

## 종료 조건

- 12개 task 모두 체크박스 완료.
- `~/study/system-design/` 의 모든 파일이 GitHub origin/main 과 동기화됨.
- Obsidian 으로 vault 가 열리며 graph view 가 동작.
- 다음 명령으로 ch01 ingest 시작 가능.
