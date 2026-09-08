# -*- coding: utf-8 -*-
"""
Низкоуровневый слой формирования PDF.

Бланки воспроизводятся из JSON-шаблонов, снятых с официальных документов:
каждый глиф и линия ставятся в те же координаты, что и в оригинале.
Поверх пустого бланка накладываются значения, введённые пользователем.

Система координат: `top` — расстояние от ВЕРХА страницы (как в исходных
документах). Пересчёт в координаты ReportLab выполняется внутри.
"""
from __future__ import annotations

import json
import os
from typing import Iterable, List, Optional, Sequence, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

from .paths import resource

# ---------------------------------------------------------------- шрифты ---

#: Доля кегля, на которую базовая линия ниже верха строки.
#: Значения получены калибровкой по каждой гарнитуре — они различаются,
#: поэтому единый коэффициент давал бы сдвиг на моноширинных бланках.
BASELINE_FACTORS = {
    "R": 0.7840, "B": 0.7840, "I": 0.7840, "BI": 0.7840,
    "M": 0.6980, "MB": 0.6980, "S": 0.7900, "SB": 0.7900,
}
BASELINE_FACTOR = BASELINE_FACTORS["R"]

# ------------------------------------------------------- поля страницы ---
#
# Готовые документы идут на печать, поэтому всё содержимое должно лежать
# в пределах полей — иначе принтер обрежет край. Границы сняты с самих
# официальных бланков: их содержимое укладывается в x 55.3..568.3 и
# top 30.1..773.0. Лист A4 — 595.3×841.9, то есть остаётся 55 pt слева,
# 27 сверху, 25 справа и 69 снизу. Непечатаемая зона бытового принтера —
# обычно 4–6 мм (11–17 pt), так что запас есть со всех сторон.
#
# Правило простое: если текст или таблица не помещаются до нижней границы,
# создаётся новая страница. Уменьшать кегль нельзя ни при каких условиях.

MARGIN_LEFT = 55.0         # левая граница содержимого
MARGIN_RIGHT = 570.0       # правая граница содержимого (координата x)
MARGIN_TOP = 28.0          # верхняя граница (top)
MARGIN_BOTTOM = 790.0      # нижняя граница (top), ниже неё не пишем

#: с какой отметки начинается содержимое на новых страницах
CONTENT_TOP = 60.0


def inside_page(x0: float, top: float, x1: Optional[float] = None,
                bottom: Optional[float] = None) -> bool:
    """Проверяет, что прямоугольник целиком лежит в пределах полей."""
    x1 = x0 if x1 is None else x1
    bottom = top if bottom is None else bottom
    return (MARGIN_LEFT <= min(x0, x1) and max(x0, x1) <= MARGIN_RIGHT
            and MARGIN_TOP <= min(top, bottom)
            and max(top, bottom) <= MARGIN_BOTTOM)


#: Насколько базовая линия значения выше линии-подчёркивания.
#:
#: Подобрано по самим бланкам: в них подпись поля стоит ровно на 15.1 pt
#: выше своей линии, а базовая линия текста кегля 12 — на 9.41 pt ниже его
#: верхнего края. Разница 5.7 pt и ставит вписанное значение на ту же
#: строку, что и печатный текст бланка, а не заметно ниже неё.
VALUE_LIFT = 5.7

_FONT_DIR = resource("assets", "fonts")

# Имена шрифтов, регистрируемые в ReportLab
FONT_MAP = {
    "R": "Doc-Serif",
    "B": "Doc-Serif-Bold",
    "I": "Doc-Serif-Italic",
    "BI": "Doc-Serif-BoldItalic",
    "M": "Doc-Mono",
    "MB": "Doc-Mono-Bold",
    "S": "Doc-Sans",
    "SB": "Doc-Sans-Bold",
}

