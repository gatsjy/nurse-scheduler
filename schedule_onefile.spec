# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

# 메인 GUI exe에는 OR-Tools를 넣지 않는다.
#   PyQt(Qt DLL)와 OR-Tools가 같은 프로세스에 공존하면 솔버가 세그폴트/멈춤을 일으킨다.
#   OR-Tools 계산은 함께 번들한 별도 실행파일 nurse_solver.exe에서만 수행한다.
openpyxl_datas, _, _ = collect_all('openpyxl')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=openpyxl_datas + [
        ('assets/D2Coding.ttf', 'assets'),
        ('assets/D2CodingBold.ttf', 'assets'),
        ('dist/nurse_solver.exe', '.'),     # 별도 솔버 실행파일 번들(런타임에 서브프로세스로 실행)
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
    # OR-Tools/numpy/pandas는 메인 exe에서 제외(솔버 exe에만 존재)
    excludes=['matplotlib', 'PIL', 'tkinter', 'ortools', 'numpy', 'pandas'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# onefile: 모든 바이너리/데이터를 EXE 하나에 포함
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NurseScheduler',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # 콘솔창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)
