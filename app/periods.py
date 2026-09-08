# -*- coding: utf-8 -*-
"""
Сроки подачи документов на награды.

Данные сняты с файла «Сроки.xlsx»: там сроки нарисованы полосами по дням
года, и каждая полоса переведена здесь в понятный промежуток. Сроки
государственных наград уточнены отдельно — в таблице они заданы событиями
(«Заслуженные учителя Российской Федерации», «Награды ко Дню науки»), а не
наградами из справочника.

Кроме самих промежутков модуль отвечает на вопрос «можно ли подавать
документы сегодня»: по этому ответу приложение закрывает награды, срок
которых ещё не наступил, и предупреждает о тех, чей срок вот-вот истечёт.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

#: Промежуток подачи: (месяц с, день с, месяц по, день по).
#: Если конец раньше начала, промежуток переходит через новый год.
Period = Tuple[int, int, int, int]

#: Отметка «круглый год»
WHOLE_YEAR = "круглый год"

#: За сколько дней до конца приёма награда помечается предупреждением
WARN_DAYS = 14

_MP_COMMON: List[Period] = [(11, 10, 1, 10)]

PERIODS: Dict[str, object] = {
    # --- уровень 1 ---
    "minobrko1": [(1, 10, 2, 10)],           # «Педагог-наставник»
    "minobrko2": WHOLE_YEAR,
    "minobrko3": WHOLE_YEAR,

    # --- уровень 2: областные награды — приём круглый год ---
    "nagrko1": WHOLE_YEAR, "nagrko2": WHOLE_YEAR, "nagrko3": WHOLE_YEAR,
    "nagrko4": WHOLE_YEAR, "nagrko5": WHOLE_YEAR, "nagrko6": WHOLE_YEAR,
    "nagrko7": WHOLE_YEAR, "nagrko8": WHOLE_YEAR,

    # --- уровень 3: Министерство просвещения ---
    # «Отличник просвещения» принимается четырьмя окнами в году
    "minpros1": [(12, 10, 1, 10), (3, 10, 4, 10), (6, 10, 7, 10),
                 (9, 10, 10, 10)],
    "minpros7": [(9, 10, 10, 10)],           # «Почетный наставник»
    "minpros2": _MP_COMMON, "minpros3": _MP_COMMON, "minpros4": _MP_COMMON,
    "minpros5": _MP_COMMON, "minpros6": _MP_COMMON, "minpros8": _MP_COMMON,
    "minpros9": _MP_COMMON, "minpros10": _MP_COMMON,

    # --- уровень 4: государственные награды ---
    "gosnagr1": WHOLE_YEAR,                  # Медаль ордена «За заслуги перед Отечеством»
    "gosnagr2": WHOLE_YEAR,                  # «За заслуги в освоении космоса»
    "gosnagr3": WHOLE_YEAR,                  # «За заслуги в освоении атомной энергии»
    "gosnagr4": WHOLE_YEAR,                  # Знак отличия «За наставничество»
    "gosnagr5": [(7, 10, 8, 10)],            # Почетные звания Российской Федерации
}

_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
           "августа", "сентября", "октября", "ноября", "декабря"]


def _dm(month: int, day: int) -> str:
    return f"{day:02d}.{month:02d}"


def _human(day: date) -> str:
    """«10 сентября» — так дата читается легче, чем «10.09»."""
    return f"{day.day} {_MONTHS[day.month - 1]}"


def _days_word(n: int) -> str:
    """Правильная форма слова «день» при числе n."""
    rest = abs(n) % 100
    if 11 <= rest <= 14:
        return "дней"
    rest %= 10
    if rest == 1:
        return "день"
    if 2 <= rest <= 4:
        return "дня"
    return "дней"


def days_text(n: int) -> str:
    return f"{n} {_days_word(n)}"


def text_for(award_id: str) -> str:
    """Срок подачи одной строкой — для плитки награды."""
    value = PERIODS.get(award_id)
    if value is None:
        return ""
    if value == WHOLE_YEAR:
        return "Подача: круглый год"
    parts = [f"с {_dm(m1, d1)} по {_dm(m2, d2)}" for m1, d1, m2, d2 in value]
    return "Подача: " + ", ".join(parts)


def _window(period: Period, year: int) -> Tuple[date, date]:
    """
    Границы одного промежутка в конкретном году.

    Промежуток может переходить через новый год: тогда конец берётся
    из следующего года.
    """
    m1, d1, m2, d2 = period
    start = date(year, m1, d1)
    end_year = year if (m2, d2) >= (m1, d1) else year + 1
    return start, date(end_year, m2, d2)


def _all_windows(periods: List[Period], today: date) -> List[Tuple[date, date]]:
    """Все промежутки вокруг текущей даты — прошлый, этот и следующий год."""
    out = []
    for year in (today.year - 1, today.year, today.year + 1):
        for period in periods:
            out.append(_window(period, year))
    return sorted(out)


def status_for(award_id: str, today: Optional[date] = None) -> dict:
    """
    Можно ли сегодня подавать документы на эту награду.

    Возвращает:
      ``open``      — приём открыт;
      ``period``    — срок одной строкой для плитки;
      ``closes_on`` — дата окончания приёма («10 октября»), если он открыт;
      ``days_left`` — сколько дней осталось до конца приёма;
      ``warning``   — приём кончается совсем скоро (см. WARN_DAYS);
      ``opens_on``  — когда приём откроется, если сейчас он закрыт;
      ``message``   — готовое объяснение для пользователя.

    Для наград, срок которых не задан, приём считается открытым: запрещать
    то, о чём ничего не известно, было бы неправильно.
    """
    today = today or date.today()
    value = PERIODS.get(award_id)
    period_text = text_for(award_id)

    if value is None or value == WHOLE_YEAR:
        return {"open": True, "period": period_text, "whole_year": True,
                "days_left": None, "warning": False,
                "closes_on": "", "opens_on": "", "message": ""}

    windows = _all_windows(list(value), today)

    for start, end in windows:
        if start <= today <= end:
            days_left = (end - today).days
            warning = days_left <= WARN_DAYS
            message = ""
            if warning:
                message = (
                    "Приём документов на эту награду заканчивается "
                    f"{_human(end)}. " +
                    ("Сегодня последний день." if days_left == 0
                     else f"Осталось {days_text(days_left)}.")
                )
            return {"open": True, "period": period_text, "whole_year": False,
                    "days_left": days_left, "warning": warning,
                    "closes_on": _human(end), "opens_on": "",
                    "message": message}

    upcoming = [start for start, _end in windows if start > today]
    opens = min(upcoming) if upcoming else None
    if opens is None:
        return {"open": True, "period": period_text, "whole_year": False,
                "days_left": None, "warning": False,
                "closes_on": "", "opens_on": "", "message": ""}

    wait = (opens - today).days
    return {
        "open": False, "period": period_text, "whole_year": False,
        "days_left": None, "warning": False, "closes_on": "",
        "opens_on": _human(opens),
        "message": (f"Приём документов на эту награду откроется "
                    f"{_human(opens)} — через {days_text(wait)}."),
    }


def is_open(award_id: str, today: Optional[date] = None) -> bool:
    """Короткий ответ: принимаются ли сегодня документы на эту награду."""
    return bool(status_for(award_id, today)["open"])
