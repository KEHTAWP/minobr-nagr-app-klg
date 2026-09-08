# -*- coding: utf-8 -*-
"""
Заполнение бланков наградных документов.

Каждый бланк воспроизводится из JSON-шаблона, снятого с официального
документа: глифы и линии ставятся в те же координаты, что и в оригинале.
Поверх пустого бланка выводятся значения из анкеты.

Бланк отрисовывается «полосами» (см. :class:`FormFiller`). Если значение не
помещается в отведённую строку, оно переносится на дополнительные строки, а
всё, что ниже, сдвигается — так же, как это происходило бы при заполнении
документа в текстовом редакторе. Данные никогда не обрезаются.

Поля для подписей, инициалов и печатей намеренно остаются пустыми — их
заполняют от руки после печати документа.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .pdfkit import (CONTENT_TOP, MARGIN_BOTTOM, MARGIN_LEFT, MARGIN_RIGHT,
                     Document, Sheet, blank_sheet, draw_template_page,
                     draw_template_region, load_template, region_bottom,
                     region_bounds)

#: Предельный `top`, ниже которого не пишем: это нижнее поле страницы.
#: Всё, что не помещается до него, переносится на следующую страницу —
#: документы идут на печать, и обрезанный принтером край недопустим.
PAGE_BOTTOM = MARGIN_BOTTOM
PAGE_TOP = CONTENT_TOP
BODY_SIZE = 12.0
SMALL = 10.0
LEADING = 19.8             # шаг строк бланка

#: Минимальный просвет между полосами бланка при сжатии титульного листа.
#: Меньше — и строки начнут наползать друг на друга.
MIN_BAND_GAP = 3.0

#: Надписи бланков, которые заменяются должностью, введённой пользователем:
#: (номер страницы, top, x от, x до).
#: В кадровой справке и наградном листе Министерства просвещения блок подписи
#: теперь строится заново целиком — там прятать отдельные надписи не нужно.
SIGNER_LABELS = {
    "predstavlenie": [(2, 161.2, 0.0, 270.0)],
}


def _clean(value) -> str:
    """Значение анкеты одной строкой, без лишних пробелов."""
    return " ".join(str(value or "").split())


def _signer(d: dict) -> str:
    """Должность руководителя, подписывающего документы."""
    return _clean(d.get("signer_position"))


def _hr_signer(d: dict) -> str:
    """
    Должность работника кадровой службы.

    В кадровой справке подпись ставит именно кадровик, а не руководитель:
    в бланке так и написано — «Работник кадровой службы или руководитель
    организации». Если поле не заполнено, подписывает руководитель, а если
    и его должность не указана — остаётся типовая надпись бланка.
    """
    return (_clean(d.get("hr_position")) or _signer(d)
            or "Работник кадровой службы или руководитель организации")


def _chair(d: dict) -> str:
    """Председатель общего собрания трудового коллектива."""
    return _clean(d.get("chair_position"))


def _secretary(d: dict) -> str:
    """Секретарь общего собрания трудового коллектива."""
    return _clean(d.get("secretary_position"))


# --------------------------------------------------------------- утилиты ---

def _fio(d: dict) -> str:
    """Фамилия Имя Отчество одной строкой."""
    parts = [d.get("surname", ""), d.get("name", ""), d.get("patronymic", "")]
    return " ".join(p.strip() for p in parts if p and p.strip())


def org_genitive(d: dict) -> str:
    """
    Наименование организации в родительном падеже.

    Пользователь может вписать его сам — тогда берём как есть. Автоматическое
    склонение остаётся запасным вариантом: русский язык слишком богат, чтобы
    полагаться на него в официальном документе.
    """
    manual = _clean(d.get("org_genitive"))
    if manual:
        return manual
    from .textutil import to_genitive
    return to_genitive(_clean(d.get("org_full")))


def fio_genitive(d: dict) -> str:
    """Фамилия, имя и отчество в родительном падеже (если указаны вручную)."""
    return _clean(d.get("fio_genitive")) or _fio(d)


def _work_line(d: dict) -> str:
    """«Организация, должность» — порядок для кадровой справки."""
    org = (d.get("org_full") or "").strip()
    pos = (d.get("position") or "").strip()
    return f"{org}, {pos}" if org and pos else (org or pos)


def _position_line(d: dict) -> str:
    """«Должность, организация» — порядок для наградных листов."""
    org = (d.get("org_full") or "").strip()
    pos = (d.get("position") or "").strip()
    return f"{pos}, {org}" if org and pos else (pos or org)


def _protocol_line(d: dict) -> str:
    """«дата обсуждения, № протокола» одной строкой."""
    date = (d.get("discussion_date") or "").strip()
    num = (d.get("protocol_no") or "").strip()
    parts = []
    if date:
        parts.append(f"от {date}")
    if num:
        parts.append(f"№ {num}")
    return " ".join(parts)


def _draw_signer(sheet: Sheet, text: str, x0: float, x1: float,
                 top: float, size: float) -> float:
    """
    Выводит должность подписывающего на месте типовой надписи бланка.

    Возвращает `top` строки, на которой оказалась последняя строка текста, —
    по ней выравниваются линии для подписи. Число строк не ограничено:
    должность указывается полностью, вместе с наименованием организации,
    и обрезать её нельзя.
    """
    lines = sheet.wrap(text, x1 - x0, size) if text else []
    for i, line in enumerate(lines):
        sheet.glyph(line, x0, top + i * (size * 1.3), size)
    return top + max(len(lines) - 1, 0) * (size * 1.3)


def signature_height(sheet: Sheet, position: str, text_width: float,
                     size: float = BODY_SIZE, seal: bool = True) -> float:
    """
    Сколько места по высоте займёт блок подписи.

    Нужно, чтобы решать заранее: поместится он под текстом или блок целиком
    надо перенести на следующую страницу. Иначе получалось либо «половина
    подписи за краем листа», либо лишний почти пустой лист.
    """
    lines = sheet.wrap(position or "", text_width, size) if position else [""]
    return (max(len(lines) - 1, 0) * size * 1.3 + 12.4 + 16.0
            + (20.0 if seal else 0.0))


def draw_signature_block(sheet: Sheet, top: float, position: str,
                         x0: float = 56.8, text_width: float = 200.0,
                         sign: Tuple[float, float] = (250.0, 370.0),
                         fio: Tuple[float, float] = (390.0, 537.9),
                         size: float = BODY_SIZE,
                         labels: Tuple[str, str] = ("(подпись)", "(ФИО)"),
                         seal: bool = True) -> float:
    """
    Рисует блок «должность — подпись — ФИО» и возвращает `top` под ним.

    Блок строится приложением, а не берётся из бланка: должность вместе с
    полным наименованием организации занимает столько строк, сколько нужно,
    а линии для подписи встают на уровень её последней строки — как это
    выглядит в заполненном от руки документе. Сами подписи и ФИО остаются
    пустыми: их вписывают после печати.
    """
    last = _draw_signer(sheet, position, x0, x0 + text_width, top, size)
    rule = last + 12.4
    sheet.hline(sign[0], sign[1], rule, 0.5)
    sheet.hline(fio[0], fio[1], rule, 0.5)
    sheet.text_centered(labels[0], (sign[0] + sign[1]) / 2.0, rule + 3.0, 10.0)
    sheet.text_centered(labels[1], (fio[0] + fio[1]) / 2.0, rule + 3.0, 10.0)
    bottom = rule + 16.0
    if seal:
        sheet.glyph("М.П.", x0, bottom, BODY_SIZE, "R")
        bottom += 20.0
    return bottom


def draw_position_signature(sheet: Sheet, top: float, position: str,
                            x0: float = 56.8, x1: float = 360.0,
                            sign: Tuple[float, float] = (400.0, 537.9),
                            size: float = BODY_SIZE,
                            seal: bool = True) -> float:
    """
    Вариант блока подписи, в котором должность стоит НА линии бланка.

    Так устроен наградной лист Калужской области: слева линия с подписью
    «(должность руководителя)», справа — линия для подписи. Должность
    занимает столько строк, сколько нужно; линии встают под последней.
    """
    lines = sheet.wrap(position or "", x1 - x0 - 4.0, size) if position else [""]
    for i, line in enumerate(lines):
        sheet.glyph(line, x0 + 2.0, top + i * (size * 1.3), size)
    rule = top + max(len(lines) - 1, 0) * (size * 1.3) + 12.4
    sheet.hline(x0, x1, rule, 0.5)
    sheet.hline(sign[0], sign[1], rule, 0.5)
    sheet.text_centered("(должность руководителя)", (x0 + x1) / 2.0,
                        rule + 3.0, 10.0)
    sheet.text_centered("(подпись)", (sign[0] + sign[1]) / 2.0, rule + 3.0, 10.0)
    bottom = rule + 18.0
    if seal:
        sheet.glyph("М.П.", x0, bottom, BODY_SIZE, "R")
        bottom += 20.0
    return bottom


def _collegial(d: dict) -> str:
    """Наименование коллегиального органа, рекомендовавшего кандидатуру."""
    return _clean(d.get("collegial_body"))


#: шаг дополнительных строк, добавляемых к строке бланка
GROW_LEADING = 15.5


def _grow_lines(sheet: Sheet, text: str, x0: float, x1: float,
                line_top: float, size: float = BODY_SIZE) -> float:
    """
    Пишет значение над линией бланка, добавляя строки, если оно длинное.

    Каждая дополнительная строка получает собственное подчёркивание, а всё,
    что расположено в бланке ниже, вызывающая сторона сдвигает на
    возвращённую величину. Полное наименование организации в родительном
    падеже иначе не помещается и уезжало за край листа.
    """
    text = _clean(text)
    if not text:
        return 0.0
    lines = sheet.wrap(text, x1 - x0 - 4.0, size)
    for i, line in enumerate(lines):
        top = line_top + i * GROW_LEADING
        sheet.value_on_line(line, x0, x1, top, size, align="center")
        if i < len(lines) - 1:
            sheet.hline(x0, x1, top, 0.8)
    return max(len(lines) - 1, 0) * GROW_LEADING


def _draw_mp_signers(sheet: Sheet, top: float, head: str, chair: str) -> float:
    """
    Подписи на листе рекомендации Министерства просвещения.

    Слева руководитель организации, справа председатель общего собрания
    трудового коллектива. В бланке под каждую должность отведено по две
    строки — полного наименования организации туда не втиснуть, поэтому
    блок строится заново: должности занимают сколько нужно, а линии для
    подписей встают под ними. Возвращает `top` под подписями.
    """
    size = SMALL
    # если должность не указана, остаётся типовая надпись бланка
    head = head or "Руководитель организации (органа)"
    chair = chair or "Председатель коллегиального органа организации"
    last = max(_draw_signer(sheet, head, 56.8, 306.1, top, size),
               _draw_signer(sheet, chair, 321.7, 568.3, top, size))
    rule = last + size * 1.3 + 18.0

    for x0, x1 in ((55.3, 171.5), (175.7, 306.1), (321.7, 438.0), (442.2, 568.3)):
        sheet.hline(x0, x1, rule, 0.8)
    for x in (172.9, 439.4):
        sheet.glyph("/", x, rule - 12.4, BODY_SIZE)
    for x0, x1, label in ((55.3, 171.5, "(подпись)"),
                          (175.7, 306.1, "(фамилия, инициалы)"),
                          (321.7, 438.0, "(подпись)"),
                          (442.2, 568.3, "(фамилия, инициалы)")):
        sheet.text_centered(label, (x0 + x1) / 2.0, rule + 1.9, 10.0)
    return rule + 14.0


def _history(d: dict) -> List[dict]:
    rows = d.get("work_history") or []
    return [r for r in rows if any((r.get(k) or "").strip()
                                   for k in ("from", "to", "position", "address"))]


# ----------------------------------------------------------- заполнитель ---

class FormFiller:
    """
    Отрисовка бланка полосами с поддержкой значений переменной длины.

    Полоса — горизонтальный участок шаблона. Значения раскладываются по
    отведённым в бланке строкам; если строк не хватает, добавляются новые,
    и последующие полосы смещаются вниз на ту же величину.
    """

    def __init__(self, sheet: Sheet, template: dict, page_index: int = 0,
                 left_margin: float = 56.8, leading: float = LEADING,
                 doc: Optional[Document] = None, squeeze: float = 0.0):
        self.sheet = sheet
        self.tpl = template
        self.page = page_index
        self.left = left_margin
        self.leading = leading
        self.dy = 0.0
        #: нужен, чтобы бланк мог продолжиться на следующей странице
        self.doc = doc
        #: доля пустых промежутков между полосами, которую нужно поджать,
        #: чтобы титульный лист уместился на одной странице (0 — не жать)
        self.squeeze = squeeze
        #: самая нижняя отметка, до которой дошло содержимое
        self.bottom = 0.0
        #: сколько всего пустого места можно поджать
        self.slack = 0.0
        self._prev_bottom: Optional[float] = None
        self._pending: Dict[str, str] = {}

    # --- значения ---

    def put(self, key: str, text) -> None:
        """
        Регистрирует значение, которое будет разложено по строкам бланка.

        Переводы строк сохраняются: если пользователь перечислил награды
        по одной на строку, в бланке они тоже окажутся на отдельных строках.
        """
        raw = str(text or "")
        paragraphs = [" ".join(p.split()) for p in raw.split("\n")]
        self._pending[key] = [p for p in paragraphs if p]

    def has(self, key: str) -> bool:
        return bool(self._pending.get(key))

    # --- полосы ---

    def band(self, top_from: float, top_to: float,
             hide_labels: Sequence[Tuple[float, float, float]] = ()) -> None:
        """
        Выводит участок шаблона с текущим сдвигом.

        Длинные значения сдвигают бланк вниз, и рано или поздно очередная
        полоса перестаёт помещаться до нижнего поля страницы. Тогда бланк
        продолжается на следующей: полоса выводится от верхнего поля, а
        накопленный сдвиг пересчитывается так, чтобы всё, что идёт дальше,
        встало на новые места. Обрезать содержимое нельзя — документ идёт
        на печать.
        """
        top, bottom = region_bounds(self.tpl, self.page, top_from, top_to)

        # Пустой промежуток над этой полосой — то, что можно поджать, если
        # титульный лист иначе не помещается на одну страницу.
        if top is not None and self._prev_bottom is not None:
            free = max(0.0, top - self._prev_bottom - MIN_BAND_GAP)
            self.slack += free
            if self.squeeze:
                self.dy -= free * self.squeeze

        if self.doc is not None:
            lowest = region_bottom(self.tpl, self.page, top_from, top_to)
            if lowest + self.dy > PAGE_BOTTOM:
                self.sheet = self.doc.new_sheet()
                self.dy = PAGE_TOP - top_from

        draw_template_region(self.sheet, self.tpl, self.page,
                             top_from, top_to, dy=self.dy,
                             hide_labels=hide_labels)

        if bottom is not None:
            self._prev_bottom = bottom
            self.bottom = max(self.bottom, bottom + self.dy)

    def seg(self, key: str, x0: float, x1: float, line_top: float,
            last: bool = False, size: float = BODY_SIZE,
            min_size: float = 9.0) -> None:
        """
        Кладёт очередную часть значения на строку бланка.

        Кегль неизменен: если текст не помещается, он переносится. При
        `last=True` остаток дописывается на дополнительных подчёркнутых
        строках, а бланк ниже сдвигается вниз.
        """
        pending = self._pending.get(key) or []
        if not pending:
            return
        top = line_top + self.dy

        head, pending = self._take(pending, x1 - x0 - 4.0, size)
        if head:
            self.sheet.value_on_line(head, x0, x1, top, size)
        self._pending[key] = pending

        if last and pending:
            full = x1 - self.left - 4.0
            extra = 0.0
            while pending:
                extra += self.leading
                # строка не должна оказаться за нижним полем страницы
                if self.doc is not None and top + extra > PAGE_BOTTOM:
                    self.sheet = self.doc.new_sheet()
                    shift = PAGE_TOP - (top + extra)
                    top += shift
                    self.dy += shift
                head, pending = self._take(pending, full, size)
                self.sheet.value_on_line(head, self.left, x1, top + extra, size)
                self.sheet.hline(self.left, x1, top + extra, 0.5)
            self.dy += extra
            self.bottom = max(self.bottom, top + extra + size)
            self._pending[key] = []

    def short(self, text, x0: float, x1: float, line_top: float,
              size: float = BODY_SIZE, align: str = "left",
              min_size: float = 7.0) -> None:
        """Короткое значение без переноса (пол, дата, стаж)."""
        self.sheet.value_on_line(str(text or ""), x0, x1, line_top + self.dy,
                                 size, align=align, min_size=min_size)

    def centered(self, key: str, segments: Sequence[Tuple[float, float, float]],
                 size: float = BODY_SIZE) -> None:
        """Раскладывает значение по строкам с выключкой по центру."""
        pending = self._pending.get(key) or []
        for (x0, x1, top) in segments:
            if not pending:
                break
            head, pending = self._take(pending, x1 - x0 - 4.0, size)
            self.sheet.value_on_line(head, x0, x1, top + self.dy, size,
                                     align="center")
        self._pending[key] = pending

    def _take(self, pending: List[str], width: float,
              size: float) -> Tuple[str, List[str]]:
        """
        Отделяет от очереди максимум, помещающийся в строку ширины `width`.

        Абзацы не склеиваются: каждая строка исходного значения начинается
        с новой строки бланка.
        """
        if not pending:
            return "", []
        first, rest = pending[0], pending[1:]
        words = first.split()
        cur, i = "", 0
        while i < len(words):
            trial = (cur + " " + words[i]).strip()
            if self.sheet.width_of(trial, size) <= width:
                cur = trial
                i += 1
            elif not cur:
                # одно слово шире строки — переносим со знаком переноса
                pieces = self.sheet.break_word(words[i], width, size)
                cur = pieces[0]
                # в остаток слово возвращается целым: дефисы расставит
                # следующий перенос, иначе они накопились бы внутри слова
                words[i] = "".join(p[:-1] if p.endswith("-") else p
                                   for p in pieces[1:])
                break
            else:
                break
        tail = " ".join(w for w in words[i:] if w)
        return cur, ([tail] if tail else []) + rest


def fill_title_page(doc: Document, template: dict, page_index: int,
                    bands, left_margin: float = 56.8) -> FormFiller:
    """
    Заполняет титульную страницу бланка, удерживая её на одном листе.

    Пункты титульного листа нельзя разрывать между страницами: документ с
    «пунктом 10» на отдельном листе выглядит как ошибка делопроизводства.
    Но и обрезать длинные значения нельзя. Поэтому лист сначала собирается
    «вхолостую» — только чтобы измерить, насколько он не помещается, — а
    затем рисуется по-настоящему с поджатыми пустыми промежутками между
    пунктами. Сам текст при этом не меняется: кегль прежний, строки те же,
    сокращается только воздух между строками.

    Если даже полностью убранный воздух не спасает, лист продолжится на
    следующей странице: потерять данные хуже, чем разорвать бланк.

    `bands` — функция, которая выкладывает бланк по полосам; вызывается
    дважды, поэтому не должна ничего делать помимо заполнения.
    """
    probe = FormFiller(blank_sheet(), template, page_index,
                       left_margin=left_margin)
    bands(probe)

    overflow = probe.bottom - PAGE_BOTTOM
    squeeze = 0.0
    if overflow > 0 and probe.slack > 0:
        squeeze = min(1.0, overflow / probe.slack)

    # переносить на новую страницу разрешаем только тогда, когда сжатия
    # заведомо не хватит — иначе лист обязан остаться цельным
    fallback = doc if overflow > probe.slack else None

    filler = FormFiller(doc.new_sheet(), template, page_index,
                        left_margin=left_margin, doc=fallback, squeeze=squeeze)
    bands(filler)
    return filler


# -------------------------------------------------------------- таблицы ---

class TableSpec:
    """Геометрия таблицы трудовой деятельности."""

    def __init__(self, cols: Sequence[float], row_h: float,
                 keys: Sequence[str], size: float = 12.0,
                 pad_top: float = 2.0, pad_x: float = 3.0):
        self.cols = list(cols)
        self.row_h = row_h
        self.keys = list(keys)
        self.size = size
        self.pad_top = pad_top
        self.pad_x = pad_x

    @property
    def x0(self) -> float:
        return self.cols[0]

    @property
    def x1(self) -> float:
        return self.cols[-1]


def _row_cells(sheet: Sheet, spec: TableSpec,
               row: dict) -> Tuple[List[List[str]], float]:
    """Готовит содержимое строки по графам и считает её высоту."""
    cells: List[List[str]] = []
    for ci, key in enumerate(spec.keys):
        val = (row.get(key) or "").strip()
        avail = spec.cols[ci + 1] - spec.cols[ci] - 2 * spec.pad_x
        # кегль постоянный: слишком длинное слово переносится со знаком переноса
        cells.append(sheet.wrap(val, avail, spec.size) if val else [])
    need = max((len(ls) for ls in cells), default=1) or 1
    height = max(spec.row_h, need * spec.size * 1.15 + spec.pad_top + 4.0)
    return cells, height


def draw_table_rows(doc: Document, sheet: Sheet, spec: TableSpec, top: float,
                    rows: List[dict], max_bottom: float = PAGE_BOTTOM,
                    new_top: float = 60.0,
                    frame_top: Optional[float] = None
                    ) -> Tuple[Sheet, float, bool]:
    """
    Рисует строки таблицы, начиная с `top`.

    Если строки не помещаются до низа листа, таблица продолжается на
    следующей странице: незакрытая часть обрамляется, открывается новый лист,
    и заполнение идёт дальше. Раньше строки просто уходили за край листа.

    Возвращает (лист, `top` нижней границы, переносилась ли таблица).
    """
    cur = top
    seg_top = top if frame_top is None else frame_top
    moved = False

    for row in rows:
        cells, h = _row_cells(sheet, spec, row)

        if cur + h > max_bottom and cur > seg_top:
            draw_table_frame(sheet, spec, seg_top, cur)
            sheet = doc.new_sheet()
            cur = seg_top = new_top
            moved = True
            cells, h = _row_cells(sheet, spec, row)

        sheet.hline(spec.x0, spec.x1, cur + h, 0.5)
        for x in spec.cols:
            sheet.vline(x, cur, cur + h, 0.5)
        for ci, lines in enumerate(cells):
            ty = cur + spec.pad_top
            for ln in lines:
                sheet.glyph(ln, spec.cols[ci] + spec.pad_x, ty, spec.size)
                ty += spec.size * 1.15
        cur += h

    draw_table_frame(sheet, spec, seg_top, cur)
    return sheet, cur, moved


def draw_table_frame(sheet: Sheet, spec: TableSpec, top: float,
                     bottom: float) -> None:
    """Внешняя рамка таблицы."""
    sheet.hline(spec.x0, spec.x1, top, 0.75)
    sheet.hline(spec.x0, spec.x1, bottom, 0.75)
    sheet.vline(spec.x0, top, bottom, 0.75)
    sheet.vline(spec.x1, top, bottom, 0.75)


def pad_rows(rows: List[dict], minimum: int = 1) -> List[dict]:
    """
    Готовит строки таблицы: пустые записи отбрасываются.

    Лишние пустые строки в готовом документе выглядят как недоработка,
    поэтому таблица содержит ровно столько строк, сколько записей внёс
    пользователь. Совсем пустая таблица недопустима — остаётся одна строка.
    """
    rows = [r for r in rows
            if any((r.get(k) or "").strip() for k in ("from", "to", "position", "address"))]
    return rows or [{}]


# ------------------------------------------------------- кадровая справка ---

KADR_TABLE = TableSpec(cols=[57.3, 133.8, 196.1, 553.5], row_h=21.3,
                       keys=["from", "to", "position"])
KADR_STAZH = [("stazh_total", 143.3, 163.4), ("stazh_sphere", 217.3, 236.6),
              ("stazh_org", 327.9, 348.1), ("stazh_position", 504.1, 552.6)]


def render_kadrovaya(doc: Document, d: dict) -> None:
    """Кадровая справка — входит в пакет на всех уровнях наград."""
    tpl = load_template("kadrovaya")

    def bands(f: FormFiller) -> None:
        f.put("fio", _fio(d))
        f.put("work", _work_line(d))
        f.put("birth_place", d.get("birth_place"))
        f.put("education", d.get("education"))
        f.put("degree", d.get("degree"))
        f.put("home", d.get("home"))

        f.band(0.0, 54.0)                              # заголовок
        f.band(54.0, 76.0);  f.seg("fio", 206.6, 552.6, 73.3, last=True)
        f.band(76.0, 95.0);  f.seg("work", 215.3, 552.6, 93.1, last=True)
        f.band(95.0, 110.0)                            # пояснение к п.2
        f.band(110.0, 130.0); f.short(d.get("gender"), 101.9, 552.6, 127.6)
        f.band(130.0, 150.0); f.short(d.get("birth_date"), 158.6, 552.6, 147.4)
        f.band(150.0, 170.0); f.seg("birth_place", 167.0, 552.6, 167.2, last=True)
        f.band(170.0, 189.0); f.seg("education", 147.2, 552.6, 187.0, last=True)
        f.band(189.0, 204.0)                           # пояснение к п.6
        f.band(204.0, 224.0); f.seg("degree", 240.8, 552.6, 221.5, last=True)
        f.band(224.0, 244.0); f.seg("home", 167.0, 552.6, 241.3, last=True)
        f.band(244.0, 263.0)
        for key, x0, x1 in KADR_STAZH:
            f.short(d.get(key), x0, x1, 261.1, size=SMALL, align="center")
        f.band(263.0, 276.0)                           # «10. Трудовая деятельность:»

    f = fill_title_page(doc, tpl, 0, bands)
    sheet, dy = f.sheet, f.dy
    head_top, table_top = 276.5 + dy, 305.6 + dy
    draw_template_region(sheet, tpl, 0, 276.0, 305.6, dy=dy,
                         chars_only=True)   # шапка таблицы
    sheet.hline(57.3, 553.5, head_top, 0.75)
    sheet.hline(57.8, 196.5, 291.1 + dy, 0.75)
    sheet.hline(57.3, 553.5, table_top, 0.75)
    for x in (57.3, 196.1, 553.5):
        sheet.vline(x, head_top, table_top, 0.75)
    sheet.vline(133.8, 291.1 + dy, table_top, 0.5)

    rows = pad_rows(_history(d))
    sheet, bottom, moved = draw_table_rows(doc, sheet, KADR_TABLE, table_top,
                                           rows, max_bottom=PAGE_BOTTOM - 90,
                                           frame_top=head_top)

    # Блок подписи идёт сразу под таблицей с небольшим отступом, а не в самом
    # низу листа. Подписывает работник кадровой службы: так устроен бланк.
    sign_top = bottom + 26.0
    need = signature_height(sheet, _hr_signer(d), 230.0, seal=False)
    if sign_top + need > PAGE_BOTTOM:
        sheet = doc.new_sheet()
        sign_top = 60.0
    draw_signature_block(sheet, sign_top, _hr_signer(d),
                         text_width=230.0,
                         sign=(300.0, 410.0), fio=(430.0, 553.5),
                         seal=False)


# ------------------------------------------- наградной лист (Калуж. обл.) ---

# В наградном листе Калужской области графа «ухода» самая узкая: в самом
# бланке ей отведено 39.7 pt, и дата «08.2004» кеглем 12 туда не влезала.
# Раньше ради этого во всей таблице уменьшали кегль до 11 — теперь вместо
# этого граница между графами сдвинута с 136.0 до 133.0 pt: подпись «ухода»
# в шапке заканчивается левее, так что перерисовка ничего не задевает,
# а шрифт остаётся тем же, что и во всём документе.
NKO_DIVIDER = 133.0
NKO_TABLE = TableSpec(cols=[56.8, NKO_DIVIDER, 175.7, 351.5, 537.9], row_h=22.6,
                      keys=["from", "to", "position", "address"],
                      size=BODY_SIZE, pad_x=1.5)


def render_nagrlist_ko(doc: Document, d: dict) -> None:
    """Наградной лист гражданина — награды Калужской области."""
    tpl = load_template("nagrlist_ko")

    def bands(f: FormFiller) -> None:
        f.put("fio", _fio(d))
        f.put("work", _position_line(d))
        f.put("birth_place", d.get("birth_place"))
        f.put("education", d.get("education"))
        f.put("degree", d.get("degree"))
        f.put("awards", d.get("awards_received"))
        f.put("home", d.get("home"))

        f.band(0.0, 86.0)
        f.band(86.0, 107.0);  f.seg("fio", 206.7, 538.6, 103.9, last=True)
        f.band(107.0, 127.0); f.seg("work", 215.4, 538.6, 123.7, last=True)
        f.band(127.0, 144.0)
        f.band(144.0, 163.0)
        f.short(d.get("gender"), 101.9, 201.5, 160.6)
        f.short(d.get("birth_date"), 300.6, 538.6, 160.6)
        f.band(163.0, 181.0)
        f.band(181.0, 200.0); f.seg("birth_place", 164.4, 538.6, 197.4)
        f.band(200.0, 234.0); f.seg("birth_place", 56.7, 538.6, 231.8, last=True)
        f.band(234.0, 253.0)
        # линия п.6 идёт во всю ширину, значение ставим правее подписи поля
        f.band(253.0, 271.0); f.seg("education", 150.0, 538.6, 268.7)
        f.band(271.0, 308.0); f.seg("education", 56.7, 538.6, 305.5, last=True)
        f.band(308.0, 326.0)
        f.band(326.0, 345.0); f.seg("degree", 235.0, 538.6, 342.4, last=True)
        f.band(345.0, 384.0); f.seg("awards", 240.9, 538.6, 381.5)
        f.band(384.0, 405.0); f.seg("awards", 56.7, 538.6, 401.3, last=True)
        f.band(405.0, 424.0); f.seg("home", 167.0, 538.6, 421.1, last=True)
        f.band(424.0, 442.0); f.short(d.get("stazh_total"), 189.5, 538.6, 440.9)
        f.band(442.0, 482.0)                           # «11. Трудовая деятельность»

    f = fill_title_page(doc, tpl, 0, bands)
    sheet, dy = f.sheet, f.dy
    draw_template_region(sheet, tpl, 0, 482.0, 604.6, dy=dy,
                         chars_only=True)   # шапка таблицы
    top_h, top_sub, table_top = 482.9 + dy, 582.1 + dy, 604.6 + dy
    sheet.hline(56.8, 537.9, top_h, 0.75)
    sheet.hline(57.2, 537.6, top_sub, 0.75)
    sheet.hline(56.8, 537.9, table_top, 0.75)
    for x in (56.8, 175.7, 351.5, 537.9):
        sheet.vline(x, top_h, table_top, 0.75)
    sheet.vline(NKO_DIVIDER, top_sub, table_top, 0.5)

    rows = pad_rows(_history(d))
    sheet, bottom, moved = draw_table_rows(doc, sheet, NKO_TABLE, table_top,
                                           rows, max_bottom=PAGE_BOTTOM - 40,
                                           frame_top=top_h)
    if not moved:
        for x in (175.7, 351.5):
            sheet.vline(x, top_h, bottom, 0.75)

    # «Сведения в пунктах 1-11…» и заголовок характеристики
    tail_dy = bottom - 651.1
    if 744.0 + tail_dy > PAGE_BOTTOM:
        sheet = doc.new_sheet()
        tail_dy = 60.0 - 655.0
    draw_template_region(sheet, tpl, 0, 655.0, 744.0, dy=tail_dy)
    char_top = 735.6 + tail_dy + 18.0

    # текст характеристики, затем подписи и «М.П.»
    rest, cur = _flow_characteristic(doc, sheet, d, char_top, 481.0)
    sheet, cur = _finish_characteristic(doc, sheet, rest, cur, 481.0)

    # Подписи идут сразу за характеристикой с небольшим отступом. Раньше они
    # выводились по координатам бланка и потому уезжали в самый низ листа,
    # а длинная должность не помещалась в одну строку и обрывалась.
    sign_top = cur + 30.0
    if sign_top + signature_height(sheet, _signer(d), 300.0) > PAGE_BOTTOM:
        sheet = doc.new_sheet()
        sign_top = 60.0
    draw_position_signature(sheet, sign_top, _signer(d))


def _flow_characteristic(doc: Document, sheet: Sheet, d: dict,
                         top: float, width: float) -> Tuple[str, float]:
    """Выводит текст характеристики, при необходимости на нескольких страницах."""
    rest, cur = sheet.flow_text(d.get("characteristic", ""), 56.8, top,
                               max_width=width, max_top=PAGE_BOTTOM - 70,
                               size=BODY_SIZE, leading=15.5, first_indent=28.0,
                               justify=True)
    return rest, cur


def _finish_characteristic(doc: Document, sheet: Sheet, rest: str, cur: float,
                           width: float,
                           max_top: float = PAGE_BOTTOM - 70
                           ) -> Tuple[Sheet, float]:
    """
    Дописывает остаток характеристики на новых страницах.

    Продолжение начинается с абзацного отступа: без него первая строка новой
    страницы выглядела приклеенной к левому краю и читалась как обрывок.
    """
    while rest:
        sheet = doc.new_sheet()
        rest, cur = sheet.flow_text(rest, 56.8, 60.0, max_width=width,
                                    max_top=max_top, size=BODY_SIZE,
                                    leading=15.5, first_indent=28.0,
                                    justify=True)
    return sheet, cur


# ------------------------------------ наградной лист (Минпросвещения РФ) ---

def render_nagrlist_mp(doc: Document, d: dict, award_title: str) -> None:
    """Наградной лист Министерства просвещения Российской Федерации."""
    tpl = load_template("nagrlist_mp")

    def bands(f: FormFiller) -> None:
        f.put("award", award_title)
        f.put("work", _position_line(d))
        f.put("birth_place", d.get("birth_place"))
        f.put("education", d.get("education"))
        f.put("degree", d.get("degree"))
        f.put("qualification", d.get("qualification"))
        f.put("awards", d.get("awards_received"))
        # название сферы в бланк не выводится: там нужно число лет

        f.band(0.0, 190.0)
        f.centered("award", [(232.5, 567.0, 195.4), (232.5, 567.0, 215.2)])
        f.band(190.0, 290.0)
        f.band(290.0, 310.0); f.short(d.get("surname"), 121.9, 566.9, 307.4)
        f.band(310.0, 330.0)
        f.short(d.get("name"), 84.9, 277.9, 327.2)
        f.short(d.get("patronymic"), 399.8, 566.9, 327.2)
        f.band(330.0, 350.0); f.seg("work", 272.3, 566.9, 347.0)
        f.band(350.0, 370.0); f.seg("work", 56.7, 566.9, 366.8, last=True)
        f.band(370.0, 387.0)
        f.band(387.0, 406.0)
        f.short(d.get("gender"), 96.5, 187.0, 403.6)
        f.short(d.get("birth_date"), 283.6, 566.9, 403.6)
        f.band(406.0, 423.0)
        f.band(423.0, 443.0); f.seg("birth_place", 161.7, 566.9, 440.5)
        f.band(443.0, 480.0); f.seg("birth_place", 56.7, 566.9, 477.3, last=True)
        f.band(480.0, 500.0); f.seg("education", 144.4, 566.9, 497.1)
        f.band(500.0, 548.0); f.seg("education", 56.7, 566.9, 545.5, last=True)
        f.band(548.0, 568.0); f.seg("degree", 235.3, 566.9, 565.3, last=True)
        f.band(568.0, 588.0); f.seg("qualification", 402.6, 566.9, 585.1, last=True)
        f.band(588.0, 627.0); f.seg("awards", 130.3, 566.9, 624.2, last=True)
        f.band(627.0, 647.0)
        f.short(d.get("stazh_total"), 192.6, 243.7, 644.0, align="center")
        # в графе «в сфере» бланк ждёт число лет, а не название сферы
        f.short(d.get("stazh_sphere"), 294.8, 400.0, 644.0)
        f.band(647.0, 684.0); f.short(d.get("stazh_org"), 308.9, 566.9, 680.9)
        f.band(684.0, 900.0)

    f = fill_title_page(doc, tpl, 0, bands)
    # страница 2 — характеристика
    sheet = doc.new_sheet()
    draw_template_page(sheet, tpl, 1)
    rest, _ = sheet.flow_text(d.get("characteristic", ""), 56.8, 78.0,
                              max_width=510.0, max_top=PAGE_BOTTOM,
                              size=BODY_SIZE, leading=15.5, first_indent=28.0,
                              justify=True)
    sheet, _ = _finish_characteristic(doc, sheet, rest, 0.0, 510.0,
                                      max_top=PAGE_BOTTOM)

    # страница 3 — рекомендация коллегиального органа
    sheet = doc.new_sheet()
    # всё, что ниже строки с наименованием органа, выводится вручную:
    # наименование занимает столько строк, сколько нужно, и сдвигает низ листа
    draw_template_page(sheet, tpl, 2, skip_regions=[(105.0, 900.0)])
    sheet.value_on_line(fio_genitive(d), 128.8, 484.6, 84.7, align="center")

    extra = _grow_lines(sheet, _collegial(d), 56.7, 567.0, 110.8)
    draw_template_region(sheet, tpl, 2, 105.0, 160.0, dy=extra)
    sheet.value_on_line(_protocol_line(d), 56.7, 567.0, 137.9 + extra,
                        align="center")

    # Слева — руководитель, справа — председатель общего собрания трудового
    # коллектива. Обе должности пишутся полностью, поэтому блок строится
    # заново: в бланке под них отведено по две строки, а их не хватает.
    bottom = _draw_mp_signers(sheet, 164.3 + extra, _signer(d), _chair(d))
    # «М.П.» и строка с датой — из бланка, сдвинутые под подписи
    draw_template_region(sheet, tpl, 2, 240.0, 900.0, dy=bottom + 10.0 - 251.1)


# --------------------------------------- представление («Отличник просв.») ---

PRD_TABLE = TableSpec(cols=[56.3, 141.2, 226.2, 552.5], row_h=24.0,
                      keys=["from", "to", "position"])
PRD_TABLE_TOP = 128.3       # верх первой строки данных в бланке представления


def render_predstavlenie(doc: Document, d: dict) -> None:
    """Представление к ведомственному знаку отличия «Отличник просвещения»."""
    tpl = load_template("predstavlenie")

    def bands(f: FormFiller) -> None:
        f.put("work", _position_line(d))
        f.put("birth_place", d.get("birth_place"))
        f.put("education", d.get("education"))
        f.put("degree", d.get("degree"))
        f.put("awards", d.get("awards_received"))
        # название сферы в бланк не выводится: там нужно число лет

        f.band(0.0, 238.0)
        f.band(238.0, 258.0); f.short(d.get("surname"), 121.7, 552.4, 255.3)
        f.band(258.0, 297.0)
        f.short(d.get("name"), 84.9, 277.9, 294.4)
        f.short(d.get("patronymic"), 399.8, 552.4, 294.4)
        f.band(297.0, 336.0); f.seg("work", 272.3, 552.4, 333.5)
        f.band(336.0, 356.0); f.seg("work", 56.7, 552.4, 353.3, last=True)
        f.band(356.0, 392.0)
        f.band(392.0, 412.0)
        f.short(d.get("gender"), 96.5, 283.9, 409.5)
        f.short(d.get("birth_date"), 379.9, 552.4, 409.5)
        f.band(412.0, 449.0)
        f.band(449.0, 468.0); f.seg("birth_place", 161.6, 552.4, 465.6)
        f.band(468.0, 517.0); f.seg("birth_place", 56.7, 552.4, 514.0, last=True)
        f.band(517.0, 536.0); f.seg("education", 144.2, 552.4, 533.8)
        f.band(536.0, 585.0); f.seg("education", 56.7, 552.4, 582.2, last=True)
        f.band(585.0, 624.0); f.seg("degree", 235.2, 552.4, 621.3, last=True)
        f.band(624.0, 682.0); f.seg("awards", 56.7, 552.4, 679.7, last=True)
        f.band(682.0, 721.0)
        f.short(d.get("stazh_total"), 192.6, 243.6, 718.8, align="center")
        # в графе «в сфере» бланк ждёт число лет, а не название сферы
        f.short(d.get("stazh_sphere"), 294.8, 400.0, 718.8)
        f.band(721.0, 900.0); f.short(d.get("stazh_org"), 308.8, 552.4, 757.9)

    f = fill_title_page(doc, tpl, 0, bands)

    # страница 2 — трудовая деятельность, подпись кадровика, характеристика
    sheet = doc.new_sheet()
    draw_template_page(sheet, tpl, 1,
                       skip_regions=[(128.0, 900.0)],
                       skip_line_regions=[(56.0, 128.0)])
    sheet.hline(56.0, 552.8, 56.7, 0.75)
    sheet.hline(56.5, 552.2, 104.3, 0.75)
    sheet.hline(56.5, 552.2, 128.3, 0.75)
    for x in (56.3, 226.2, 552.5):
        sheet.vline(x, 56.7, 128.3, 0.75)
    sheet.vline(141.2, 104.3, 128.3, 0.5)

    rows = pad_rows(_history(d))
    sheet, bottom, moved = draw_table_rows(doc, sheet, PRD_TABLE, PRD_TABLE_TOP,
                                           rows, max_bottom=PAGE_BOTTOM - 40,
                                           frame_top=56.7)

    if moved:
        # таблица заняла отдельную страницу целиком — продолжаем с чистого листа
        sheet = doc.new_sheet()
        dy = PAGE_TOP - 156.0
    else:
        dy = bottom - 152.3

    # Под таблицей стоит подпись кадровика: в бланке написано «Руководитель
    # кадрового подразделения», и подставляется туда должность кадрового
    # работника из анкеты, а не должность руководителя организации.
    hr = _hr_signer(d) or "Руководитель кадрового подразделения"
    hr_lines = sheet.wrap(hr, 250.0, BODY_SIZE)
    hr_extra = max(len(hr_lines) - 1, 0) * (BODY_SIZE * 1.3)

    draw_template_region(sheet, tpl, 1, 156.0, 170.0, dy=dy,
                         hide_labels=[(165.8, 0.0, 300.0)])
    _draw_signer(sheet, hr, 56.8, 306.8, 165.8 + dy, BODY_SIZE)
    draw_template_region(sheet, tpl, 1, 170.0, 900.0, dy=dy + hr_extra)

    # заголовок п.12 занимает две строки — текст начинаем под ними
    char_top = 239.6 + dy + hr_extra + 34.0

    rest, _ = sheet.flow_text(d.get("characteristic", ""), 56.8, char_top,
                              max_width=496.0, max_top=PAGE_BOTTOM,
                              size=BODY_SIZE, leading=15.5, first_indent=28.0,
                              justify=True)
    sheet, _ = _finish_characteristic(doc, sheet, rest, 0.0, 496.0,
                                      max_top=PAGE_BOTTOM)

    # страница 3 — рекомендация и согласование
    sheet = doc.new_sheet()
    hide = [(t, a, b) for _pg, t, a, b in SIGNER_LABELS["predstavlenie"]]
    secretary = _secretary(d)
    if secretary:
        # Место справа занимает печатная надпись «Секретарь коллегиального
        # органа организации» с пояснениями. Если должность секретаря указана
        # в анкете, эти строки заменяются ею целиком.
        hide = hide + [(top, 300.0, 600.0) for top in
                       (161.2, 175.0, 188.6, 200.1, 211.7, 223.2, 234.8, 246.3)]

    draw_template_page(sheet, tpl, 2, skip_regions=[(103.0, 900.0)])
    sheet.value_on_line(fio_genitive(d), 129.9, 470.1, 82.0, align="center")

    extra = _grow_lines(sheet, _collegial(d), 56.7, 552.8, 107.9)
    draw_template_region(sheet, tpl, 2, 103.0, 900.0, dy=extra,
                         hide_labels=hide)
    sheet.value_on_line(_protocol_line(d), 56.7, 552.8, 134.7 + extra,
                        align="center")
    # Должность ставится ровно над своей линией для подписи (55.3 слева и
    # 313.1 справа): раньше левый блок начинался с отступа в 28 pt и
    # выглядел съехавшим относительно всего остального.
    _draw_signer(sheet, _signer(d) or "Руководитель организации (органа)",
                 56.0, 296.3, 161.2 + extra, BODY_SIZE)
    if secretary:
        _draw_signer(sheet, secretary, 313.5, 554.3, 161.2 + extra, BODY_SIZE)


# ------------------------------------------------------- характеристика ----

def render_harakteristika(doc: Document, d: dict, award_title: str) -> None:
    """Характеристика в свободной форме — отдельный лист пакета."""
    sheet = doc.new_sheet()
    sheet.text_centered("ХАРАКТЕРИСТИКА", 297.6, 60.0, 14.0)

    top = 88.0
    if _fio(d):
        sheet.text_centered(_fio(d), 297.6, top, 12.0)
        top += 18.0
    work = _position_line(d)
    if work:
        for ln in sheet.wrap(work, 460.0, 11.0):
            sheet.text_centered(ln, 297.6, top, 11.0, "R")
            top += 14.0
    # Строка о том, к какой награде представляется кандидат, здесь не нужна:
    # характеристика прикладывается к пакету, где награда уже названа.

    top += 18.0
    rest, cur = sheet.flow_text(d.get("characteristic", ""), 56.8, top,
                                max_width=481.0, max_top=PAGE_BOTTOM - 80,
                                size=BODY_SIZE, leading=15.5, first_indent=28.0,
                                justify=True)
    sheet, cur = _finish_characteristic(doc, sheet, rest, cur, 481.0,
                                        max_top=PAGE_BOTTOM - 80)

    # место для подписи — заполняется от руки
    sign = cur + 30.0
    if sign + signature_height(sheet, _signer(d), 250.0) > PAGE_BOTTOM:
        sheet = doc.new_sheet()
        sign = 60.0
    draw_signature_block(sheet, sign, _signer(d), text_width=250.0,
                         sign=(310.0, 410.0), fio=(430.0, 537.9))


# ------------------------------------------------------------- согласия ----

def render_blank_form(doc: Document, template_name: str) -> None:
    """Бланк, который остаётся пустым и заполняется от руки после печати."""
    tpl = load_template(template_name)
    for i in range(len(tpl["pages"])):
        draw_template_page(doc.new_sheet(), tpl, i)
