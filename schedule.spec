# -*- mode: python ; coding: utf-8 -*-
# 폴더형 빌드. onefile(schedule_onefile.spec)과 동일 원칙:
#   메인 exe에는 OR-Tools를 넣지 않고(PyQt와 DLL 충돌), 별도 nurse_solver.exe를 번들해
#   서브프로세스로 계산한다.
from PyInstaller.utils.hooks import collect_all

openpyxl_datas, _, _ = collect_all('openpyxl')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=openpyxl_datas + [
        ('assets/D2Coding.ttf', 'assets'),
        ('assets/D2CodingBold.ttf', 'assets'),
        ('dist/nurse_solver.exe', '.'),     # 별도 솔버 실행파일 번들
    ],
    hiddenimports=[
        'openpyxl',
        'PyQt5.sip',
        'PyQt5.QtPrintSupport',
        'pkg_resources.py2_warn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'PIL', 'tkinter', 'ortools', 'numpy', 'pandas'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NurseScheduler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,     # 콘솔창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,         # 아이콘 파일이 있으면 경로 지정 (예: 'icon.ico')
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NurseScheduler',
)
