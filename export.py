"""XLSX export for the work-code × cert mapping (issue #34).

Pure module — no Streamlit, no SQL. Given the structured data from
`db.fetch_mapping_grid()`, builds an **A3-landscape** workbook split into one
sheet per 중분류(l2):

  rows    = certs, in holder-count order
  columns = the group's work codes, each with a 4-row stacked header
            (CA-111 / 중분류 / 소분류 / 산정·검증)
  cells   = influence (1-5), blank where no mapping

Tuned for printing: A3 landscape, left cert columns + the 4 header rows are
frozen and repeated on every printed page, fit to one page wide.
"""
import io
import re

import xlsxwriter

_WORK_PREFIX = re.compile(r"^WORK-")
_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")

# Mapping value area is column D onward (0-based col 3); header is rows 1-4
# (0-based 0-3); data starts at row 5 (0-based 4).
_FIRST_VAL_COL = 3
_DATA_ROW0 = 4

# Pack ~13 work codes per sheet so each sheet fills one A3-landscape page.
WORK_CODES_PER_SHEET = 13
# Work-code column width ≈ 4 CJK chars (the 소분류 row is usually ~4 chars).
_WORK_COL_WIDTH = 9
_CHARS_PER_LINE = 4  # at the width above, for wrap-height estimates


def _wrap_height(max_len: int, line: int = 14, pad: int = 3) -> float:
    """Row height to fit `max_len` wrapped CJK chars at _WORK_COL_WIDTH."""
    lines = max(1, -(-max_len // _CHARS_PER_LINE))  # ceil division
    return lines * line + pad


def _short_code(work_code: str) -> str:
    """'WORK-CA-111' -> 'CA-111' (compact print header)."""
    return _WORK_PREFIX.sub("", str(work_code))


def _safe_sheet_name(name: str, used: set) -> str:
    """Excel sheet name: <=31 chars, none of []:*?/\\, unique."""
    s = _BAD_SHEET_CHARS.sub(" ", str(name)).strip()[:31] or "sheet"
    base, i = s, 1
    while s in used:
        suffix = f" ({i})"
        s = base[: 31 - len(suffix)] + suffix
        i += 1
    used.add(s)
    return s


def build_mapping_workbook(certs, work_codes, influence) -> bytes:
    """Return .xlsx bytes. See module docstring for the layout."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})

    f_title = wb.add_format(
        {"bold": True, "font_size": 11, "valign": "vcenter", "align": "left"}
    )
    f_code = wb.add_format({
        "bold": True, "align": "center", "valign": "vcenter",
        "border": 1, "bg_color": "#D9E1F2", "text_wrap": True,
    })
    f_sub = wb.add_format({
        "align": "center", "valign": "vcenter",
        "border": 1, "bg_color": "#EAF0FA", "text_wrap": True,
    })
    f_lbl = wb.add_format({
        "bold": True, "align": "center", "valign": "vcenter",
        "border": 1, "bg_color": "#D9E1F2",
    })
    f_text = wb.add_format({"align": "left", "valign": "vcenter", "border": 1})
    f_num = wb.add_format({"align": "center", "valign": "vcenter", "border": 1})

    cert_list = list(certs.itertuples(index=False))  # cert_code, cert_name, holder_count

    # Pack work codes into fixed-size pages (~13 cols) so each sheet fills one
    # A3 page. Sort by work_code so each page is a contiguous code range; the
    # code prefix encodes the classification, so same-중분류 codes stay adjacent.
    wcs_sorted = sorted(
        work_codes.itertuples(index=False), key=lambda r: r.work_code
    )
    pages = [
        wcs_sorted[i:i + WORK_CODES_PER_SHEET]
        for i in range(0, len(wcs_sorted), WORK_CODES_PER_SHEET)
    ]
    total = len(pages)

    used_names = set()
    for idx, wcs in enumerate(pages, start=1):
        ws = wb.add_worksheet(_safe_sheet_name(f"{idx}쪽", used_names))

        # --- print setup (A3 landscape) ---
        ws.set_landscape()
        ws.set_paper(8)  # 8 = A3
        ws.set_margins(0.3, 0.3, 0.5, 0.5)
        ws.fit_to_pages(1, 0)         # 1 page wide, unlimited tall
        ws.repeat_columns(0, 2)        # A:C on every printed page
        ws.repeat_rows(0, 3)           # header rows 1-4 on every printed page
        ws.freeze_panes(_DATA_ROW0, _FIRST_VAL_COL)

        # --- top-left title + cert info labels ---
        first, last = _short_code(wcs[0].work_code), _short_code(wcs[-1].work_code)
        ws.merge_range(0, 0, 2, 2, f"{idx}/{total}쪽  ·  {first} ~ {last}", f_title)
        ws.write(3, 0, "자격증코드", f_lbl)
        ws.write(3, 1, "자격증명", f_lbl)
        ws.write(3, 2, "보유자수", f_lbl)

        # --- per-work-code stacked header (4 rows) ---
        for j, wc in enumerate(wcs):
            col = _FIRST_VAL_COL + j
            ws.write(0, col, _short_code(wc.work_code), f_code)  # row1: code
            ws.write(1, col, wc.l2, f_sub)                       # row2: 중분류
            ws.write(2, col, wc.l3 or "", f_sub)                 # row3: 소분류
            ws.write(3, col, wc.task_type, f_sub)                # row4: 산정/검증
            ws.set_column(col, col, _WORK_COL_WIDTH)

        ws.set_column(0, 0, 16)
        ws.set_column(1, 1, 26)
        ws.set_column(2, 2, 8)
        # Code & task_type fit one line; 중분류/소분류 may wrap — size those rows
        # to the longest value on this page.
        ws.set_row(0, 15)
        ws.set_row(1, _wrap_height(max(len(w.l2 or "") for w in wcs)))
        ws.set_row(2, _wrap_height(max(len(w.l3 or "") for w in wcs)))
        ws.set_row(3, 15)

        # --- data rows (certs, holder order) ---
        for i, c in enumerate(cert_list):
            row = _DATA_ROW0 + i
            ws.write(row, 0, c.cert_code, f_text)
            ws.write(row, 1, c.cert_name, f_text)
            ws.write_number(row, 2, int(c.holder_count), f_num)
            for j, wc in enumerate(wcs):
                col = _FIRST_VAL_COL + j
                v = influence.get((c.cert_code, wc.work_code))
                if v is None:
                    ws.write_blank(row, col, None, f_num)
                else:
                    ws.write_number(row, col, v, f_num)

    wb.close()
    return buf.getvalue()
