# -*- coding: utf-8 -*-
"""
Запись технических сообщений о работе программы.

Нужен отдельный модуль, потому что у собранного .exe нет консоли: обычный
``print`` уходит в никуда, а обращение к ``sys.stderr`` там и вовсе
приводило к ошибке. Модули приложения сообщают о происходящем сюда, а
куда это писать, решает ``main.py`` — он передаёт свою функцию журнала.

В журнал попадают только технические сведения: что происходит при
запуске и текст ошибок. Ничего из того, что пользователь вводит в анкету,
сюда не пишется.
"""
from __future__ import annotations

from typing import Callable, List, Optional

_sink: Optional[Callable[[str], None]] = None

#: последние сообщения — на случай, если журнал ещё не подключён
_buffer: List[str] = []
_BUFFER_LIMIT = 50


def set_sink(func: Optional[Callable[[str], None]]) -> None:
    """Подключает журнал. Всё, что накопилось раньше, уходит в него сразу."""
    global _sink
    _sink = func
    if func is None:
        return
    pending, _buffer[:] = list(_buffer), []
    for message in pending:
        try:
            func(message)
        except Exception:                              # noqa: BLE001
            return


def report(message: str) -> None:
    """Сообщает о событии или ошибке. Сама никогда не падает."""
    if _sink is None:
        _buffer.append(message)
        del _buffer[:-_BUFFER_LIMIT]
        return
    try:
        _sink(message)
    except Exception:                                  # noqa: BLE001
        pass


def report_exception(prefix: str = "") -> str:
    """Записывает текущую ошибку целиком и возвращает её текст."""
    import traceback
    details = traceback.format_exc()
    report((prefix + "\n" if prefix else "") + details.rstrip())
    return details
