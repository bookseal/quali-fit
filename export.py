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
from collections import OrderedDict

import xlsxwriter

_WORK_PREFIX = re.compile(r"^WORK-")
_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")

# Mapping value area is column D onward (0-based col 3); header is rows 1-4
# (0-based 0-3); data starts at row 5 (0-based 4).
_FIRST_VAL_COL = 3
_DATA_ROW0 = 4


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

    # Group work codes by (대분류, 중분류); each group becomes one sheet.
    groups = OrderedDict()
    for r in sorted(work_codes.itertuples(index=False),
                    key=lambda r: (r.l1, r.l2, r.work_code)):
        groups.setdefault((r.l1, r.l2), []).append(r)

    used_names = set()
    for (l1, l2), wcs in groups.items():
        ws = wb.add_worksheet(_safe_sheet_name(l2, used_names))

        # --- print setup (A3 landscape) ---
        ws.set_landscape()
        ws.set_paper(8)  # 8 = A3
        ws.set_margins(0.3, 0.3, 0.5, 0.5)
        ws.fit_to_pages(1, 0)         # 1 page wide, unlimited tall
        ws.repeat_columns(0, 2)        # A:C on every printed page
        ws.repeat_rows(0, 3)           # header rows 1-4 on every printed page
        ws.freeze_panes(_DATA_ROW0, _FIRST_VAL_COL)

        # --- top-left title + cert info labels ---
        ws.merge_range(0, 0, 2, 2, f"{l1} · {l2}", f_title)
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
            ws.set_column(col, col, 6.5)

        ws.set_column(0, 0, 16)
        ws.set_column(1, 1, 26)
        ws.set_column(2, 2, 8)
        for r in range(4):
            ws.set_row(r, 16)

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

        # --- influence color scale (light -> dark) for at-a-glance reading ---
        if wcs and cert_list:
            ws.conditional_format(
                _DATA_ROW0, _FIRST_VAL_COL,
                _DATA_ROW0 + len(cert_list) - 1, _FIRST_VAL_COL + len(wcs) - 1,
                {
                    "type": "3_color_scale",
                    "min_type": "num", "min_value": 1, "min_color": "#FFFFFF",
                    "mid_type": "num", "mid_value": 3, "mid_color": "#FFD27F",
                    "max_type": "num", "max_value": 5, "max_color": "#F4795B",
                },
            )

    wb.close()
    return buf.getvalue()