# Кандидаты файлов: сначала системные Windows-шрифты (точное совпадение с
# оригиналом), затем свободные метрически совместимые из комплекта поставки.
_FONT_FILES = {
    "R":  ["times.ttf",   "LiberationSerif-Regular.ttf"],
    "B":  ["timesbd.ttf", "LiberationSerif-Bold.ttf"],
    "I":  ["timesi.ttf",  "LiberationSerif-Italic.ttf"],
    "BI": ["timesbi.ttf", "LiberationSerif-BoldItalic.ttf"],
    "M":  ["cour.ttf",    "LiberationMono-Regular.ttf", "LiberationSerif-Regular.ttf"],
    "MB": ["courbd.ttf",  "LiberationMono-Bold.ttf",    "LiberationSerif-Bold.ttf"],
    "S":  ["arial.ttf",   "LiberationSans-Regular.ttf", "LiberationSerif-Regular.ttf"],
    "SB": ["arialbd.ttf", "LiberationSans-Bold.ttf",    "LiberationSerif-Bold.ttf"],
}

_WIN_FONT_DIRS = [
    r"C:\Windows\Fonts",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
]

_fonts_ready = False


def _find_font_file(names: Sequence[str]) -> Optional[str]:
    """Ищет файл шрифта: сначала в комплекте приложения, затем в системе."""
    for name in names:
        local = os.path.join(_FONT_DIR, name)
        if os.path.exists(local):
            return local
    for name in names:
        for d in _WIN_FONT_DIRS:
            if not d:
                continue
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    # общий случай для Linux/macOS при разработке
    for name in names:
        for d in ("/usr/share/fonts/truetype/liberation",
                  "/usr/share/fonts/truetype/dejavu"):
            p = os.path.join(d, name)
            if os.path.exists(p):
                return p
    return None


def ensure_fonts() -> None:
    """Регистрирует шрифты в ReportLab (однократно)."""
    global _fonts_ready
    if _fonts_ready:
        return
    for code, alias in FONT_MAP.items():
        path = _find_font_file(_FONT_FILES[code])
        if path is None:
            raise RuntimeError(
                f"Не найден файл шрифта для начертания «{code}». "
                f"Ожидался один из: {', '.join(_FONT_FILES[code])}"
            )
        pdfmetrics.registerFont(TTFont(alias, path))
    _fonts_ready = True


def font_name(code: str) -> str:
    return FONT_MAP.get(code, FONT_MAP["R"])


# ------------------------------------------------------------------ лист ---

