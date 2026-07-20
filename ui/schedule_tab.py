"""스케줄 탭 — 월별 그리드 (간호사 × 날짜)."""
import calendar
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox,
    QProgressDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QBrush
import database as db
import scheduler
import excel_export
import pdf_export


class _GenWorker(QThread):
    """스케줄 생성을 백그라운드에서 실행 (UI가 얼지 않게).

    OR-Tools 솔버는 메인 스레드가 아닌 곳에서 돌리면 세그폴트가 나므로,
    앱 시작 시 띄워둔 상주 솔버 프로세스에 계산을 맡기고, 이 QThread는 결과만
    폴링한다. 중지(cancel) 시 워커 프로세스를 종료해 풀이를 즉시 끊는다.
    """
    done     = pyqtSignal(dict)
    failed   = pyqtSignal(str)
    canceled = pyqtSignal()

    def __init__(self, year, month):
        super().__init__()
        self.year, self.month = year, month
        self._cancel = False

    def cancel(self):
        """UI 스레드에서 호출. 취소 플래그를 세우고 솔버 프로세스를 종료한다."""
        self._cancel = True
        scheduler.cancel_generate()

    def run(self):
        import queue
        scheduler._dbg('GENWORKER: run 시작')
        try:
            scheduler.submit_generate(self.year, self.month)
        except Exception as e:               # noqa: BLE001
            scheduler._dbg('GENWORKER: submit 예외 %r' % e)
            self.failed.emit(f'생성 오류: {e}')
            return
        waited = 0.0
        while True:
            if self._cancel:
                self.canceled.emit()
                return
            try:
                tag, payload = scheduler.poll_result(0.2)
            except queue.Empty:
                waited += 0.2
                if waited % 2 < 0.2:
                    scheduler._dbg('GENWORKER: 결과 대기중 %.0f초' % waited)
                continue                     # 아직 계산 중 — 다시 대기
            except Exception as e:           # noqa: BLE001
                if self._cancel:
                    self.canceled.emit()
                    return
                self.failed.emit(f'생성 오류: {e}')
                return
            break
        scheduler._dbg('GENWORKER: 결과 수신 tag=%s' % tag)
        if self._cancel:
            self.canceled.emit()
            return
        if tag == 'ok':
            self.done.emit(payload)
        else:                                # 'nosol' | 'err'
            self.failed.emit(payload)

SHIFT_CYCLE    = ['D', 'E', 'N', 'O']
SHIFT_KR       = {'D': 'D', 'E': 'E', 'N': 'N', 'O': '휴'}
COLOR_DEFAULTS = {'D':'#6FA8DC','E':'#FFCE47','N':'#A47BE0','O':'#E0E0E0',
                  'sat':'#9FCAF2','hol':'#FFAFAF'}
WD_KR          = ['월', '화', '수', '목', '금', '토', '일']


def _load_colors():
    cfg = db.get_settings()
    return {k: QColor(cfg.get(f'color_{k}', v)) for k, v in COLOR_DEFAULTS.items()}


