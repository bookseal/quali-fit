# quali-fit — Explainable Staffing Recommender

An internal web tool that, given a work-classification code, recommends the
best-fit employees **with the reason for each match shown next to the score**.
It started as a real in-house tool for a cost-engineering consultancy and is
being grown into a multi-tenant SaaS. This repo is the **generalized,
synthetic-data version** — no real data or real organization names are
included.

> 📊 **개발 진행 상황 & 로드맵 (비개발자용)** — 한눈에 보는 페이지:
> **<https://bookseal.github.io/quali-fit/>**
> *우리가 일하는 법 · 지금까지 한 일(주차별) · 앞으로 할 일.* 원장님/실무자용 링크입니다.
> (GitHub Pages가 켜지면 위 주소에서 열립니다 — 소스는 [`docs/`](docs/).)

**Status:** active hand-rebuild. Eight phases shipped (v0.0.1 → v0.0.8); the
recommender and CRUD over all six tables are live in Korean. v0.0.9 (matrix
editor for the work-cert mapping) is in flight on the `phase9-matrix-editor`
branch. See the [issues](../../issues) for the live phase checklist and the
[pull requests](../../pulls) for the per-phase self-reviews.

> **AI collaboration, stated up front.** The code is written together with an
> AI agent. My contribution is problem framing, data-model and scoring design,
> trade-off decisions, review, and course corrections. This README, the
> per-phase issues, and the PR self-reviews are the real artifacts — the
> *trace of judgment*, not the raw lines.

## Problem & context

When the firm bids on a project, the proposal must say "we will staff this
work with these people" — with evidence. That was manual. The input data
(employees, education, certifications, work codes) lived in messy CSV files.
The goal: pick a work code and get a ranked list of suitable employees, with
a short, readable **reason per person** (which certificates contributed, with
what weight, with expiry checked).

## What it does today

- Six normalized tables (employee, education, employee↔cert, cert master,
  work-code master, work-code↔cert mapping) with one generic CRUD editor —
  FK dropdowns, derived join columns, auto-generated IDs, atomic save with
  rollback, validation that blocks before SQL.
- **Recommend mode**: pick a work code → see the work code's required certs
  (sorted by influence) → see the ranked employee list with a per-person
  rationale (contributing certs, expired ones flagged, "how scoring works"
  expander).
- **Scoring is explainable, not a black box.** Pure `scoring.py` (no
  Streamlit, no SQL) with unit tests on the math.
  ```
  contribution_per_cert = influence (1–5) × (1 if valid else 0)
  score                 = best_contribution + min(extras × 0.5, 2.0)
  ```
  Best contribution rewards a strong qualifying cert; the capped diversity
  bonus rewards breadth without letting a cert-collector beat a focused
  specialist. Binary expiry keeps "is this cert real right now?"
  interpretable.
- **Korean UI throughout** (table titles, column headers, buttons, toasts),
  but identifiers (URL params, dict keys, df column names) stay English.
  Single translation dict at the top of `app.py`.
- **2-tier nav**: 직원 / 업무분류 / 한국 자격증 목록, with sub-tabs per
  category. Mode and selection both live in the URL (`?mode=…&cat=…&svc=…`
  or `?mode=recommend&wc=…`) so refresh keeps you on the same screen.

## Stack

| Layer | Choice |
|---|---|
| UI / server | Streamlit (single Python process; no separate front-end) |
| Domain | Pure Python (`scoring.py`, `validation.py`) — no Streamlit, no SQL |
| Storage | SQLite (one file; WAL mode; foreign keys enforced) |
| Runtime | Python 3.13 venv, `streamlit run app.py` |

The point of the layering is portability: the same `db` and domain code can
later sit behind FastAPI or another front-end with no rewrite. `db.py` has
no Streamlit import; `app.py` has no raw SQL; the pure modules have neither.

## Version history

Each version is one issue → one branch → one PR (from v0.0.6 onward) → one
tag. Earlier phases (v0.0.2 – v0.0.5) shipped via direct push to `main` and
are intentionally not rewritten — adopting the branch+PR workflow was itself
a deliberate transition documented in #6.

