# -*- mode: python ; coding: utf-8 -*-
"""
Сборка приложения в один исполняемый файл Windows.

Запуск:  pyinstaller minobr.spec --noconfirm
Результат: dist\\ПорталНаград.exe
"""

block_cipher = None

# Ресурсы, которые обязаны попасть внутрь .exe
datas = [
    ('web', 'web'),                    # интерфейс: html, css, js, изображения
    ('app/templates', 'app/templates'),  # шаблоны официальных бланков
    ('assets/fonts', 'assets/fonts'),  # шрифты для формирования PDF
]

# Установщик WebView2 не обязателен: если его положили в assets/webview2,
# он попадёт в сборку, и программа сможет предложить установку компонента.
import os as _os
if _os.path.isdir('assets/webview2') and any(
        f.lower().endswith('.exe') for f in _os.listdir('assets/webview2')):
    datas.append(('assets/webview2', 'assets/webview2'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # оболочка окна в Windows
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'clr_loader',
        'pythonnet',
        # reportlab подключает эти модули не напрямую
        'reportlab.pdfbase._fontdata_enc_winansi',
        'reportlab.pdfbase._fontdata_enc_macroman',
        # Pillow — обязательная зависимость reportlab
        'PIL',
        'PIL.Image',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Исключаем только то, что заведомо не используется.
    # ВАЖНО: PIL исключать нельзя — без него не запускается reportlab.
    excludes=[
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
    name='ПорталНаград',
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
    icon='assets/icon.ico' if __import__('os').path.exists('assets/icon.ico') else None,
)