class Sheet:
    """
    Страница документа с координатами, отсчитываемыми от верха листа.

    Инкапсулирует ReportLab-canvas и переводит `top` в его систему координат.
    """

    def __init__(self, canvas: rl_canvas.Canvas, page_w: float, page_h: float):
        self.c = canvas
        self.page_w = page_w
        self.page_h = page_h

    # --- преобразование координат ---

    def y_of_top(self, top: float) -> float:
        """Координата ReportLab для отметки `top` от верха страницы."""
        return self.page_h - top

    def baseline(self, top: float, size: float, code: str = "R") -> float:
        """Базовая линия текста, чей верхний край находится на `top`."""
        return self.page_h - top - BASELINE_FACTORS.get(code, BASELINE_FACTOR) * size

    # --- примитивы ---

    def glyph(self, text: str, x: float, top: float, size: float,
              code: str = "R") -> None:
        self.c.setFont(font_name(code), size)
        self.c.drawString(x, self.baseline(top, size, code), text)

    def text(self, text: str, x: float, top: float, size: float = 12.0,
             code: str = "R") -> None:
        self.glyph(text, x, top, size, code)

    def text_centered(self, text: str, cx: float, top: float,
                      size: float = 12.0, code: str = "R") -> None:
        w = pdfmetrics.stringWidth(text, font_name(code), size)
        self.glyph(text, cx - w / 2.0, top, size, code)

    def hline(self, x0: float, x1: float, top: float,
              width: float = 0.5) -> None:
        y = self.y_of_top(top)
        self.c.setLineWidth(width)
        self.c.line(x0, y, x1, y)

    def vline(self, x: float, top: float, bottom: float,
              width: float = 0.5) -> None:
        self.c.setLineWidth(width)
        self.c.line(x, self.y_of_top(top), x, self.y_of_top(bottom))

    def rect(self, x0: float, top: float, x1: float, bottom: float,
             width: float = 0.5) -> None:
        self.c.setLineWidth(width)
        self.c.rect(x0, self.y_of_top(bottom), x1 - x0,
                    self.y_of_top(top) - self.y_of_top(bottom), stroke=1, fill=0)

    # --- работа с текстом ---

    @staticmethod
    def width_of(text: str, size: float, code: str = "R") -> float:
        return pdfmetrics.stringWidth(text, font_name(code), size)

    def fit_size(self, text: str, max_width: float, size: float,
                 code: str = "R", min_size: float = 7.0) -> float:
        """Подбирает кегль, при котором текст умещается в заданную ширину."""
        s = size
        while s > min_size and self.width_of(text, s, code) > max_width:
            s -= 0.25
        return s

    def break_word(self, word: str, max_width: float, size: float,
                   code: str = "R") -> List[str]:
        """
        Делит слово, которое само по себе шире строки.

        Нужно для узких граф таблиц: кегль не уменьшается, поэтому слишком
        длинное слово переносится, а не выходит за границу ячейки. На месте
        разрыва ставится дефис — иначе «настоящее» превращалось в «насто» и
        «ящее» без всякого признака переноса, и читалось это как опечатка.
        """
        hyphen_w = self.width_of("-", size, code)
        parts, cur = [], ""
        for ch in word:
            # на строке должно остаться место ещё и под знак переноса
            if cur and self.width_of(cur + ch, size, code) + hyphen_w > max_width:
                parts.append(cur + "-")
                cur = ch
            else:
                cur += ch
        if cur:
            parts.append(cur)
        if len(parts) == 1:
            return parts
        # если места не хватило даже на один символ с дефисом — рвём как есть
        return parts or [word]

    def wrap(self, text: str, max_width: float, size: float,
             code: str = "R") -> List[str]:
        """
        Разбивает текст на строки по ширине.

        Кегль никогда не уменьшается: если слово не помещается целиком,
        оно переносится по буквам.
        """
        out: List[str] = []
        for para in str(text).split("\n"):
            words = para.split()
            if not words:
                out.append("")
                continue
            cur = ""
            for w in words:
                trial = (cur + " " + w).strip()
                if self.width_of(trial, size, code) <= max_width:
                    cur = trial
                    continue
                if cur:
                    out.append(cur)
                    cur = ""
                if self.width_of(w, size, code) <= max_width:
                    cur = w
                else:
                    pieces = self.break_word(w, max_width, size, code)
                    out.extend(pieces[:-1])
                    cur = pieces[-1]
            if cur:
                out.append(cur)
        return out

    # --- заполнение полей бланка ---

    def value_on_line(self, text: str, x0: float, x1: float, line_top: float,
                      size: float = 12.0, code: str = "R",
                      align: str = "left", min_size: float = 7.0) -> None:
        """
        Пишет значение над линией-подчёркиванием, начинающейся в (x0..x1).

        Кегль не подбирается: он всегда одинаков во всём документе. За тем,
        чтобы текст помещался, следит вызывающая сторона — она делит значение
        на строки. Параметр `min_size` сохранён для совместимости и не влияет
        на вывод.
        """
        text = (text or "").strip()
        if not text:
            return
        baseline = self.y_of_top(line_top) + VALUE_LIFT
        self.c.setFont(font_name(code), size)
        if align == "center":
            w = self.width_of(text, size, code)
            self.c.drawString(x0 + max((x1 - x0 - w) / 2.0, 2.0), baseline, text)
        else:
            self.c.drawString(x0 + 2.0, baseline, text)

    def value_on_lines(self, text: str, segments: Sequence[Tuple[float, float, float]],
                       size: float = 12.0, code: str = "R",
                       align: str = "left") -> str:
        """
        Распределяет длинное значение по нескольким линиям бланка.

        `segments` — последовательность (x0, x1, line_top).
        Возвращает остаток, не поместившийся в отведённые линии.
        """
        text = " ".join(str(text or "").split())
        if not text or not segments:
            return text
        words = text.split()
        idx = 0
        for (x0, x1, top) in segments:
            if idx >= len(words):
                break
            avail = x1 - x0 - 4.0
            cur = ""
            while idx < len(words):
                trial = (cur + " " + words[idx]).strip()
                if self.width_of(trial, size, code) <= avail or not cur:
                    cur = trial
                    idx += 1
                else:
                    break
            self.value_on_line(cur, x0, x1, top, size, code, align)
        return " ".join(words[idx:])

    def justified_line(self, line: str, x: float, top: float, width: float,
                       size: float, code: str = "R") -> None:
        """
        Выводит строку, растянутую по ширине за счёт межсловных пробелов.

        Так оформлены характеристики: текст выключен по ширине, как в
        исходных документах, при этом кегль остаётся неизменным.
        """
        words = line.split()
        if len(words) < 2:
            self.glyph(line, x, top, size, code)
            return
        text_w = sum(self.width_of(w, size, code) for w in words)
        gaps = len(words) - 1
        space = (width - text_w) / gaps
        if space < self.width_of(" ", size, code):
            # строка и так плотная — оставляем обычные пробелы
            self.glyph(line, x, top, size, code)
            return

        baseline = self.baseline(top, size, code)
        self.c.setFont(font_name(code), size)
        cur = x
        for word in words:
            self.c.drawString(cur, baseline, word)
            cur += self.width_of(word, size, code) + space

    def flow_text(self, text: str, x: float, top: float, max_width: float,
                  max_top: float, size: float = 12.0, code: str = "R",
                  leading: Optional[float] = None,
                  first_indent: float = 0.0,
                  justify: bool = False) -> Tuple[str, float]:
        """
        Выводит абзацы текста сверху вниз в заданной области.

        При `justify=True` строки выключаются по ширине; последняя строка
        абзаца остаётся выключенной влево, как это принято в вёрстке.

        Возвращает (непоместившийся остаток, `top` после последней строки).
        """
        leading = leading or size * 1.15
        cur_top = top
        remaining_paragraphs = []
        paragraphs = str(text or "").split("\n")
        overflow = False

        for pi, para in enumerate(paragraphs):
            if not para.strip():
                cur_top += leading
                continue

            indent = first_indent
            lines: List[str] = []
            words = para.split()
            cur = ""
            while words:
                w = words[0]
                trial = (cur + " " + w).strip()
                limit = (max_width - indent) if not lines else max_width
                if self.width_of(trial, size, code) <= limit:
                    cur = trial
                    words.pop(0)
                elif not cur:
                    # одиночное слово шире строки — переносим по буквам
                    pieces = self.break_word(w, limit, size, code)
                    lines.extend(pieces[:-1])
                    cur = pieces[-1]
                    words.pop(0)
                else:
                    lines.append(cur)
                    cur = ""
            if cur:
                lines.append(cur)

            for li, line in enumerate(lines):
                if cur_top + size > max_top:
                    # Место кончилось. Остаток абзаца и все следующие абзацы
                    # уходят в возвращаемый «хвост» — ровно по одному разу.
                    # Раньше они попадали туда дважды: и здесь, и на новом
                    # витке внешнего цикла, отчего конец характеристики
                    # печатался в документе два раза подряд.
                    remaining_paragraphs.append(" ".join(lines[li:]))
                    remaining_paragraphs.extend(paragraphs[pi + 1:])
                    overflow = True
                    break
                dx = indent if li == 0 else 0.0
                is_last = (li == len(lines) - 1)
                if justify and not is_last:
                    self.justified_line(line, x + dx, cur_top,
                                        max_width - dx, size, code)
                else:
                    self.glyph(line, x + dx, cur_top, size, code)
                cur_top += leading

            if overflow:
                break

        return "\n".join(remaining_paragraphs).strip(), cur_top


