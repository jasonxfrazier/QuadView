from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

root = Path(SPECPATH).parent
browser_root = Path(os.environ['QUADVIEW_BROWSER_BUNDLE'])
pw_datas, pw_binaries, pw_hidden = collect_all('playwright')
datas = pw_datas + [(str(browser_root), 'ms-playwright')]
datas += [(str(root / 'build/third-party'), 'third-party')]
datas += collect_data_files('PySide6', includes=['**/LICENSE*', '**/COPYING*'])
a = Analysis([str(root / 'main.py')], pathex=[str(root)],
    binaries=pw_binaries, datas=datas,
    hiddenimports=pw_hidden + ['win32timezone'],
    hookspath=[], runtime_hooks=[str(root / 'packaging/runtime_hook.py')],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
              'PySide6.QtQml', 'PySide6.QtQuick'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='QuadView',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, icon=str(root / 'build/quadview.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='QuadView')
