"""Collect the exact locked browser revision and generate the native icon."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import importlib.metadata
from playwright.sync_api import sync_playwright
from PySide6.QtWidgets import QApplication
from quadview.ui.main_window import make_icon

root = Path(__file__).resolve().parents[1]
bundle = root / 'build/ms-playwright'
if bundle.exists():
    if bundle.resolve().parent != (root / 'build').resolve():
        raise RuntimeError('Browser staging directory is outside the build directory')
    shutil.rmtree(bundle)
if bundle.exists():
    if bundle.resolve().parent != (root / 'build').resolve():
        raise RuntimeError('Browser staging directory is outside the build directory')
    shutil.rmtree(bundle)
with sync_playwright() as pw:
    executable = Path(pw.chromium.executable_path)
if not executable.exists():
    subprocess.run([sys.executable, '-m', 'playwright', 'install', '--no-shell', 'chromium'], check=True)
with sync_playwright() as pw:
    executable = Path(pw.chromium.executable_path)
browser = executable.parents[1]
bundle.mkdir(parents=True, exist_ok=True)
shutil.copytree(browser, bundle / browser.name, dirs_exist_ok=True)
for item in browser.parent.iterdir():
    if item.is_dir() and item.name.startswith(('ffmpeg-', 'winldd-')):
        shutil.copytree(item, bundle / item.name, dirs_exist_ok=True)
app = QApplication([])
if not make_icon().pixmap(128, 128).save(str(root / 'build/quadview.ico'), 'ICO'):
    raise RuntimeError('Could not generate Windows icon')
print('Prepared bundled Chromium and app icon')
notices = root / 'build/third-party'
notices.mkdir(parents=True, exist_ok=True)
for package in ('playwright', 'PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'pywin32', 'greenlet', 'pyee'):
    distribution = importlib.metadata.distribution(package)
    for item in distribution.files or ():
        if 'license' in item.name.lower() or item.name.lower().startswith(('copying', 'notice')):
            source = Path(distribution.locate_file(item))
            if source.is_file():
                target = notices / package / str(item).replace('..', '_')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license, notices / 'Python-LICENSE.txt')
shutil.copy2(root / 'packaging/THIRD-PARTY-NOTICES.txt', notices / 'THIRD-PARTY-NOTICES.txt')
