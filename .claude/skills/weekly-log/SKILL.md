---
name: weekly-log
description: 한 주간 완료된 작업(PR)을 수집해 docs/index.html의 "이번 주·지난 주" 진행에 새 주(週) 블록을 추가하고, 밀려난 주는 docs/history.html로 옮기며, 진행 보드·버전 기록을 갱신한 뒤 브랜치+PR로 올린다. 주간 보고용. "주간 로그", "이번 주 정리", "weekly log" 요청 시 사용.
---

# weekly-log — 주간 진행 갱신

대상 독자는 **비개발자(원장님·관계자)** 다. 화면은 [docs/index.html](../../../docs/index.html)(이번 주·지난 주 + 진행 보드 + 버전 기록)과 [docs/history.html](../../../docs/history.html)(그 이전 주). 형식·원칙은 [CLAUDE.md](../../../CLAUDE.md)를 따른다.

## 쉬운 말 원칙 (중요)
- 화면에 보이는 글에는 **어려운 기술 용어를 쓰지 않는다.** "브랜치/머지/커밋/PR" 같은 말 금지.
  - 이슈 → **할 일** (`<a class="iss" ...>할 일 #N</a>`)
  - PR → **작업** (`<a class="pr" ...>작업 #N</a>`)
  - 배포 화면 → **▶ 화면** (`<a class="live" ...>▶ 이름</a>`)
- **날짜는 곳곳에, 월·일로.** 형식 `6월 15일(월) ~ 6월 21일(일)`. (모두 2026년이라 연도는 생략)
- 아이콘은 크고 명확하게, 뜻이 모호한 이모지는 피한다.

## 절차

1. **대상 주 결정** — 인자가 없으면 가장 최근 월~일 주. 경계의 요일을 파이썬으로 구한다
   (`date.fromisoformat`, `'월화수목금토일'[d.weekday()]`).

2. **그 주 완료된 작업(PR) 수집**:
   ```
   gh pr list --state merged --json number,title,mergedAt,author --jq \
     '[.[] | select(.mergedAt[0:10] >= "<시작>" and .mergedAt[0:10] <= "<끝>")]'
   gh pr view <N> --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'
   ```
   제목/본문에 `#NN`로 참조된 할 일(이슈)도 근거로 포함.

3. **사용자 화면 변경엔 ▶ 화면 링크.** base `https://quali-fit.bit-habit.com`
   - 조직도 `?mode=manage&cat=employee_group&svc=employee`
   - 학력 `…&svc=education` · 매핑 `?mode=manage&cat=work_group&svc=work_code_cert_map` · 추천 `?mode=recommend`
   - 진행 페이지 `https://bookseal.github.io/quali-fit/`
   인프라/문서-내부 변경은 화면 링크 생략. HTML에서 `&`는 `&amp;`.

4. **index.html의 "이번 주·지난 주" 갱신:**
   - 새 블록을 `<div class="week current">`로 맨 위에 넣고, `<span class="wk-tag now">이번 주</span> <범위>` 형식.
   - 직전 "이번 주" 블록 → `class="week"`로 내리고 태그를 `<span class="wk-tag">지난 주</span>`로 바꾼다.
   - 기존 "지난 주" 블록 → **index에서 떼어 history.html의 주간 목록 맨 위로 옮긴다**(태그 없이 날짜 제목만). 즉 index에는 항상 두 주만 남는다.

5. **진행 보드(다음/진행 중/완료) 손보기** — 이번 주에 끝난 일은 "끝난 일" 칸에 `<div class="kanban">`로 추가(제목·쉬운 설명·`완료 날짜`·자세히 링크). 시작/완료로 상태가 바뀐 카드는 칸을 옮긴다.

6. **버전 기록 갱신** — 이번 주에 버전이 올라갔으면 `table.vh`에 행 추가: 버전 · 무엇이 좋아졌나 · **완성한 날**(`M월 D일`). 완성일은 태그 날짜로 확인:
   `git log -1 --format=%ad --date=format:'%m월 %d일' vX.Y.Z`

7. **검증** — `index.html`·`history.html` 파싱 확인, `style.css` 중괄호 균형, 화면 글에 금지 용어(브랜치/머지/커밋/PR)가 없는지 grep.

8. **브랜치 + PR** (main 직접 금지) — `git checkout -b docs/weekly-<시작날짜>`, 커밋(끝에 Co-Authored-By), `gh pr create`. **머지는 사용자에게 맡긴다**(보고 전 검토). 요청 시에만 머지.

## 주의
- 초안 전제 — 보고 전 사람이 문구·강조를 다듬는다.
- 수치/주장은 근거가 있을 때만.
- 이미 그 주 블록이 있으면 새로 만들지 말고 항목을 추가/갱신.
