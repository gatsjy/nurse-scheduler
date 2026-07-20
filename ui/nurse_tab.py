"""간호사 관리 탭."""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QFormLayout, QLineEdit, QComboBox, QTextEdit, QDialogButtonBox,
    QMessageBox, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
import database as db

LEVEL_COLORS = {
    '신규': '#FFE0E0',
    '일반': '#FFFFFF',
    '숙련': '#E0F0FF',
    '책임': '#E0FFE0',
}


class NurseTab(QWidget):
    def __init__(self):
        super().__init__()
        self._nurses = []
        self._teams  = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        btn_add = QPushButton('➕ 간호사 추가')
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton('✏️ 수정')
        btn_edit.clicked.connect(self._edit)
        self.btn_toggle = QPushButton('🚫 비활성화')
        self.btn_toggle.clicked.connect(self._toggle_active)
        btn_del = QPushButton('🗑️ 삭제')
        btn_del.clicked.connect(self._delete)
        top.addWidget(btn_add)
        top.addWidget(btn_edit)
        top.addWidget(self.btn_toggle)
        top.addWidget(btn_del)
        top.addStretch()

        # 등급 범례
        for level, color in LEVEL_COLORS.items():
            lbl = QLabel(f'  {level}  ')
            lbl.setStyleSheet(f'background:{color}; border:1px solid #ccc; border-radius:3px;')
            top.addWidget(lbl)

        layout.addLayout(top)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(['이름', '사번', '직군', '팀', '직책', '등급', '입사일', '상태', '야간 불가', '메모'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit)
        self.table.itemSelectionChanged.connect(self._update_toggle_label)
        layout.addWidget(self.table)

    def _update_toggle_label(self):
        nurse = self._selected_nurse()
        if nurse is not None and not nurse.active:
            self.btn_toggle.setText('✅ 활성화')
        else:
            self.btn_toggle.setText('🚫 비활성화')

    def refresh(self):
        self._nurses  = db.get_nurses(active_only=False)
        self._teams   = db.get_teams()
        team_map      = {t.id: t for t in self._teams}

        self.table.setRowCount(len(self._nurses))
        for i, n in enumerate(self._nurses):
            self.table.setItem(i, 0, QTableWidgetItem(n.name))

            emp_item = QTableWidgetItem(getattr(n, 'emp_no', '') or '')
            emp_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 1, emp_item)

            job_item = QTableWidgetItem(getattr(n, 'job_type', 'RN') or 'RN')
            job_item.setTextAlignment(Qt.AlignCenter)
            if getattr(n, 'job_type', 'RN') == 'NA':
                job_item.setBackground(QBrush(QColor('#EFE0FF')))
            self.table.setItem(i, 2, job_item)

            # 팀 열
            team = team_map.get(n.team_id) if n.team_id else None
            team_item = QTableWidgetItem(team.name if team else '')
            team_item.setTextAlignment(Qt.AlignCenter)
            if team:
                team_item.setBackground(QBrush(QColor(team.color)))
            self.table.setItem(i, 3, team_item)

            self.table.setItem(i, 4, QTableWidgetItem(n.position))

            lv_item = QTableWidgetItem(n.level)
            lv_item.setTextAlignment(Qt.AlignCenter)
            lv_item.setBackground(QBrush(QColor(LEVEL_COLORS.get(n.level, '#FFFFFF'))))
            self.table.setItem(i, 5, lv_item)

            self.table.setItem(i, 6, QTableWidgetItem(n.hire_date))
            status_item = QTableWidgetItem('활성' if n.active else '비활성')
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 7, status_item)

            nn_item = QTableWidgetItem('야간 불가' if n.no_night else '')
            nn_item.setTextAlignment(Qt.AlignCenter)
            if n.no_night:
                nn_item.setBackground(QBrush(QColor('#FFD7D7')))
            self.table.setItem(i, 8, nn_item)
            self.table.setItem(i, 9, QTableWidgetItem(n.note))

            # 비활성 간호사는 행 전체를 회색으로 흐리게 표시
            if not n.active:
                gray_bg = QColor('#F0F0F0')
                gray_fg = QColor('#9AA0A6')
                for c in range(self.table.columnCount()):
                    it = self.table.item(i, c)
                    if it is None:
                        continue
                    it.setForeground(QBrush(gray_fg))
                    it.setBackground(QBrush(gray_bg))
                    f = it.font()
                    f.setStrikeOut(True)
                    it.setFont(f)

        self._update_toggle_label()

    def _selected_nurse(self):
        if not self.table.selectedItems():
            return None
        return self._nurses[self.table.currentRow()]

    def _add(self):
        dlg = NurseDialog(self, nurses=self._nurses)
        if dlg.exec_() == QDialog.Accepted:
            db.add_nurse(**dlg.get_data())
            self.refresh()

    def _edit(self):
        nurse = self._selected_nurse()
        if not nurse:
            QMessageBox.warning(self, '선택', '수정할 간호사를 선택하세요.')
            return
        dlg = NurseDialog(self, nurse, nurses=self._nurses)
        if dlg.exec_() == QDialog.Accepted:
            db.update_nurse(nurse.id, **dlg.get_data())
            self.refresh()

    def _toggle_active(self):
        nurse = self._selected_nurse()
        if not nurse:
            QMessageBox.warning(self, '선택', '활성/비활성화할 간호사를 선택하세요.')
            return
        if nurse.active:
            reply = QMessageBox.question(
                self, '비활성화',
                f'{nurse.name} 간호사를 비활성화하시겠습니까?\n'
                '(스케줄 자동 생성 대상에서 제외됩니다. 데이터는 보존됩니다.)',
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                db.deactivate_nurse(nurse.id)
                self.refresh()
        else:
            db.reactivate_nurse(nurse.id)
            self.refresh()

    def _delete(self):
        nurse = self._selected_nurse()
        if not nurse:
            QMessageBox.warning(self, '선택', '삭제할 간호사를 선택하세요.')
            return
        reply = QMessageBox.warning(
            self, '완전 삭제',
            f'{nurse.name} 간호사를 완전히 삭제하시겠습니까?\n\n'
            '⚠️ 이 간호사의 근무 요청과 저장된 스케줄 기록도 함께 삭제되며,\n'
            '되돌릴 수 없습니다.\n\n'
            '(단순히 편성에서 제외하려면 삭제 대신 "비활성화"를 사용하세요.)',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            db.delete_nurse(nurse.id)
            self.refresh()


class NurseDialog(QDialog):
    def __init__(self, parent=None, nurse=None, nurses=None):
        super().__init__(parent)
        self.setWindowTitle('간호사 추가' if nurse is None else '간호사 수정')
        self.setMinimumWidth(320)
        layout = QFormLayout(self)

        self.name_edit = QLineEdit(nurse.name if nurse else '')

        self.emp_edit = QLineEdit(getattr(nurse, 'emp_no', '') if nurse else '')
        self.emp_edit.setPlaceholderText('사번 입력')

        self.job_combo = QComboBox()
        self.job_combo.addItems(['RN', 'NA'])
        if nurse:
            idx = self.job_combo.findText(getattr(nurse, 'job_type', 'RN'))
            if idx >= 0:
                self.job_combo.setCurrentIndex(idx)

        self.pos_combo = QComboBox()
        self.pos_combo.addItems(['사원', '대리', '주임', '을계장', '갑계장'])
        if nurse:
            idx = self.pos_combo.findText(nurse.position)
            if idx >= 0:
                self.pos_combo.setCurrentIndex(idx)

        # 프리셉터 선택 (이 사람이 프리셉티일 때 짝). 본인 제외.
        self.precep_combo = QComboBox()
        self.precep_combo.addItem('없음', None)
        cur_pre = getattr(nurse, 'preceptor_id', None) if nurse else None
        for n in (nurses or []):
            if nurse and n.id == nurse.id:
                continue
            emp = getattr(n, 'emp_no', '') or ''
            self.precep_combo.addItem(f'{n.name} ({emp})' if emp else n.name, n.id)
            if cur_pre == n.id:
                self.precep_combo.setCurrentIndex(self.precep_combo.count() - 1)

        self.level_combo = QComboBox()
        self.level_combo.addItems(['신규', '일반', '숙련', '책임'])
        if nurse:
            idx = self.level_combo.findText(getattr(nurse, 'level', '일반'))
            if idx >= 0:
                self.level_combo.setCurrentIndex(idx)

        self.hire_edit = QLineEdit(nurse.hire_date if nurse else '')
        self.hire_edit.setPlaceholderText('예: 2020-03-02')

        self.no_night_chk = QCheckBox('야간 근무 배정 제외')
        if nurse:
            self.no_night_chk.setChecked(bool(nurse.no_night))

        self.night_only_chk = QCheckBox('나이트 전담 (밤/오프만, NN-OO 패턴)')
        if nurse:
            self.night_only_chk.setChecked(bool(getattr(nurse, 'night_only', False)))

        self.note_edit = QTextEdit(nurse.note if nurse else '')
        self.note_edit.setFixedHeight(60)

        layout.addRow('이름 *',  self.name_edit)
        layout.addRow('사번',    self.emp_edit)
        layout.addRow('직군',    self.job_combo)
        layout.addRow('직책',    self.pos_combo)
        layout.addRow('프리셉터', self.precep_combo)
        layout.addRow('등급',    self.level_combo)
        layout.addRow('입사일',  self.hire_edit)
        layout.addRow('야간 제한', self.no_night_chk)
        layout.addRow('나이트 전담', self.night_only_chk)
        layout.addRow('메모',    self.note_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _validate(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, '입력 오류', '이름을 입력하세요.')
            return
        self.accept()

    def get_data(self):
        return {
            'name':      self.name_edit.text().strip(),
            'emp_no':    self.emp_edit.text().strip(),
            'job_type':  self.job_combo.currentText(),
            'position':  self.pos_combo.currentText(),
            'preceptor_id': self.precep_combo.currentData(),
            'level':     self.level_combo.currentText(),
            'hire_date': self.hire_edit.text().strip(),
            'note':      self.note_edit.toPlainText().strip(),
            'no_night':  self.no_night_chk.isChecked(),
            'night_only': self.night_only_chk.isChecked(),
        }
