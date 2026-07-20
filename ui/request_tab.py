"""요청 관리 탭 — 간호사별 휴무/특정 근무 요청."""
import calendar
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
import database as db

SHIFT_KR    = {'off': '휴무', 'D': '낮', 'E': '저녁', 'N': '밤'}
SHIFT_COLOR = {
    'off': QColor('#F0F0F0'),
    'D':   QColor('#BDD7EE'),
    'E':   QColor('#FFE699'),
    'N':   QColor('#C5A8FF'),
}
WD_KR = ['월','화','수','목','금','토','일']


class RequestTab(QWidget):
    def __init__(self):
        super().__init__()
        from datetime import date
        today = date.today()
        self.year  = today.year
        self.month = today.month
        self._nurses  = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        btn_prev = QPushButton('◀')
        btn_prev.setFixedWidth(36)
        btn_prev.clicked.connect(self._prev_month)
        self.lbl_month = QLabel()
        self.lbl_month.setAlignment(Qt.AlignCenter)
        btn_next = QPushButton('▶')
        btn_next.setFixedWidth(36)
        btn_next.clicked.connect(self._next_month)
        btn_clear = QPushButton('🗑️ 전체 삭제')
        btn_clear.clicked.connect(self._clear_all)

        top.addWidget(btn_prev)
        top.addWidget(self.lbl_month, 1)
        top.addWidget(btn_next)
        top.addStretch()
        top.addWidget(btn_clear)
        layout.addLayout(top)

        info = QLabel('셀을 더블클릭하면 요청 유형이 순환합니다. (빈칸 → 휴무 → 낮 → 저녁 → 밤 → 빈칸)')
        info.setStyleSheet('color: #666; font-size: 11px;')
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._toggle_request)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(24)
        layout.addWidget(self.table)

    def refresh(self):
        self._nurses = db.get_nurses()
        self.lbl_month.setText(f'{self.year}년 {self.month}월 근무 요청')
        days = calendar.monthrange(self.year, self.month)[1]
        weekdays = [calendar.weekday(self.year, self.month, d) for d in range(1, days+1)]

        reqs = db.get_requests(self.year, self.month)
        req_map = {}
        for r in reqs:
            req_map[(r.nurse_id, r.day)] = r.req_type

        self.table.setRowCount(len(self._nurses))
        self.table.setColumnCount(days)
        self.table.setHorizontalHeaderLabels(
            [f'{d}\n{WD_KR[weekdays[d-1]]}' for d in range(1, days+1)]
        )
        self.table.setVerticalHeaderLabels([n.name for n in self._nurses])

        for ri, nurse in enumerate(self._nurses):
            for d in range(1, days+1):
                rt = req_map.get((nurse.id, d))
                text = SHIFT_KR.get(rt, '') if rt else ''
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                if rt:
                    item.setBackground(QBrush(SHIFT_COLOR.get(rt, QColor('#FFF'))))
                self.table.setItem(ri, d-1, item)

    def _toggle_request(self, row, col):
        nurse = self._nurses[row]
        day   = col + 1
        reqs  = db.get_requests(self.year, self.month)
        cur   = next((r.req_type for r in reqs if r.nurse_id == nurse.id and r.day == day), None)
        cycle = [None, 'off', 'D', 'E', 'N']
        nxt   = cycle[(cycle.index(cur) + 1) % len(cycle)]
        db.set_request(nurse.id, self.year, self.month, day, nxt)
        self.refresh()

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

    def _clear_all(self):
        reply = QMessageBox.question(
            self, '전체 삭제',
            f'{self.year}년 {self.month}월 요청을 모두 삭제하시겠습니까?',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            reqs = db.get_requests(self.year, self.month)
            for r in reqs:
                db.set_request(r.nurse_id, self.year, self.month, r.day, None)
            self.refresh()