| Version | What landed | Issue | PR |
|---|---|---|---|
| v0.0.1 | venv · Streamlit · rerun model · "hello world" | [#1](../../issues/1) | — |
| v0.0.2 | SQLite schema + CSV seed for 6 tables (idempotent) | [#2](../../issues/2) | — |
| v0.0.3 | Read-only multi-service views; URL-backed selection | [#3](../../issues/3) | — |
| v0.0.4 | CRUD for the `employee` table; `st.data_editor` diff → one transaction | [#4](../../issues/4) | — |
| v0.0.5 | Pure `validation.py`; errors block save, warnings advise | [#5](../../issues/5) | — |
| v0.0.6 | Generic CRUD for all 6 tables; FK dropdowns; derived join columns; auto-IDs | [#6](../../issues/6) | [#7](../../pull/7) |
| v0.0.7 | Explainable scoring service; Manage / Recommend mode toggle; top-3 rationale | [#8](../../issues/8) | [#9](../../pull/9) |
| v0.0.8 | UX rework: 2-tier nav, Korean labels, cert profile in Recommend | [#10](../../issues/10) | [#11](../../pull/11) |
| v0.0.9 | Matrix editor for `work_code_cert_map` (up to 102 × 64 cells) — **in progress** | [#12](../../issues/12) | — |

The roadmap is not preserved — the original v0.0.8 ("safe writes + backup")
was deferred when real-use feedback after v0.0.7 made UX rework higher
priority. The shuffle is documented in #10 rather than hidden, because
reshuffling under feedback is part of the trace of judgment.

## Key engineering decisions

- **Surrogate keys, single source of truth.** Natural keys like `(name,
  dept, title)` were replaced by `employee_id`. The cert↔work-code mapping
  lives in one join table — not duplicated in the cert master.
- **DDL is the single source of truth for schema metadata.** PK columns,
  required columns, and FK targets are read at runtime via `PRAGMA` rather
  than maintained in a parallel Python dict. Adding a column to a table
  doesn't require touching CRUD code.
- **Explainable scoring, not a black box.** Pure functions, fixture-based
  unit tests, per-person rationale rendered in the UI, "how scoring works"
  expander.
- **Identifiers English, display Korean.** Translation dict at the top of
  `app.py`; URLs, dict keys, df column names stay grep-able.
- **Deliberate trade-offs.** SQLite is right-sized for a small org and one
  or two tenants; Postgres would be over-engineering today. The plan
  documents the trigger for each next step (multi-tenant →
  SQLite-per-tenant → auth).
- **Mistakes and recovery.** A past migration accidentally lost three rows;
  they were restored from the timestamped backup, and the lesson became a
  guardrail in the code.

## Roadmap

1. **v0.0.9** — matrix editor for `work_code_cert_map` (in flight).
2. **v0.1.0** — feature parity with the original tool; safe writes + backup
   (the deferred v0.0.8); ADRs in `docs/adr/` for the load-bearing decisions.
3. **v0.2.x** — authentication. Local accounts for the demo; OIDC
   (`st.login`) for production. Auth boundary in its own module.
4. **v0.3.x** — multi-tenant SaaS. One SQLite file per tenant under
   `data/tenants/<id>/`. **Tenant is derived from the authenticated session
   only** (never from a query parameter or client input). Per-tenant
   `config.yaml` for display and weights. A synthetic demo tenant ships
   with the repo.
5. **v0.4.x** — FastAPI in front. Add a REST API in front of the same `db`
   and domain code. The UI stays separate.

Out of scope for now (on purpose): billing, self-serve signup, automatic
tenant provisioning, RBAC, audit logs. Scope control is part of the design.

## Data and privacy (public repo)

- **No real data, no real names, no real organization, ever — not now, not
  in history.** Anonymizing 40 employees with rich attributes is not safe
  (small size + many attributes = re-identifiable). The repo ships synthetic
  CSVs under `Data/` and (planned) a synthetic data generator.
- Real data lives outside the repo (a separate `DATA_DIR`). Only synthetic
  samples and the generator get committed.
- Cleanliness is structural, not a chore: real data never enters the repo,
  so there is nothing to scrub.

## Run

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Initialize SQLite + seed from the synthetic CSVs (idempotent)
.venv/bin/python -c "import db; db.init_db(); db.seed_from_csv(); print(db.count_rows())"

.venv/bin/streamlit run app.py
```

Then open the browser to the URL Streamlit prints. Default landing is
**데이터 관리 → 직원 → 기본정보**; switch to **직원 추천** from the
sidebar to try the recommender.

## How this is built (portfolio intent)

Even solo, the work is run through real artifacts: **one GitHub issue per
decision (context, options chosen, reason) → branch → PR with a self-review
(risks considered, alternatives rejected, verification) → meaningful merge
→ tag**. From v0.0.6 onward every phase has a public self-review PR; the
PR template lives at `.github/pull_request_template.md`. Major forks will
get an ADR in `docs/adr/`. The point is not commit count — it is a trace
of judgment that can be explained out loud.
