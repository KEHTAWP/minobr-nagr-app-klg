# -*- coding: utf-8 -*-
"""
Поиск файлов приложения — одинаково при запуске из исходников и из .exe.

PyInstaller распаковывает вложенные файлы во временную папку и кладёт путь
к ней в ``sys._MEIPASS``. Опираться на ``__file__`` модуля ненадёжно: при
сборке он может указывать внутрь архива. Поэтому корень определяется явно.
"""
from __future__ import annotations

import os
import sys


def app_root() -> str:
    """Корневая папка приложения (в собранном виде — папка распаковки)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource(*parts: str) -> str:
    """Путь к файлу приложения относительно его корня."""
    return os.path.join(app_root(), *parts)