# -------------------------------------------------------------- шаблоны ---

_template_cache: dict = {}
_TEMPLATE_DIR = resource("app", "templates")


def load_template(name: str) -> dict:
    """Загружает JSON-шаблон бланка (с кэшированием)."""
    if name in _template_cache:
        return _template_cache[name]
    path = os.path.join(_TEMPLATE_DIR, name + ".json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Шаблон бланка не найден: {path}")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    _template_cache[name] = data
    return data


def draw_template_page(sheet: Sheet, template: dict, page_index: int,
                       skip_regions: Iterable[Tuple[float, float]] = (),
                       skip_line_regions: Iterable[Tuple[float, float]] = (),
                       hide_labels: Iterable[Tuple[float, float, float]] = ()
                       ) -> None:
    """
    Отрисовывает пустой бланк из шаблона.

    `skip_regions` — интервалы (top_from, top_to), которые не выводятся вовсе.
    `skip_line_regions` — интервалы, где пропускаются только линии, но текст
    сохраняется (нужно для таблиц: заголовок остаётся, рамки строятся заново).
    `hide_labels` — надписи (top, x_from, x_to), которые нужно убрать: на их
    место приложение выводит собственный текст, например должность
    подписывающего вместо готовой формулировки бланка.
    """
    page = template["pages"][page_index]
    regions = list(skip_regions)
    line_regions = list(skip_line_regions) + regions
    labels = list(hide_labels)

    def skipped(top: float) -> bool:
        return any(a <= top <= b for a, b in regions)

    def line_skipped(top: float) -> bool:
        return any(a <= top <= b for a, b in line_regions)

    def label_hidden(x: float, top: float) -> bool:
        return any(abs(top - lt) < 1.5 and lx0 <= x <= lx1
                   for lt, lx0, lx1 in labels)

    for text, x, top, size, code in page["chars"]:
        if skipped(top) or label_hidden(x, top):
            continue
        sheet.glyph(text, x, top, size, code)

    for ln in page["lines"]:
        if len(ln) >= 5:                      # вертикальный отрезок
            x0, _x1, top, w, bottom = ln[:5]
            if line_skipped(top) or line_skipped(bottom):
                continue
            sheet.vline(x0, top, bottom, w)
        else:
            x0, x1, top, w = ln[:4]
            if line_skipped(top):
                continue
            sheet.hline(x0, x1, top, w)

    for x0, top, x1, bottom, w in page["rects"]:
        if line_skipped(top) or line_skipped(bottom):
            continue
        sheet.rect(x0, top, x1, bottom, w)


