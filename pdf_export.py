"""근무표 출력본(PDF) 저장 — 화면의 컬러 그리드를 그대로 인쇄용 PDF로 렌더링."""
from __future__ import annotations
import calendar
from PyQt5.QtGui import QTextDocument
from PyQt5.QtPrintSupport import QPrinter
import database as db

SHIFT_KR = {'D': 'D', 'E': 'E', 'N': 'N', 'O': '휴'}
COLOR_DEFAULTS = {'D': '#6FA8DC', 'E': '#FFCE47', 'N': '#A47BE0', 'O': '#E0E0E0',
                  'sat': '#9FCAF2', 'hol': '#FFAFAF'}
WD_KR = ['월', '화', '수', '목', '금', '토', '일']


def _colors() -> dict:
    cfg = db.get_settings()
    return {k: cfg.get(f'color_{k}', v) for k, v in COLOR_DEFAULTS.items()}


def _esc(s: str) -> str:
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def build_html(year: int, month: int, nurses, teams, schedule) -> str:
    days = calendar.monthrange(year, month)[1]
    holidays = db.get_holidays(year, month)
    c = _colors()
    ncols = 2 + days + 5

    # ── 헤더 행 (이름 + 사번 + 일자 + 집계) ──────────────────────────────────
    th = ['<th>이름</th>', '<th>사번</th>']
    for d in range(1, days + 1):
        wd = calendar.weekday(year, month, d)
        hol = holidays.get(d)
        bg = c['hol'] if (hol or wd == 6) else (c['sat'] if wd == 5 else '#F2F2F2')
        th.append(f'<th style="background-color:{bg}">{d}<br/>{WD_KR[wd]}</th>')
    for lab in ('D합', 'E합', 'N합', '휴합', '근무합'):
        th.append(f'<th style="background-color:#F2F2F2">{lab}</th>')
    header = '<tr>' + ''.join(th) + '</tr>'

    body = []

    def nurse_rows(members):
        for n in members:
            sc = schedule.get(n.id, {})
            cnt = {'D': 0, 'E': 0, 'N': 0, 'O': 0}
            emp = getattr(n, 'emp_no', '') or ''
            tds = [f'<td class="nm">{_esc(n.name)}</td>',
                   f'<td class="nm">{_esc(emp)}</td>']
            for d in range(1, days + 1):
                sh = sc.get(d, 'O')
                cnt[sh] += 1
                tds.append(f'<td style="background-color:{c[sh]}">{SHIFT_KR[sh]}</td>')
            work = cnt['D'] + cnt['E'] + cnt['N']
            for v in (cnt['D'], cnt['E'], cnt['N'], cnt['O'], work):
                tds.append(f'<td>{v}</td>')
            body.append('<tr>' + ''.join(tds) + '</tr>')

    if teams:
        for t in teams:
            members = [n for n in nurses if n.team_id == t.id]
            if not members:
                continue
            body.append(f'<tr><td colspan="{ncols}" class="team" '
                        f'style="background-color:{t.color}">📁 {_esc(t.name)}</td></tr>')
            nurse_rows(members)
        noteam = [n for n in nurses if n.team_id is None]
        if noteam:
            body.append(f'<tr><td colspan="{ncols}" class="team" '
                        f'style="background-color:#EEEEEE">📁 미배정</td></tr>')
            nurse_rows(noteam)
    else:
        nurse_rows(nurses)

    style = (
        '<style>'
        'table { border-collapse: collapse; width: 100%; }'
        'th, td { border: 1px solid #999; text-align: center; font-size: 7pt; padding: 1px; }'
        'td.nm { text-align: left; white-space: nowrap; font-size: 8pt; }'
        'td.team { text-align: left; font-weight: bold; font-size: 8pt; }'
        'h2 { font-size: 13pt; margin: 0 0 6px 0; }'
        '</style>'
    )
    return (f'<html><head>{style}</head><body>'
            f'<h2>{year}년 {month}월 근무표</h2>'
            f'<table>{header}{"".join(body)}</table>'
            f'</body></html>')


def export(year: int, month: int, nurses, teams, schedule, path: str):
    """근무표를 A4 가로 PDF로 저장."""
    doc = QTextDocument()
    doc.setHtml(build_html(year, month, nurses, teams, schedule))

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPrinter.A4)
    printer.setOrientation(QPrinter.Landscape)
    printer.setPageMargins(8, 8, 8, 8, QPrinter.Millimeter)
    doc.print_(printer)
