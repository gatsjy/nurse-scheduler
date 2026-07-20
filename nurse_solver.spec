# -*- mode: python ; coding: utf-8 -*-
# 별도 솔버 실행파일 — PyQt를 절대 포함하지 않는다(OR-Tools와 DLL 충돌 회피).
from PyInstaller.utils.hooks import collect_all

ortool_datas, ortool_bins, ortool_hiddens = collect_all('ortools')

a = Analysis(
    ['solver_cli.py'],
    pathex=[],
    binaries=ortool_bins,
    datas=ortool_datas,
    hiddenimports=['ortools.sat.python.cp_model', *ortool_hiddens],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'PIL', 'tkinter', 'PyQt5', 'PyQt5.sip'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='nurse_solver',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    upx_exclude=[], runtime_tmpdir=None,
    console=True,               # 콘솔 앱(창은 부모가 CREATE_NO_WINDOW로 숨김)
    disable_windowed_traceback=False, argv_emulation=False, icon=None,
)