class ScheduleTab(QWidget):
    def __init__(self):
        super().__init__()
        from datetime import date
        today = date.today()
        self.year  = today.year
        self.month = today.month
        self._schedule = {}  # {nurse_id: {day: shift}}
        self._nurses   = []
        self._teams    = []
        self._progress = None
        self._worker   = None
        self._row_nurse_map = {}  # visual row → nurse (skips header rows)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ── 상단 컨트롤 ──────────────────────────────────────────────────────
        top = QHBoxLayout()
        btn_prev = QPushButton('◀')
        btn_prev.setFixedWidth(36)
        btn_prev.clicked.connect(self._prev_month)

        self.lbl_month = QLabel()
        self.lbl_month.setAlignment(Qt.AlignCenter)
        self.lbl_month.setFont(QFont('', 13, QFont.Bold))

        btn_next = QPushButton('▶')
        btn_next.setFixedWidth(36)
        btn_next.clicked.connect(self._next_month)

        self._gen_btn = QPushButton('🔄 자동 생성')
        btn_gen = self._gen_btn
        btn_gen.clicked.connect(self._auto_generate)

        btn_save = QPushButton('💾 저장')
        btn_save.clicked.connect(self._save)

        btn_excel = QPushButton('📊 엑셀 출력')
        btn_excel.clicked.connect(self._export_excel)

        btn_pdf = QPushButton('🖨️ 출력본(PDF)')
        btn_pdf.clicked.connect(self._export_pdf)

        top.addWidget(btn_prev)
        top.addWidget(self.lbl_month, 1)
        top.addWidget(btn_next)
        top.addStretch()
        top.addWidget(btn_gen)
        top.addWidget(btn_save)
        top.addWidget(btn_excel)
        top.addWidget(btn_pdf)
        layout.addLayout(top)

        # ── 범례 (동적 — refresh()에서 갱신) ────────────────────────────────
        self._legend_layout = QHBoxLayout()
        self._legend_labels = {}
        for key, label in [('D','D (낮)'),('E','E (저녁)'),('N','N (밤)'),('O','휴')]:
            lbl = QLabel(f'  {label}  ')
            lbl.setStyleSheet('border:1px solid #ccc; border-radius:3px;')
            self._legend_labels[key] = lbl
            self._legend_layout.addWidget(lbl)
        self._legend_layout.addStretch()
        layout.addLayout(self._legend_layout)

        # ── 테이블 ───────────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.cellDoubleClicked.connect(self._toggle_shift)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(24)
        layout.addWidget(self.table)

        # ── 하단 요약 ─────────────────────────────────────────────────────────
        self.lbl_summary = QLabel()
        layout.addWidget(self.lbl_summary)

    def refresh(self):
        self._nurses   = db.get_nurses()
        self._teams    = db.get_teams()
        self._schedule = db.get_schedule(self.year, self.month)
        # 범례 색상 갱신
        colors = _load_colors()
        for key, lbl in self._legend_labels.items():
            lbl.setStyleSheet(
                f'background:{colors[key].name()}; border:1px solid #ccc; border-radius:3px;'
            )
        self._render()

    def _render(self):
        self.lbl_month.setText(f'{self.year}년 {self.month}월')
        days = calendar.monthrange(self.year, self.month)[1]
        weekdays = [calendar.weekday(self.year, self.month, d) for d in range(1, days+1)]
        colors   = _load_colors()
        holidays = db.get_holidays(self.year, self.month)
        total_cols = days + 5  # days + D합/E합/N합/휴합/근무합

        # ── 팀별 행 순서 구성 ─────────────────────────────────────────────────
        # rows: ('header', team) | ('nurse', nurse)
        rows = []
        if self._teams:
            for team in self._teams:
                members = [n for n in self._nurses if n.team_id == team.id]
                if members:
                    rows.append(('header', team))
                    rows.extend(('nurse', n) for n in members)
            no_team = [n for n in self._nurses if n.team_id is None]
            if no_team:
                rows.append(('header', None))  # 미배정 그룹
                rows.extend(('nurse', n) for n in no_team)
        else:
            rows.extend(('nurse', n) for n in self._nurses)

        self._row_nurse_map = {}
        col_labels = [str(d) for d in range(1, days+1)] + ['D합', 'E합', 'N합', '휴합', '근무합']
        self.table.setRowCount(len(rows))
        self.table.setColumnCount(total_cols)
        self.table.setHorizontalHeaderLabels(col_labels)

        # 날짜 열은 균일 고정 폭, 집계열만 내용맞춤.
        # (팀 헤더가 0번 열을 span 해서 ResizeToContents가 첫 열만 넓히는 문제 방지)
        hdr = self.table.horizontalHeader()
        for i in range(days):
            hdr.setSectionResizeMode(i, QHeaderView.Fixed)
            self.table.setColumnWidth(i, 28)
        for i in range(days, total_cols):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        v_labels = []
        for kind, obj in rows:
            if kind == 'header':
                v_labels.append('')
            else:
                emp = getattr(obj, 'emp_no', '') or ''
                v_labels.append(f'{obj.name}  {emp}' if emp else obj.name)
        self.table.setVerticalHeaderLabels(v_labels)

        # 헤더 요일 색상
        for d_idx in range(days):
            wd    = weekdays[d_idx]
            d     = d_idx + 1
            hname = holidays.get(d, '')
            label = f'{d}\n{WD_KR[wd]}' + (f'\n{hname[:4]}' if hname else '')
            item  = self.table.horizontalHeaderItem(d_idx)
            if item:
                item.setText(label)
                if hname or wd == 6:
                    item.setBackground(QBrush(colors['hol']))
                elif wd == 5:
                    item.setBackground(QBrush(colors['sat']))

        # 셀 채우기
        for row_idx, (kind, obj) in enumerate(rows):
            if kind == 'header':
                # 팀 헤더 행: 전체 열 스팬
                team = obj
                label = f'  📁 {team.name}' if team else '  📁 미배정'
                bg    = QColor(team.color) if team else QColor('#EEEEEE')
                header_item = QTableWidgetItem(label)
                header_item.setBackground(QBrush(bg))
                header_item.setFont(QFont('', 9, QFont.Bold))
                header_item.setFlags(Qt.ItemIsEnabled)  # 클릭/편집 불가
                self.table.setItem(row_idx, 0, header_item)
                self.table.setSpan(row_idx, 0, 1, total_cols)
                self.table.setRowHeight(row_idx, 20)
            else:
                nurse = obj
                self._row_nurse_map[row_idx] = nurse
                nurse_sched = self._schedule.get(nurse.id, {})
                counts = {'D': 0, 'E': 0, 'N': 0, 'O': 0}
                for d in range(1, days + 1):
                    shift = nurse_sched.get(d, 'O')
                    counts[shift] += 1
                    cell = QTableWidgetItem(SHIFT_KR[shift])
                    cell.setTextAlignment(Qt.AlignCenter)
                    cell.setBackground(QBrush(colors[shift]))
                    self.table.setItem(row_idx, d - 1, cell)
                for i, key in enumerate(['D', 'E', 'N', 'O']):
                    ci = QTableWidgetItem(str(counts[key]))
                    ci.setTextAlignment(Qt.AlignCenter)
                    self.table.setItem(row_idx, days + i, ci)
                work = counts['D'] + counts['E'] + counts['N']
                cw = QTableWidgetItem(str(work))
                cw.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_idx, days + 4, cw)

        self._update_summary(days)

    def _update_summary(self, days):
        total_d = total_e = total_n = 0
        for nurse in self._row_nurse_map.values():
            ns = self._schedule.get(nurse.id, {})
            for d in range(1, days + 1):
                s = ns.get(d, 'O')
                if s == 'D':   total_d += 1
                elif s == 'E': total_e += 1
                elif s == 'N': total_n += 1
        self.lbl_summary.setText(
            f'  전체 배정 — D: {total_d}  E: {total_e}  N: {total_n}'
        )

    def _toggle_shift(self, row, col):
        days = calendar.monthrange(self.year, self.month)[1]
        if col >= days:
            return
        nurse = self._row_nurse_map.get(row)
        if nurse is None:  # 헤더 행 클릭 무시
            return
        day = col + 1
        ns  = self._schedule.setdefault(nurse.id, {})
        cur = ns.get(day, 'O')
        nxt = SHIFT_CYCLE[(SHIFT_CYCLE.index(cur) + 1) % len(SHIFT_CYCLE)]
        ns[day] = nxt
        item = QTableWidgetItem(SHIFT_KR[nxt])
        item.setTextAlignment(Qt.AlignCenter)
        item.setBackground(QBrush(_load_colors()[nxt]))
        self.table.setItem(row, col, item)
        self._update_summary(days)

    def _prev_month(self):
        self.month -= 1
        if self.month < 1:
            self.month = 12
            self.year -= 1
        self.refresh()

    def _next_month(self):
        self.month += 1
        if self.month > 12:
            self.month = 1
            self.year += 1
        self.refresh()

    def _auto_generate(self):
        msg = QMessageBox(self)
        msg.setWindowTitle('자동 생성')
        msg.setText(
            f'{self.year}년 {self.month}월 스케줄을 자동 생성하시겠습니까?\n기존 스케줄이 덮어씌워집니다.'
        )
        yes_btn = msg.addButton('예', QMessageBox.YesRole)
        msg.addButton('아니오', QMessageBox.NoRole)
        msg.exec_()
        if msg.clickedButton() != yes_btn:
            return

        self._gen_btn.setEnabled(False)
        self._gen_btn.setText('⏳ 생성 중...')

        # 돌아가는 busy 진행창 (min=max=0 → 애니메이션되는 무한 진행바)
        # 두 번째 인자('생성 중지')가 취소 버튼 라벨이 된다.
        self._progress = QProgressDialog(
            '스케줄을 생성하는 중입니다...\n잠시만 기다려 주세요.', '생성 중지', 0, 0, self)
        self._progress.setWindowTitle('자동 생성 중')
        self._progress.setWindowModality(Qt.ApplicationModal)
        self._progress.setMinimumDuration(0)     # 즉시 표시
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.canceled.connect(self._request_cancel)
        self._progress.show()

        # 백그라운드 스레드에서 생성 → 진행바가 계속 돌 수 있음
        self._worker = _GenWorker(self.year, self.month)
        self._worker.done.connect(self._on_generated)
        self._worker.failed.connect(self._on_gen_failed)
        self._worker.canceled.connect(self._on_gen_canceled)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _request_cancel(self):
        """'생성 중지' 클릭 시: 워커에 취소를 요청한다(실제 종료는 워커가 처리).
        완료 처리는 워커의 canceled 시그널(_on_gen_canceled)에서 한다."""
        if getattr(self, '_progress', None) is not None:
            self._progress.setLabelText('생성을 중지하는 중입니다...')
        if getattr(self, '_worker', None) is not None and self._worker.isRunning():
            self._worker.cancel()

    def _finish_generation(self):
        """진행창 닫고 버튼 원복 (성공/실패/취소 공통)."""
        if getattr(self, '_progress', None) is not None:
            self._progress.blockSignals(True)   # close()가 canceled를 재발생시키지 않게
            self._progress.close()
            self._progress = None
        self._gen_btn.setEnabled(True)
        self._gen_btn.setText('🔄 자동 생성')

    def _on_generated(self, result):
        self._schedule = result
        self._finish_generation()
        self._render()
        total_work = sum(
            1 for dm in self._schedule.values()
            for s in dm.values() if s in ('D', 'E', 'N')
        )
        QMessageBox.information(
            self, '생성 완료',
            f'{self.year}년 {self.month}월 스케줄이 생성되었습니다.\n\n'
            f'간호사: {len(self._schedule)}명  /  총 근무: {total_work}건\n\n'
            f'저장하려면 💾 저장 버튼을 누르세요.'
        )

    def _on_gen_failed(self, message):
        self._finish_generation()
        QMessageBox.warning(self, '스케줄 생성 실패', message)

    def _on_gen_canceled(self):
        self._finish_generation()
        self.lbl_summary.setText('  생성이 중지되었습니다.')

    def _save(self):
        db.save_schedule(self.year, self.month, self._schedule)
        QMessageBox.information(self, '저장', '스케줄이 저장되었습니다.')

    def _export_excel(self):
        path, _ = QFileDialog.getSaveFileName(
            self, '엑셀 저장', f'스케줄_{self.year}{self.month:02d}.xlsx',
            'Excel (*.xlsx)'
        )
        if path:
            excel_export.export(self.year, self.month, self._nurses, self._schedule, path)
            QMessageBox.information(self, '완료', f'엑셀 파일이 저장되었습니다.\n{path}')

    def _export_pdf(self):
        if not self._schedule:
            QMessageBox.information(
                self, '출력본', '먼저 스케줄을 생성/저장하거나 불러온 뒤 저장하세요.')
            return
        path, _ = QFileDialog.getSaveFileName(
            self, '출력본 PDF 저장', f'근무표_{self.year}{self.month:02d}.pdf', 'PDF (*.pdf)'
        )
        if not path:
            return
        try:
            pdf_export.export(self.year, self.month, self._nurses, self._teams,
                              self._schedule, path)
            QMessageBox.information(self, '완료', f'출력본 PDF가 저장되었습니다.\n{path}')
        except Exception as e:                       # noqa: BLE001
            QMessageBox.warning(self, '오류', f'PDF 저장 실패: {e}')
