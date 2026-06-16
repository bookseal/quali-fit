---
name: weekly-log
description: 한 주간 머지된 PR을 수집해 docs/index.html 주차별 진행 로그에 근거(PR/이슈 링크·배포 deep-link)와 함께 새 주(週) 블록을 추가하고 브랜치+PR로 올린다. 주간 성과보고용. "주간 로그", "이번 주 정리", "weekly log" 요청 시 사용.
---

# weekly-log — 주차별 진행 로그 갱신

`docs/index.html`의 "주차별 진행 로그"는 매주 성과보고와 1:1로 대응한다(비개발자/원장님용). 이 스킬은 한 주의 머지된 PR을 근거와 함께 새 `.week` 블록으로 추가한다. 형식 규칙은 [CLAUDE.md](../../../CLAUDE.md)를 따른다.

## 입력
- 대상 주 범위. 인자가 없으면 **가장 최근 월~일 주**를 기본으로 한다(예: 오늘이 화요일이면 이번 주 월요일~일요일). 인자로 `2026-06-15..2026-06-21` 형태를 받으면 그 범위를 쓴다.

## 절차

1. **대상 주 결정** — 월요일~일요일 범위와 각 경계의 요일을 구한다.
   날짜/요일 계산은 파이썬으로(예: `date.fromisoformat`, `'월화수목금토일'[d.weekday()]`).

2. **그 주 머지된 PR 수집** (정렬: 오래된→최신, 또는 묶어서):
   ```
   gh pr list --state merged --json number,title,mergedAt,author --jq \
     '[.[] | select(.mergedAt[0:10] >= "<시작>" and .mergedAt[0:10] <= "<끝>")]'
   ```
   각 PR의 닫은 이슈:
   ```
   gh pr view <N> --json closingIssuesReferences --jq '[.closingIssuesReferences[].number]'
   ```
   PR 본문/제목에 `#NN`로 참조된 이슈도 근거로 포함한다.

3. **사용자 화면 변경 판별 → 배포 deep-link 부여.** base: `https://quali-fit.bit-habit.com`
   - 조직도: `?mode=manage&cat=employee_group&svc=employee`
   - 학력:   `?mode=manage&cat=employee_group&svc=education`
   - 업무–자격증 매핑: `?mode=manage&cat=work_group&svc=work_code_cert_map`
   - 추천:   `?mode=recommend`
   - 진행 페이지(Pages): `https://bookseal.github.io/quali-fit/`
   인프라/CI/문서-내부 변경은 화면 링크를 생략한다. `&`는 HTML에서 `&amp;`로 이스케이프.

4. **새 `.week` 블록 생성**, 기존 최신 주 위에 삽입한다. 직전까지의 "맨 위 주"가 더 이상 현재 주가 아니면 그 블록의 `class="week current"`를 `class="week"`로 내리고, 새 블록을 `class="week current"`로 맨 위에 둔다. 형식:
   ```html
   <div class="week current">
     <h3>요약 제목 <span class="range">2026.MM.DD(요일) – MM.DD(요일)</span></h3>
     <ul>
       <li>한 일 설명 <span class="ver-tag">vX.Y.Z</span>
         <span class="refs">
           <a class="pr"  href=".../pull/N">PR #N</a>
           <a class="iss" href=".../issues/M">이슈 #M</a>
           <a class="live" href="https://quali-fit.bit-habit.com/?...">▶ 화면명</a>
         </span>
       </li>
     </ul>
   </div>
   ```
   협업이 있었으면 누가(브랜치)·검증·머지를 한 줄로 남긴다.

5. **검증** — `python -c "import html.parser; html.parser.HTMLParser().feed(open('docs/index.html').read())"`로 파싱 확인. 모든 PR/이슈 링크가 실제 번호와 맞는지 점검.

6. **브랜치 + PR** (main 직접 커밋 금지):
   - `git checkout -b docs/weekly-<시작날짜>`
   - `docs/index.html` 커밋(커밋 메시지 끝에 Co-Authored-By 트레일러).
   - `gh pr create`로 PR 생성. **머지는 사용자에게 맡긴다**(보고 전 문구 검토용). 요청 시에만 머지.

## 주의
- 초안임을 전제로 하고, 보고 전 사람이 문구·강조를 다듬는다.
- 수치/주장(예: "직원 N명")은 근거가 있을 때만 적는다.
- 이미 그 주 블록이 있으면 새로 만들지 말고 항목을 **추가/갱신**한다.
