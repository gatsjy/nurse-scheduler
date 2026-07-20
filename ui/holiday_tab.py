"""공휴일 관리 탭."""
import calendar
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
import database as db

WD_KR = ['월','화','수','목','금','토','일']

# 한국 법정공휴일 기본값 (고정일 기준)
DEFAULT_HOLIDAYS = {
    (1,  1): '신정',
    (3,  1): '삼일절',
    (5,  5): '어린이날',
    (6,  6): '현충일',
    (8, 15): '광복절',
    (10, 3): '개천절',
    (10, 9): '한글날',
    (12,25): '크리스마스',
}


class HolidayTab(QWidget):
    def __init__(self):
        super().__init__()
        from datetime import date
        today = date.today()
        self.year  = today.year
        self.month = today.month
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
        btn_defaults = QPushButton('📅 법정공휴일 불러오기')
        btn_defaults.clicked.connect(self._load_defaults)

        top.addWidget(btn_prev)
        top.addWidget(self.lbl_month, 1)
        top.addWidget(btn_next)
        top.addStretch()
        top.addWidget(btn_defaults)
        layout.addLayout(top)

        info = QLabel('셀을 더블클릭하여 공휴일을 추가/수정/삭제하세요.')
        info.setStyleSheet('color: #666; font-size: 11px;')
        layout.addWidget(info)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(['날짜', '요일', '공휴일 이름'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._edit_cell)
        layout.addWidget(self.table)

    def refresh(self):
        self.lbl_month.setText(f'{self.year}년 {self.month}월 공휴일 관리')
        days = calendar.monthrange(self.year, self.month)[1]
        holidays = db.get_holidays(self.year, self.month)

        # 주말 + 공휴일인 날만 표시
        rows = []
        for d in range(1, days+1):
            wd = calendar.weekday(self.year, self.month, d)
            holiday_name = holidays.get(d, '')
            if wd >= 5 or holiday_name:  # 토·일 또는 공휴일
                rows.append((d, wd, holiday_name))

        self.table.setRowCount(len(rows))
        for i, (d, wd, name) in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(f'{self.month}월 {d}일'))
            wd_item = QTableWidgetItem(WD_KR[wd])
            wd_item.setTextAlignment(Qt.AlignCenter)
            if wd == 5:
                wd_item.setBackground(QBrush(QColor('#CCE5FF')))
            elif wd == 6:
                wd_item.setBackground(QBrush(QColor('#FFD7D7')))
            self.table.setItem(i, 1, wd_item)

            h_item = QTableWidgetItem(name)
            if name:
                h_item.setBackground(QBrush(QColor('#FFD7D7')))
                h_item.setForeground(QBrush(QColor('#CC0000')))
            self.table.setItem(i, 2, h_item)
            self.table.setRowHeight(i, 28)

        # 전체 날짜 테이블도 하단에 표시 (달력 뷰)
        self._rows_data = rows

    def _edit_cell(self, row, col):
        if col != 2 or row >= len(self._rows_data):
            return
        d, wd, cur_name = self._rows_data[row]
        if cur_name:
            # 삭제 또는 수정
            reply = QMessageBox.question(
                self, '공휴일 수정',
                f'{self.month}월 {d}일 [{cur_name}]\n삭제하려면 아니오, 수정하려면 예를 누르세요.',
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                return
            elif reply == QMessageBox.No:
                db.set_holiday(self.year, self.month, d, '')
                self.refresh()
                return
        name, ok = QInputDialog.getText(
            self, '공휴일 추가/수정',
            f'{self.month}월 {d}일 공휴일 이름:',
            text=cur_name
        )
        if ok:
            db.set_holiday(self.year, self.month, d, name.strip())
            self.refresh()

    def _load_defaults(self):
        count = 0
        for (m, d), name in DEFAULT_HOLIDAYS.items():
            if m == self.month:
                db.set_holiday(self.year, self.month, d, name)
                count += 1
        if count:
            self.refresh()
            QMessageBox.information(self, '완료', f'{count}개의 법정공휴일을 불러왔습니다.')
        else:
            QMessageBox.information(self, '안내', f'{self.month}월에 해당하는 법정공휴일이 없습니다.')

    def _prev_month(self):
        self.month -= 1
        if self.month < 1:
            self.month = 12; self.year -= 1
        self.refresh()

    def _next_month(self):
        self.month += 1
        if self.month > 12:
            self.month = 1; self.year += 1
        self.refresh()
