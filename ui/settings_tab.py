"""설정 탭 — 모든 스케줄 제약 및 색상 설정."""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QSpinBox,
    QPushButton, QLabel, QGroupBox, QMessageBox, QColorDialog,
    QCheckBox, QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
import database as db

COLOR_DEFAULTS = {
    'color_D':   '#6FA8DC',
    'color_E':   '#FFCE47',
    'color_N':   '#A47BE0',
    'color_O':   '#E0E0E0',
    'color_sat': '#9FCAF2',
    'color_hol': '#FFAFAF',
}


class SettingsTab(QWidget):
    def __init__(self):
        super().__init__()
        self._color_btns = {}
        self._build_ui()
        self.load()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(8)

        # ── 1. 평일 D/E 최소 인원 (RN) ────────────────────────────────────────
        grp1 = QGroupBox('평일 D/E 최소 인원 (RN)')
        f1 = QFormLayout(grp1)
        self.spin_min_d = QSpinBox(); self.spin_min_d.setRange(0, 30)
        self.spin_min_e = QSpinBox(); self.spin_min_e.setRange(0, 30)
        self.spin_min_n = QSpinBox(); self.spin_min_n.setRange(0, 30)
        f1.addRow('평일 낮 (D) 최소 인원',   self.spin_min_d)
        f1.addRow('평일 저녁 (E) 최소 인원', self.spin_min_e)
        f1.addRow('밤 (N) 최소 인원 (미사용)', self.spin_min_n)
        layout.addWidget(grp1)

        # ── 1-2. 요일유형별 필요 인원 (고정) ──────────────────────────────────
        grp_staff = QGroupBox('요일유형별 필요 인원 (주말·공휴일·평일N은 정확히 그 인원)')
        fs = QFormLayout(grp_staff)
        def _spin():
            s = QSpinBox(); s.setRange(0, 30); return s
        self.spin_we_d,  self.spin_we_e,  self.spin_we_n  = _spin(), _spin(), _spin()
        self.spin_wd_n = _spin()
        self.spin_na_we_d, self.spin_na_we_e, self.spin_na_we_n = _spin(), _spin(), _spin()
        self.spin_na_wd_n = _spin()
        fs.addRow('[RN] 주말·공휴일 D', self.spin_we_d)
        fs.addRow('[RN] 주말·공휴일 E', self.spin_we_e)
        fs.addRow('[RN] 주말·공휴일 N', self.spin_we_n)
        fs.addRow('[RN] 평일 N',        self.spin_wd_n)
        fs.addRow('[NA] 주말·공휴일 D', self.spin_na_we_d)
        fs.addRow('[NA] 주말·공휴일 E', self.spin_na_we_e)
        fs.addRow('[NA] 주말·공휴일 N', self.spin_na_we_n)
        fs.addRow('[NA] 평일 N',        self.spin_na_wd_n)
        note_staff = QLabel('* 주말·공휴일 D/E/N과 평일 N은 "정확히 그 인원". 평일 D/E는 위 최소값 이상.')
        note_staff.setStyleSheet('color:#888; font-size:11px;')
        fs.addRow('', note_staff)
        layout.addWidget(grp_staff)

        # ── 2. 야간 근무 제약 ─────────────────────────────────────────────────
        grp2 = QGroupBox('야간 근무 제약')
        f2 = QFormLayout(grp2)
        self.spin_max_consec_n  = QSpinBox(); self.spin_max_consec_n.setRange(1, 7)
        self.spin_rest          = QSpinBox(); self.spin_rest.setRange(1, 5)
        self.spin_max_monthly_n = QSpinBox(); self.spin_max_monthly_n.setRange(1, 31)
        f2.addRow('최대 연속 야간 일수',     self.spin_max_consec_n)
        f2.addRow('야간 후 의무 휴무일 수',  self.spin_rest)
        f2.addRow('1인당 월 최대 야간 횟수', self.spin_max_monthly_n)
        layout.addWidget(grp2)

        # ── 3. 연속 근무 패턴 ─────────────────────────────────────────────────
        grp3 = QGroupBox('연속 근무 패턴')
        f3 = QFormLayout(grp3)
        self.spin_max_consec_work = QSpinBox(); self.spin_max_consec_work.setRange(1, 14)
        self.chk_forbid_ed = QCheckBox('E→D 역방향 배정 금지  (저녁 다음날 낮 근무 방지)')
        f3.addRow('최대 연속 근무일 (D+E+N)', self.spin_max_consec_work)
        f3.addRow('역방향 교대',              self.chk_forbid_ed)
        layout.addWidget(grp3)

        # ── 3-2. 생성 속도 ────────────────────────────────────────────────────
        grp_speed = QGroupBox('자동 생성 속도')
        fsp = QFormLayout(grp_speed)
        self.spin_solve_seconds = QSpinBox(); self.spin_solve_seconds.setRange(1, 30)
        self.spin_solve_seconds.setSuffix('초')
        fsp.addRow('직군별 계산 시간 상한', self.spin_solve_seconds)
        note_speed = QLabel('* 낮출수록 생성이 빨라집니다(권장 3초). 너무 낮추면(1~2초) 인원이 많을 때\n'
                            '  "생성 불가"가 날 수 있습니다. 전체 소요는 RN·NA 두 직군 합산이라 이 값의 약 2배입니다.')
        note_speed.setStyleSheet('color:#888; font-size:11px;')
        fsp.addRow('', note_speed)
        layout.addWidget(grp_speed)

        # ── 4. 인력 구성 (Skill Mix) ──────────────────────────────────────────
        grp4 = QGroupBox('인력 구성 규칙 (Skill Mix)')
        f4 = QFormLayout(grp4)
        self.spin_min_charge  = QSpinBox(); self.spin_min_charge.setRange(0, 5)
        self.spin_min_skilled = QSpinBox(); self.spin_min_skilled.setRange(0, 5)
        self.chk_prevent_new  = QCheckBox('신규간호사 단독 교대 배정 방지')
        note_skill = QLabel('  * 등급: 신규 < 일반 < 숙련 < 책임  |  숙련자 = 숙련 + 책임')
        note_skill.setStyleSheet('color:#888; font-size:11px;')
        f4.addRow('교대당 최소 책임간호사 수', self.spin_min_charge)
        f4.addRow('교대당 최소 숙련자 수',     self.spin_min_skilled)
        f4.addRow('신규 단독 방지',            self.chk_prevent_new)
        f4.addRow('',                          note_skill)
        layout.addWidget(grp4)

        # ── 5. 교대 색상 ──────────────────────────────────────────────────────
        grp5 = QGroupBox('교대 색상')
        f5 = QFormLayout(grp5)
        for key, label in [('color_D', 'D (낮)'), ('color_E', 'E (저녁)'),
                            ('color_N', 'N (밤)'), ('color_O', '휴무')]:
            f5.addRow(label, self._make_color_btn(key))
        layout.addWidget(grp5)

        # ── 6. 달력 헤더 색상 ─────────────────────────────────────────────────
        grp6 = QGroupBox('달력 헤더 색상')
        f6 = QFormLayout(grp6)
        for key, label in [('color_sat', '토요일'), ('color_hol', '일요일 / 공휴일')]:
            f6.addRow(label, self._make_color_btn(key))
        layout.addWidget(grp6)

        # ── 버튼 ──────────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_save         = QPushButton('💾 설정 저장')
        btn_reset_colors = QPushButton('↩ 색상 초기화')
        btn_save.clicked.connect(self._save)
        btn_reset_colors.clicked.connect(self._reset_colors)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_reset_colors)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        note = QLabel('* 색상은 선택 즉시 저장. 나머지는 저장 버튼 클릭 후 재생성 시 반영.')
        note.setStyleSheet('color:#888; font-size:11px;')
        layout.addWidget(note)

        # ── 7. 현재 적용 규칙 요약 ───────────────────────────────────────────
        grp7 = QGroupBox('현재 적용 중인 규칙 요약')
        g7_layout = QVBoxLayout(grp7)
        self.rule_display = QLabel()
        self.rule_display.setWordWrap(True)
        self.rule_display.setTextFormat(Qt.RichText)
        self.rule_display.setStyleSheet(
            'font-size: 12px; padding: 8px;'
            'background: #F8F8F8; border: 1px solid #DDD; border-radius: 4px;'
        )
        g7_layout.addWidget(self.rule_display)
        layout.addWidget(grp7)

    def _make_color_btn(self, key):
        btn = QPushButton()
        btn.setFixedSize(100, 24)
        self._color_btns[key] = btn
        btn.clicked.connect(lambda _, k=key: self._pick_color(k))
        return btn

    def _apply_btn_color(self, key, hex_color):
        r, g, b = QColor(hex_color).getRgb()[:3]
        text = '#000' if (0.299 * r + 0.587 * g + 0.114 * b) > 128 else '#fff'
        self._color_btns[key].setStyleSheet(
            f'background:{hex_color}; color:{text};'
            f'border:1px solid #aaa; border-radius:3px;'
        )
        self._color_btns[key].setText(hex_color.upper())

    def _pick_color(self, key):
        cfg = db.get_settings()
        cur = cfg.get(key, COLOR_DEFAULTS.get(key, '#FFFFFF'))
        c = QColorDialog.getColor(QColor(cur), self, '색상 선택')
        if c.isValid():
            h = c.name().upper()
            db.set_setting(key, h)
            self._apply_btn_color(key, h)

    def _reset_colors(self):
        if QMessageBox.question(self, '초기화', '색상을 기본값으로 되돌리겠습니까?',
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            for k, v in COLOR_DEFAULTS.items():
                db.set_setting(k, v)
                self._apply_btn_color(k, v)

    def load(self):
        cfg = db.get_settings()
        self.spin_min_d.setValue(int(cfg.get('min_day',   5)))
        self.spin_min_e.setValue(int(cfg.get('min_eve',   4)))
        self.spin_min_n.setValue(int(cfg.get('min_night', 3)))
        self.spin_we_d.setValue(int(cfg.get('we_day',   5)))
        self.spin_we_e.setValue(int(cfg.get('we_eve',   5)))
        self.spin_we_n.setValue(int(cfg.get('we_night', 5)))
        self.spin_wd_n.setValue(int(cfg.get('wd_night', 5)))
        self.spin_na_we_d.setValue(int(cfg.get('na_we_day',   2)))
        self.spin_na_we_e.setValue(int(cfg.get('na_we_eve',   2)))
        self.spin_na_we_n.setValue(int(cfg.get('na_we_night', 1)))
        self.spin_na_wd_n.setValue(int(cfg.get('na_wd_night', 1)))
        self.spin_max_consec_n.setValue( int(cfg.get('max_consec_night',  3)))
        self.spin_rest.setValue(         int(cfg.get('rest_after_night',  2)))
        self.spin_max_monthly_n.setValue(min(int(cfg.get('max_monthly_night', 31)), 31))
        self.spin_max_consec_work.setValue(int(cfg.get('max_consec_work',         5)))
        self.spin_solve_seconds.setValue(min(max(int(float(cfg.get('solve_seconds', 3))), 1), 30))
        self.spin_min_charge.setValue(     int(cfg.get('min_charge_per_shift',    1)))
        self.spin_min_skilled.setValue(    int(cfg.get('min_skilled_per_shift',   1)))
        self.chk_forbid_ed.setChecked(   cfg.get('forbid_ed',        '1') == '1')
        self.chk_prevent_new.setChecked( cfg.get('prevent_new_only', '1') == '1')
        for key, default in COLOR_DEFAULTS.items():
            self._apply_btn_color(key, cfg.get(key, default))
        self._update_rule_display()

    def _save(self):
        db.set_setting('min_day',            self.spin_min_d.value())
        db.set_setting('min_eve',            self.spin_min_e.value())
        db.set_setting('min_night',          self.spin_min_n.value())
        db.set_setting('we_day',   self.spin_we_d.value())
        db.set_setting('we_eve',   self.spin_we_e.value())
        db.set_setting('we_night', self.spin_we_n.value())
        db.set_setting('wd_night', self.spin_wd_n.value())
        db.set_setting('na_we_day',   self.spin_na_we_d.value())
        db.set_setting('na_we_eve',   self.spin_na_we_e.value())
        db.set_setting('na_we_night', self.spin_na_we_n.value())
        db.set_setting('na_wd_night', self.spin_na_wd_n.value())
        db.set_setting('max_consec_night',   self.spin_max_consec_n.value())
        db.set_setting('rest_after_night',   self.spin_rest.value())
        db.set_setting('max_monthly_night',  self.spin_max_monthly_n.value())
        db.set_setting('max_consec_work',    self.spin_max_consec_work.value())
        db.set_setting('solve_seconds',      self.spin_solve_seconds.value())
        db.set_setting('min_charge_per_shift',  self.spin_min_charge.value())
        db.set_setting('min_skilled_per_shift', self.spin_min_skilled.value())
        db.set_setting('forbid_ed',        '1' if self.chk_forbid_ed.isChecked()   else '0')
        db.set_setting('prevent_new_only', '1' if self.chk_prevent_new.isChecked() else '0')
        self._update_rule_display()
        QMessageBox.information(self, '저장', '설정이 저장되었습니다.')

    def _update_rule_display(self):
        on  = '<span style="color:#1a7a1a; font-weight:bold;">✔ 적용</span>'
        off = '<span style="color:#aaa;">✘ 비활성</span>'
        forbid = self.chk_forbid_ed.isChecked()
        prevent = self.chk_prevent_new.isChecked()
        mn = self.spin_max_monthly_n.value()
        mn_txt = f'{mn}회' if mn < 31 else '무제한'

        lines = [
            '<b>[ 인원 배치 (RN) ]</b>',
            f'&nbsp;&nbsp;주말·공휴일: D {self.spin_we_d.value()} · E {self.spin_we_e.value()} · '
            f'N {self.spin_we_n.value()} (정확히)',
            f'&nbsp;&nbsp;평일: N {self.spin_wd_n.value()} (정확히) · '
            f'D 최소 {self.spin_min_d.value()} · E 최소 {self.spin_min_e.value()}',
            f'<b>[ 인원 배치 (NA) ]</b>',
            f'&nbsp;&nbsp;주말·공휴일: D {self.spin_na_we_d.value()} · E {self.spin_na_we_e.value()} · '
            f'N {self.spin_na_we_n.value()} &nbsp;|&nbsp; 평일 N {self.spin_na_wd_n.value()}',
            '',
            '<b>[ 야간 근무 ]</b>',
            f'&nbsp;&nbsp;최대 연속 야간 {self.spin_max_consec_n.value()}일',
            f'&nbsp;&nbsp;야간 종료 후 의무 휴무 {self.spin_rest.value()}일',
            f'&nbsp;&nbsp;1인당 월 최대 야간 {mn_txt}',
            '',
            '<b>[ 연속 근무 ]</b>',
            f'&nbsp;&nbsp;최대 연속 근무 {self.spin_max_consec_work.value()}일 (D+E+N 합산)',
            f'&nbsp;&nbsp;{self.spin_max_consec_work.value()}일 연속 근무 후 <b>2일 의무 휴무</b>',
            '',
            '<b>[ 역방향 교대 금지 ]</b> &nbsp;' + (on if forbid else off),
            (f'&nbsp;&nbsp;E → D 금지<br>'
             f'&nbsp;&nbsp;E → 휴 → D 금지<br>'
             f'&nbsp;&nbsp;N → 휴 → D 금지') if forbid else '&nbsp;&nbsp;(비활성)',
            '',
            '<b>[ Skill Mix ]</b>',
            f'&nbsp;&nbsp;교대당 최소 책임간호사 {self.spin_min_charge.value()}명',
            f'&nbsp;&nbsp;교대당 최소 숙련자 {self.spin_min_skilled.value()}명',
            f'&nbsp;&nbsp;신규 단독 교대 방지 &nbsp;' + (on if prevent else off),
        ]
        self.rule_display.setText('<br>'.join(lines))
