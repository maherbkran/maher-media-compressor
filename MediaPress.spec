# Run from this directory: python -m PyInstaller MediaLite.spec --noconfirm
from pathlib import Path
import os
import sys
# Isolate DLL discovery from unrelated desktop/runtime tools on the build host.
# In particular, Poppler's ICU DLL has versioned exports; Windows' ICU is different.
os.environ['PATH'] = os.pathsep.join([str(Path(sys.executable).parent),
                                     str(Path(os.environ['SystemRoot']) / 'System32'),
                                     os.environ['SystemRoot']])
base = Path(SPECPATH)
binaries = [(str(base / 'tools' / name), 'tools') for name in
            ('ffmpeg.exe', 'ffprobe.exe', 'jpegtran.exe', 'libjpeg-62.dll')]
datas = [(str(base / 'app.ico'), '.'), (str(base / 'licenses'), 'licenses'), (str(base / 'assets'), 'assets')]
a = Analysis([str(base / 'launcher.py')], pathex=[str(base)], binaries=binaries,
             datas=datas, hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
                       'PySide6.QtQml', 'PySide6.QtQuick', 'numpy', 'tkinter', 'matplotlib'],
             noarchive=False, optimize=1)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MediaPress', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          disable_windowed_traceback=False, icon=str(base / 'app.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MediaPress')

