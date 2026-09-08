# -*- coding: utf-8 -*-
"""
Совместимость со старыми версиями Python (нужно для сборки под Windows 7).

В Python 3.9 у функций модуля ``hashlib`` появился параметр
``usedforsecurity``. Библиотека reportlab им пользуется, из-за чего на
Python 3.8 — последней версии, работающей на Windows 7 — формирование PDF
падало с ошибкой «'usedforsecurity' is an invalid keyword argument».

Параметр носит информационный характер: он лишь сообщает системе, что хеш
считается не ради криптографической защиты (reportlab строит по нему
идентификатор документа). На результат он не влияет, поэтому на старом
Python его можно просто отбросить — документ получится точно такой же.

На Python 3.9 и новее модуль ничего не меняет.
"""
from __future__ import annotations

import hashlib
import sys

_applied = False


def _needs_patch() -> bool:
    """Проверяет, отвергает ли hashlib параметр ``usedforsecurity``."""
    try:
        hashlib.md5(b"", usedforsecurity=False)
        return False
    except TypeError:
        return True
    except Exception:                                  # noqa: BLE001
        return False


def apply(force: bool = False) -> bool:
    """
    Включает совместимость, если она нужна.

    Возвращает True, если обёртки были установлены.
    """
    global _applied
    if _applied:
        return True
    if not force and not _needs_patch():
        return False

    def wrap(func):
        def wrapper(*args, **kwargs):
            kwargs.pop("usedforsecurity", None)
            return func(*args, **kwargs)
        wrapper.__name__ = getattr(func, "__name__", "hash")
        return wrapper

    for name in ("md5", "sha1", "sha224", "sha256", "sha384", "sha512",
                 "blake2b", "blake2s", "new"):
        original = getattr(hashlib, name, None)
        if original is not None:
            setattr(hashlib, name, wrap(original))

    _applied = True
    return True


#: Применяется при импорте пакета: к моменту формирования PDF всё готово.
PATCHED = apply()

#: Для сообщений в самопроверке
PYTHON_VERSION = ".".join(str(p) for p in sys.version_info[:3])
