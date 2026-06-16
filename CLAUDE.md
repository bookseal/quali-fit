# CLAUDE.md — 에이전트 작업 지침

quali-fit: 업무분류 코드로 적합 직원을 **이유와 함께** 추천하는 사내 Streamlit 도구.
계층: 화면(`app.py`) → 데이터(`db.py`) → 계산(`scoring.py`/`validation.py`). `app.py`엔 raw SQL 금지, `db.py`엔 Streamlit import 금지.

## 작업 흐름 (업계표준 — main 직접 커밋 금지)

- **모든 변경은 브랜치 → PR → 머지.** `main`에 직접 커밋하지 않는다. (Pages가 `main/docs`에서 자동 배포되므로, main 직접 커밋 = 리뷰 없는 즉시 공개.)
- 한 PR = 한 가지 목적. 큰 작업은 이슈를 잘게 쪼갠다(epic + 단계별 sub-issue).
- 문서만 바뀐 푸시는 앱 배포가 skip된다(기존 CI 설정).

## 진행 문서 유지 — `docs/index.html` (비개발자/원장님용)

**규칙: PR을 열 때, 그 PR의 작업을 `docs/index.html`의 "주차별 진행 로그" 맨 위 주(主)에 한 항목으로 추가한다.** 이 페이지가 곧 주간 성과보고 자료다(매주 성과보고와 1:1).

각 항목 작성 형식(근거 필수):
- **날짜**: 주 범위에 요일 포함 — `2026.06.15(월) – 06.21(일)`.
- **근거 링크(전부)**: PR과 이슈를 구분해 칩으로 단다.
  - PR: `<a class="pr" href=".../pull/N">PR #N</a>`
  - 이슈: `<a class="iss" href=".../issues/N">이슈 #N</a>`
- **배포 화면**: 사용자에게 보이는 변경이면 배포 deep-link를 단다 — `<a class="live" href="...">▶ 화면명</a>`.
- 협업 시 누가 무엇을 했는지(브랜치/검증/머지) 한 줄로 남긴다.

배포 URL (https://quali-fit.bit-habit.com) deep-link 스킴 (`?mode=&cat=&svc=`):
- 조직도: `?mode=manage&cat=employee_group&svc=employee`
- 학력:   `?mode=manage&cat=employee_group&svc=education`
- 업무–자격증 매핑: `?mode=manage&cat=work_group&svc=work_code_cert_map`
- 추천:   `?mode=recommend`
- 진행 페이지(Pages): https://bookseal.github.io/quali-fit/

> HTML 속성값의 `&`는 `&amp;`로 이스케이프한다.

## 문서 구조

- `README.md` — 한글 랜딩, **링크 2개만**(① 진행 페이지 ② `README.en.md`). 원장님·KIBA용.
- `README.en.md` — 영문 기술 문서(글로벌 개발자용).
- `프로젝트_소개.md` — 한글 입문 설명.
- `docs/` — 정적 HTML/CSS만. **빌드·npm·React 없음**(정적·확실 원칙).

## 버전

`v0.1.0` = 비개발자 문서 정비, `v0.1.1` = 안전 저장·백업(#13, 다음 1순위). v0.0.x 태그는 지나온 기능 단계.
