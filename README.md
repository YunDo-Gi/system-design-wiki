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
