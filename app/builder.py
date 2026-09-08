# -*- coding: utf-8 -*-
"""Сборка итогового PDF: все бланки пакета в одном файле, каждый с новой страницы."""
from __future__ import annotations

import os
from typing import List

from . import awards as reg
from . import forms
from .pdfkit import Document


class MissingTemplate(Exception):
    """Шаблон бланка отсутствует в комплекте приложения."""


def build_package(data: dict, out_path: str) -> str:
    """
    Формирует пакет документов для выбранной награды.

    `data` — значения анкеты; `out_path` — куда сохранить PDF.
    Возвращает путь к созданному файлу.
    """
    award = reg.get_award(data["award_id"])
    documents: List[str] = award["documents"]
    title = award["titlePlain"]

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    doc = Document(out_path)

    for code in documents:
        if code == reg.DOC_KADROVAYA:
            forms.render_kadrovaya(doc, data)
        elif code == reg.DOC_NAGRLIST_KO:
            forms.render_nagrlist_ko(doc, data)
        elif code == reg.DOC_NAGRLIST_MP:
            forms.render_nagrlist_mp(doc, data, title)
        elif code == reg.DOC_PREDSTAVLENIE:
            forms.render_predstavlenie(doc, data)
        elif code == reg.DOC_HARAKTERISTIKA:
            forms.render_harakteristika(doc, data, title)
        elif code in reg.BLANK_DOCS:
            try:
                forms.render_blank_form(doc, code)
            except FileNotFoundError as exc:
                raise MissingTemplate(
                    f"Не найден шаблон бланка «{reg.DOC_TITLES.get(code, code)}». "
                    f"Обратитесь к разработчику приложения. ({exc})"
                ) from exc
        else:
            raise ValueError(f"Неизвестный код бланка: {code}")

    doc.save()
    return out_path


def package_contents(award_id: str) -> List[str]:
    """Человекочитаемый перечень бланков, входящих в пакет."""
    award = reg.get_award(award_id)
    return [reg.DOC_TITLES.get(c, c) for c in award["documents"]]