def draw_template_region(sheet: Sheet, template: dict, page_index: int,
                         top_from: float, top_to: float,
                         dy: float = 0.0, dx: float = 0.0,
                         hide_labels: Iterable[Tuple[float, float, float]] = (),
                         chars_only: bool = False) -> None:
    """
    Отрисовывает фрагмент шаблона, сдвинутый на (dx, dy).

    Нужен, когда таблица переменной длины смещает нижележащие блоки бланка
    (подписи, «М.П.», заголовки) — они переносятся вместе со сдвигом.
    `hide_labels` — надписи (top, x_from, x_to), которые заменяются своим
    текстом и потому не выводятся.
    `chars_only` — выводить только текст, без линий и рамок. Нужно для
    заголовков таблиц: подписи граф берутся из бланка, а рамки строятся
    заново по фактическому числу строк.
    """
    page = template["pages"][page_index]
    labels = list(hide_labels)

    def label_hidden(x: float, top: float) -> bool:
        return any(abs(top - lt) < 1.5 and lx0 <= x <= lx1
                   for lt, lx0, lx1 in labels)

    for text, x, top, size, code in page["chars"]:
        if top_from <= top < top_to and not label_hidden(x, top):
            sheet.glyph(text, x + dx, top + dy, size, code)

    if chars_only:
        return

    for ln in page["lines"]:
        if len(ln) >= 5:
            x0, _x1, top, w, bottom = ln[:5]
            if top_from <= top < top_to:
                sheet.vline(x0 + dx, top + dy, bottom + dy, w)
        else:
            x0, x1, top, w = ln[:4]
            if top_from <= top < top_to:
                sheet.hline(x0 + dx, x1 + dx, top + dy, w)

    for x0, top, x1, bottom, w in page["rects"]:
        if top_from <= top < top_to:
            sheet.rect(x0 + dx, top + dy, x1 + dx, bottom + dy, w)


