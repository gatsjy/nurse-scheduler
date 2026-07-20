"""간호사 스케줄러 — 메인 진입점."""
import sys
import os
import multiprocessing

# 스케줄 생성은 독립 프로세스(spawn)에서 OR-Tools를 돌린다.
# 패키징된 exe에서 자식 프로세스가 GUI를 다시 띄우지 않도록 freeze_support를
# 다른 무거운 import보다 먼저 호출한다.
multiprocessing.freeze_support()

# exe 패키징 여부에 따라 작업 디렉토리를 실행파일 위치로 설정
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QStatusBar
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtCore import Qt

import database as db
import scheduler


def _resource_path(rel: str) -> str:
    """개발/패키징(exe) 양쪽에서 번들 리소스 경로를 반환한다."""
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _load_app_font() -> str:
    """번들된 D2Coding(무료·오픈소스 고정폭, 한글 지원)을 등록하고 패밀리명을 반환.
    로드 실패 시 시스템 기본 폰트로 폴백."""
    family = '맑은 고딕'
    for fn in ('assets/D2Coding.ttf', 'assets/D2CodingBold.ttf'):
        fid = QFontDatabase.addApplicationFont(_resource_path(fn))
        if fid != -1:
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                family = fams[0]
    return family
from ui.schedule_tab import ScheduleTab
from ui.nurse_tab    import NurseTab
from ui.team_tab     import TeamTab
from ui.request_tab  import RequestTab
from ui.holiday_tab  import HolidayTab
from ui.settings_tab import SettingsTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('간호사 근무 스케줄러')
        self.resize(1200, 700)

        tabs = QTabWidget()
        self.schedule_tab = ScheduleTab()
        self.nurse_tab    = NurseTab()
        self.team_tab     = TeamTab()
        self.request_tab  = RequestTab()
        self.holiday_tab  = HolidayTab()
        self.settings_tab = SettingsTab()

        tabs.addTab(self.schedule_tab, '📅  스케줄')
        tabs.addTab(self.nurse_tab,    '👩‍⚕️  간호사 관리')
        tabs.addTab(self.team_tab,     '👥  팀 관리')
        tabs.addTab(self.request_tab,  '📝  근무 요청')
        tabs.addTab(self.holiday_tab,  '🎌  공휴일')
        tabs.addTab(self.settings_tab, '⚙️  설정')

        # 탭 전환 시 스케줄 탭 새로고침
        tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs = tabs
        self.setCentralWidget(tabs)

        status = QStatusBar()
        nurses = db.get_nurses()
        status.showMessage(f'  활성 간호사: {len(nurses)}명')
        self.setStatusBar(status)

    def _on_tab_changed(self, idx):
        if idx == 0:
            self.schedule_tab.refresh()
        elif idx == 1:
            self.nurse_tab.refresh()
        elif idx == 2:
            self.team_tab.refresh()
        elif idx == 3:
            self.request_tab.refresh()


def main():
    db.init_db()
    app = QApplication(sys.argv)
    app.setFont(QFont(_load_app_font(), 10))
    app.setStyle('Fusion')

    # 상주 솔버 워커를 미리 띄운다(OR-Tools를 백그라운드에서 선(先)import → 첫 생성 빠름).
    scheduler.start_solver_service()
    app.aboutToQuit.connect(scheduler.shutdown_solver_service)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
