"""팀 관리 탭 — 팀 생성/수정/삭제 및 간호사 팀 배정."""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QGroupBox, QSplitter,
    QInputDialog, QMessageBox, QColorDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush, QFont
import database as db
import team_balance


class TeamTab(QWidget):
    def __init__(self):
        super().__init__()
        self._teams = []
        self._nurses = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)

        # ── 왼쪽: 팀 목록 ────────────────────────────────────────────────────
        left = QWidget()
        left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 4, 0)

        grp_team = QGroupBox('팀 목록')
        tv = QVBoxLayout(grp_team)

        self.team_list = QListWidget()
        self.team_list.setMinimumWidth(180)
        self.team_list.currentRowChanged.connect(self._on_team_selected)
        tv.addWidget(self.team_list)

        btn_row = QHBoxLayout()
        btn_add_team   = QPushButton('➕ 팀 추가')
        btn_rename     = QPushButton('✏️ 이름')
        btn_color      = QPushButton('🎨 색상')
        btn_del_team   = QPushButton('🗑️ 삭제')
        btn_add_team.clicked.connect(self._add_team)
        btn_rename.clicked.connect(self._rename_team)
        btn_color.clicked.connect(self._change_color)
        btn_del_team.clicked.connect(self._delete_team)
        for b in (btn_add_team, btn_rename, btn_color, btn_del_team):
            btn_row.addWidget(b)
        tv.addLayout(btn_row)

        btn_balance = QPushButton('⚖️ 연차 밸런싱 자동편성 (RN)')
        btn_balance.setToolTip('입사연차·등급을 팀마다 고르게 맞춰 RN을 팀 A~F에 자동 배정합니다.')
        btn_balance.clicked.connect(self._auto_balance)
        tv.addWidget(btn_balance)

        left_v.addWidget(grp_team)
        splitter.addWidget(left)

        # ── 오른쪽: 간호사 배정 ───────────────────────────────────────────────
        right = QWidget()
        right_v = QVBoxLayout(right)
        right_v.setContentsMargins(4, 0, 0, 0)

        self.lbl_team_name = QLabel('팀을 선택하세요')
        self.lbl_team_name.setFont(QFont('', 11, QFont.Bold))
        right_v.addWidget(self.lbl_team_name)

        assign_row = QHBoxLayout()

        # 미배정 간호사
        unassigned_box = QGroupBox('미배정 간호사')
        ub_v = QVBoxLayout(unassigned_box)
        self.unassigned_list = QListWidget()
        self.unassigned_list.setSelectionMode(QListWidget.ExtendedSelection)
        ub_v.addWidget(self.unassigned_list)
        assign_row.addWidget(unassigned_box)

        # 중간 버튼
        mid = QVBoxLayout()
        mid.addStretch()
        btn_assign   = QPushButton('→\n팀에\n추가')
        btn_unassign = QPushButton('←\n팀에서\n제거')
        btn_assign.setFixedWidth(60)
        btn_unassign.setFixedWidth(60)
        btn_assign.clicked.connect(self._assign_nurses)
        btn_unassign.clicked.connect(self._unassign_nurses)
        mid.addWidget(btn_assign)
        mid.addSpacing(8)
        mid.addWidget(btn_unassign)
        mid.addStretch()
        assign_row.addLayout(mid)

        # 팀 소속 간호사
        member_box = QGroupBox('팀 소속 간호사')
        mb_v = QVBoxLayout(member_box)
        self.member_list = QListWidget()
        self.member_list.setSelectionMode(QListWidget.ExtendedSelection)
        mb_v.addWidget(self.member_list)
        assign_row.addWidget(member_box)

        right_v.addLayout(assign_row)

        note = QLabel('* 팀 선택 후 간호사를 이동하면 즉시 저장됩니다.')
        note.setStyleSheet('color:#888; font-size:11px;')
        right_v.addWidget(note)

        splitter.addWidget(right)
        splitter.setSizes([220, 600])

        layout.addWidget(splitter)

    def refresh(self):
        self._teams  = db.get_teams()
        self._nurses = db.get_nurses(active_only=False)

        prev_row = self.team_list.currentRow()
        self.team_list.clear()
        for t in self._teams:
            item = QListWidgetItem(t.name)
            item.setBackground(QBrush(QColor(t.color)))
            item.setData(Qt.UserRole, t.id)
            self.team_list.addItem(item)

        if 0 <= prev_row < len(self._teams):
            self.team_list.setCurrentRow(prev_row)
        elif self._teams:
            self.team_list.setCurrentRow(0)
        else:
            self._refresh_nurse_lists(None)

    def _on_team_selected(self, row):
        if row < 0 or row >= len(self._teams):
            self._refresh_nurse_lists(None)
            return
        team = self._teams[row]
        self.lbl_team_name.setText(f'📁 {team.name}')
        self._refresh_nurse_lists(team.id)

    def _refresh_nurse_lists(self, team_id):
        self.unassigned_list.clear()
        self.member_list.clear()
        if team_id is None:
            for n in self._nurses:
                if n.active:
                    self.unassigned_list.addItem(self._nurse_item(n))
            return
        for n in self._nurses:
            if not n.active:
                continue
            item = self._nurse_item(n)
            if n.team_id == team_id:
                self.member_list.addItem(item)
            elif n.team_id is None:
                self.unassigned_list.addItem(item)

    def _nurse_item(self, nurse):
        item = QListWidgetItem(f'{nurse.name}  ({nurse.level})')
        item.setData(Qt.UserRole, nurse.id)
        return item

    def _current_team(self):
        row = self.team_list.currentRow()
        if row < 0 or row >= len(self._teams):
            return None
        return self._teams[row]

    def _assign_nurses(self):
        team = self._current_team()
        if not team:
            QMessageBox.warning(self, '팀 선택', '팀을 먼저 선택하세요.')
            return
        for item in self.unassigned_list.selectedItems():
            db.set_nurse_team(item.data(Qt.UserRole), team.id)
        self._nurses = db.get_nurses(active_only=False)
        self._refresh_nurse_lists(team.id)

    def _unassign_nurses(self):
        team = self._current_team()
        if not team:
            return
        for item in self.member_list.selectedItems():
            db.set_nurse_team(item.data(Qt.UserRole), None)
        self._nurses = db.get_nurses(active_only=False)
        self._refresh_nurse_lists(team.id)

    def _auto_balance(self):
        try:
            teams, proposal = team_balance.balance_teams()
        except Exception as e:
            QMessageBox.warning(self, '자동편성', str(e))
            return
        if not any(proposal):
            QMessageBox.information(self, '자동편성', '배정할 RN 간호사가 없습니다.')
            return

        # 미리보기
        blocks = []
        for team, members in zip(teams, proposal):
            s = team_balance.summary(members)
            lv = ', '.join(
                f'{k} {v}' for k, v in
                sorted(s['levels'].items(),
                       key=lambda kv: -team_balance.LEVEL_RANK.get(kv[0], 1))
            )
            names = ', '.join(n.name for n in members)
            blocks.append(f'[{team.name}]  {s["count"]}명 · 평균연차 {s["avg_years"]}년\n'
                          f'    {lv}\n    {names}')
        box = QMessageBox(self)
        box.setWindowTitle('연차 밸런싱 자동편성 (RN)')
        box.setText('아래와 같이 RN을 팀에 배정합니다. (기존 RN 팀 배정은 덮어씀)\n\n'
                    + '\n\n'.join(blocks))
        box.setStandardButtons(QMessageBox.Apply | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec_() == QMessageBox.Apply:
            team_balance.apply(teams, proposal)
            self.refresh()
            QMessageBox.information(self, '완료', 'RN 팀 배정을 완료했습니다.')

    def _add_team(self):
        name, ok = QInputDialog.getText(self, '팀 추가', '팀 이름:')
        if ok and name.strip():
            try:
                db.add_team(name.strip())
                self.refresh()
                # 새 팀 선택
                for i in range(self.team_list.count()):
                    if self.team_list.item(i).text() == name.strip():
                        self.team_list.setCurrentRow(i)
                        break
            except Exception as e:
                QMessageBox.warning(self, '오류', f'팀 추가 실패: {e}')

    def _rename_team(self):
        team = self._current_team()
        if not team:
            QMessageBox.warning(self, '팀 선택', '팀을 먼저 선택하세요.')
            return
        name, ok = QInputDialog.getText(self, '이름 변경', '새 팀 이름:', text=team.name)
        if ok and name.strip():
            try:
                db.update_team(team.id, name.strip(), team.color)
                self.refresh()
            except Exception as e:
                QMessageBox.warning(self, '오류', f'이름 변경 실패: {e}')

    def _change_color(self):
        team = self._current_team()
        if not team:
            QMessageBox.warning(self, '팀 선택', '팀을 먼저 선택하세요.')
            return
        c = QColorDialog.getColor(QColor(team.color), self, '팀 색상 선택')
        if c.isValid():
            db.update_team(team.id, team.name, c.name().upper())
            self.refresh()

    def _delete_team(self):
        team = self._current_team()
        if not team:
            QMessageBox.warning(self, '팀 선택', '팀을 먼저 선택하세요.')
            return
        count = sum(1 for n in self._nurses if n.team_id == team.id)
        msg = f'"{team.name}" 팀을 삭제하시겠습니까?'
        if count:
            msg += f'\n소속 간호사 {count}명이 미배정 상태로 변경됩니다.'
        reply = QMessageBox.question(self, '팀 삭제', msg,
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            db.delete_team(team.id)
            self.refresh()
