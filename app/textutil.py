# -*- coding: utf-8 -*-
"""
Работа с русским текстом: склонение названий организаций.

В документах и итоговых сообщениях название организации иногда должно
стоять в родительном падеже («выписку из протокола общего собрания
трудового коллектива <b>муниципального бюджетного общеобразовательного
учреждения</b>»). Здесь это делается по правилам согласования.

Осторожность важнее полноты: если слово не подходит ни под одно правило,
оно остаётся без изменений. Собственные имена в кавычках не склоняются
никогда — «Средняя школа № 13» остаётся как есть.
"""
from __future__ import annotations

import re
from typing import List

_QUOTES = "«»\"'“”„"

#: Окончания, однозначно указывающие на прилагательное в именительном падеже.
#: «ие» и «ее» сюда не входят: ими заканчиваются и существительные
#: («учреждение», «управление»), а ошибиться в официальном документе хуже,
#: чем оставить слово как есть.
_ADJ_ENDINGS = ("ое", "ый", "ой", "ая", "яя", "ые")

#: Слова, которые не склоняются (аббревиатуры, номера и т. п.)
_SKIP = re.compile(r"^[^а-яё]+$", re.I)

#: После этих букв в прилагательных на «-ий» родительный падеж на «-ого»
_VELAR = set("кгхжшчщ")


def _looks_like_adjective(word: str) -> bool:
    low = word.lower()
    if len(low) < 5:
        return False
    if low.endswith(_ADJ_ENDINGS):
        return True
    # «-ий»: прилагательное, если перед окончанием согласная (калужский, синий)
    return low.endswith("ий") and len(low) > 4


def _decline_adjective(word: str) -> str:
    low = word.lower()
    if low.endswith("ий"):
        stem_last = low[-3:-2]
        return word[:-2] + ("ого" if stem_last in _VELAR else "его")
    for src, dst in (("ое", "ого"), ("ый", "ого"), ("ой", "ого"),
                     ("ая", "ой"), ("яя", "ей"), ("ые", "ых")):
        if low.endswith(src):
            return word[:-len(src)] + dst
    return word


def _decline_noun(word: str) -> str:
    """Родительный падеж существительного (единственное число)."""
    low = word.lower()

    if low.endswith("ия"):            # академия -> академии
        return word[:-2] + "ии"
    if low.endswith("ья"):            # семья -> семьи
        return word[:-2] + "ьи"
    if low.endswith("я"):             # земля -> земли
        return word[:-1] + "и"
    if low.endswith("а"):             # школа -> школы; но после г,к,х,ж,ч,ш,щ -> и
        return word[:-1] + ("и" if low[-2:-1] in "гкхжчшщ" else "ы")
    if low.endswith("ие") or low.endswith("ье"):   # учреждение -> учреждения
        return word[:-1] + "я"
    if low.endswith("е"):             # училище -> училища
        return word[:-1] + "а"
    if low.endswith("о"):             # ведомство -> ведомства
        return word[:-1] + "а"
    if low.endswith("ь"):             # деятельность -> деятельности
        return word[:-1] + "и"
    if low.endswith("й"):             # музей -> музея
        return word[:-1] + "я"
    if re.search(r"[бвгджзклмнпрстфхцчшщ]$", low):   # институт -> института
        return word + "а"
    return word


def to_genitive(phrase: str) -> str:
    """
    Ставит название организации в родительный падеж.

    Склоняется только «родовая» часть до первых кавычек: собственное имя
    в кавычках и всё, что идёт после него, остаётся неизменным.

    >>> to_genitive('Муниципальное бюджетное учреждение «Школа № 1» города Калуги')
    'Муниципального бюджетного учреждения «Школа № 1» города Калуги'
    """
    text = " ".join(str(phrase or "").split())
    if not text:
        return ""

    # всё, начиная с первых кавычек, оставляем как есть
    head, tail = text, ""
    for i, ch in enumerate(text):
        if ch in _QUOTES:
            head, tail = text[:i].rstrip(), text[i:]
            break

    words: List[str] = head.split()
    if not words:
        return text

    # Склоняем определения и одно главное слово, дальше останавливаемся:
    # хвост названия («дополнительного профессионального образования
    # Калужской области») уже стоит в родительном падеже, и трогать его
    # нельзя — иначе получится «образовании» вместо «образования».
    out: List[str] = []
    stopped = False
    for word in words:
        if stopped:
            out.append(word)
            continue
        if _SKIP.match(word) or word.isupper():        # МБОУ, № 13
            out.append(word)
            stopped = True
            continue
        if _looks_like_adjective(word):
            out.append(_decline_adjective(word))
        else:
            out.append(_decline_noun(word))
            stopped = True                             # главное слово найдено

    result = " ".join(out)
    if tail:
        result = (result + " " + tail).strip()
    return result


def lower_first(text: str) -> str:
    """Делает первую букву строчной, если слово не аббревиатура."""
    text = (text or "").strip()
    if not text:
        return ""
    first = text.split()[0]
    if first.isupper() and len(first) > 1:
        return text
    return text[0].lower() + text[1:]
