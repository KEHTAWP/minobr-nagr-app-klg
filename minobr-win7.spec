# -*- mode: python ; coding: utf-8 -*-
"""
Сборка версии для Windows 7.

Отличия от основной сборки (minobr.spec):
  * собирается интерпретатором Python 3.8 — последним, работающим на Win7;
  * не включает pywebview и WebView2: на Windows 7 этого компонента нет,
    поэтому приложение сразу открывается в браузере;
  * в комплект кладётся файл-признак assets/browser_only.marker, который
    и переводит программу в браузерный режим без лишних попыток.

Запуск:  py -3.8 -m PyInstaller minobr-win7.spec --noconfirm --clean
Результат: dist\\ПорталНаград-Win7.exe
"""
import os as _os

block_cipher = None

datas = [
    ('web', 'web'),                      # интерфейс: html, css, js, изображения
    ('app/templates', 'app/templates'),  # шаблоны официальных бланков
    ('assets/fonts', 'assets/fonts'),    # шрифты для формирования PDF
    ('build/browser_only.marker', 'assets'),   # признак браузерного режима
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'reportlab.pdfbase._fontdata_enc_winansi',
        'reportlab.pdfbase._fontdata_enc_macroman',
        'PIL',
        'PIL.Image',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Оконная оболочка в этой сборке не нужна — интерфейс идёт в браузер.
    # PIL исключать нельзя: без него не запускается reportlab.
    excludes=[
        'webview', 'clr', 'clr_loader', 'pythonnet',
        'matplotlib', 'pandas', 'scipy',
        'PySide2', 'PySide6', 'PyQt5', 'PyQt6',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ПорталНаград-Win7',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # окно консоли не показываем
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if _os.path.exists('assets/icon.ico') else None,
)