def region_bounds(template: dict, page_index: int, top_from: float,
                  top_to: float) -> Tuple[Optional[float], Optional[float]]:
    """
    Верх и низ содержимого в куске шаблона (или (None, None), если он пуст).

    По этим границам считается, сколько пустого места между соседними
    полосами бланка: именно его и можно поджать, когда титульный лист
    иначе не помещается на одну страницу.
    """
    page = template["pages"][page_index]
    top: Optional[float] = None
    bottom: Optional[float] = None

    def note(a: float, b: float) -> None:
        nonlocal top, bottom
        top = a if top is None else min(top, a)
        bottom = b if bottom is None else max(bottom, b)

    for _text, _x, at, size, _code in page["chars"]:
        if top_from <= at < top_to:
            note(at, at + size)
    for ln in page["lines"]:
        at = ln[2]
        if top_from <= at < top_to:
            note(at, ln[4] if len(ln) >= 5 else at)
    for _x0, at, _x1, low, _w in page["rects"]:
        if top_from <= at < top_to:
            note(at, low)
    return top, bottom


def region_bottom(template: dict, page_index: int,
                  top_from: float, top_to: float) -> float:
    """
    Самая нижняя отметка содержимого в куске шаблона.

    Нужна, чтобы заранее понять, поместится ли очередная полоса бланка до
    нижнего поля страницы. Пустой кусок даёт `top_from`: занимать место
    ему нечем.
    """
    page = template["pages"][page_index]
    lowest = top_from
    for _text, _x, top, size, _code in page["chars"]:
        if top_from <= top < top_to:
            lowest = max(lowest, top + size)
    for ln in page["lines"]:
        top = ln[2]
        if top_from <= top < top_to:
            lowest = max(lowest, ln[4] if len(ln) >= 5 else top)
    for _x0, top, _x1, bottom, _w in page["rects"]:
        if top_from <= top < top_to:
            lowest = max(lowest, bottom)
    return lowest


def template_region_height(template: dict, page_index: int,
                           top_from: float, top_to: float) -> float:
    """Фактическая высота содержимого фрагмента шаблона."""
    page = template["pages"][page_index]
    lo, hi = None, None
    for _t, _x, top, size, _c in page["chars"]:
        if top_from <= top < top_to:
            lo = top if lo is None else min(lo, top)
            hi = top + size if hi is None else max(hi, top + size)
    for ln in page["lines"]:
        top = ln[2]
        if top_from <= top < top_to:
            bottom = ln[4] if len(ln) >= 5 else top
            lo = top if lo is None else min(lo, top)
            hi = bottom if hi is None else max(hi, bottom)
    if lo is None:
        return 0.0
    return hi - lo


def blank_sheet(page_size=A4) -> "Sheet":
    """
    Лист «в никуда» — для измерений перед настоящей отрисовкой.

    Нужен, чтобы заранее посчитать, сколько места займёт заполненный бланк:
    ширины строк зависят от шрифта, а он известен только ReportLab. Всё
    нарисованное на таком листе выбрасывается.
    """
    import io
    ensure_fonts()
    canvas = rl_canvas.Canvas(io.BytesIO(), pagesize=page_size)
    return Sheet(canvas, page_size[0], page_size[1])


class Document:
    """Формируемый PDF-документ: последовательность бланков в одном файле."""

    def __init__(self, path: str, page_size=A4):
        ensure_fonts()
        self.page_w, self.page_h = page_size
        self.c = rl_canvas.Canvas(path, pagesize=page_size)
        self.c.setTitle("Документы на награждение")
        self._started = False

    def new_sheet(self) -> Sheet:
        """Начинает новую страницу и возвращает лист для рисования."""
        if self._started:
            self.c.showPage()
        self._started = True
        return Sheet(self.c, self.page_w, self.page_h)

    def save(self) -> None:
        self.c.save()
