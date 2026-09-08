# -*- coding: utf-8 -*-
"""
Состав анкеты для конкретной награды.

Набор вопросов зависит от того, какие бланки входят в пакет документов:
лишние поля не показываются, чтобы не запрашивать у пользователя сведения,
которые нигде не понадобятся.
"""
from __future__ import annotations

from typing import Dict, List

from . import awards as reg
from . import requirements as req


#: Напоминание для полей с адресами — выводится мелким шрифтом под полем
ADDRESS_NOTE = ("Адрес указывается полностью, без сокращений: индекс, "
                "область, район, населённый пункт, улица, дом, квартира.")

#: Пример полного наименования организации — он же образец для полей,
#: где организацию нужно назвать целиком
ORG_EXAMPLE = ("Муниципальное бюджетное общеобразовательное учреждение "
               "«Средняя общеобразовательная школа № 13» города Калуги")

#: Пример в родительном падеже. Он всегда подставляется ПОСЛЕ должности —
#: то есть в середине фразы, — поэтому начинается со строчной буквы: иначе
#: сотрудники повторяют образец дословно и пишут «Директор Муниципального».
ORG_GENITIVE_EXAMPLE = (
    "муниципального бюджетного общеобразовательного учреждения "
    "«Средняя общеобразовательная школа № 13» города Калуги")

#: Пример в творительном падеже — для наименования коллегиального органа:
#: в бланке оно продолжает фразу «Кандидатура … рекомендована …».
ORG_INSTRUMENTAL_EXAMPLE = (
    "муниципального бюджетного общеобразовательного учреждения "
    "«Средняя общеобразовательная школа № 13» города Калуги")

ORG_NOTE = ("Наименование должно совпадать с уставом и записью в трудовой "
            "книжке. Проверить его можно в выписке из ЕГРЮЛ на сайте "
            "налоговой службы — там указано полное официальное название.")

#: Как заполняется графа «Должность»
POSITION_NOTE = ("Указывается только сама должность из трудовой книжки — "
                 "«учитель», «воспитатель», «преподаватель». Предмет "
                 "(«учитель математики», «учитель русского языка») дописывать "
                 "не нужно: такой должности в штатном расписании нет.")

#: Пометка для полей с перечнем имеющихся наград
AWARDS_NOTE = ("Указывается только название награды и год её получения. "
               "Номера удостоверений, приказов и прочие реквизиты не нужны.")

#: Отдельное предупреждение для «Отличника просвещения»
OTLICHNIK_NOTE = (
    "Если у работника уже есть ведомственная «Почётная грамота» федерального "
    "уровня, полученная до 28.06.2016, представлять его к «Отличнику "
    "просвещения» нельзя. Нельзя и в том случае, если с момента получения "
    "предыдущей ведомственной награды федерального уровня не прошло трёх лет.")

#: Порядок, в котором стаж не может возрастать: каждый следующий вид стажа
#: является частью предыдущего
STAZH_CHAIN = [
    ("stazh_total", "общий стаж"),
    ("stazh_sphere", "стаж в сфере"),
    ("stazh_org", "стаж в организации"),
    ("stazh_position", "стаж в должности в организации"),
]

STAZH_POSITION_NOTE = (
    "Это работа именно в этой должности и именно в этой организации. Годы "
    "работы учителем в других школах сюда не входят — они относятся к стажу "
    "в сфере. Если работник уходил и вернулся на ту же должность в ту же "
    "организацию, периоды складываются.")


def _f(key: str, label: str, required: bool = False, kind: str = "text",
       hint: str = "", placeholder: str = "", options=None,
       note: str = "", numeric: bool = False, age: bool = False) -> dict:
    field = {"key": key, "label": label, "required": required, "kind": kind}
    if age:
        # рядом с календариком показывается число полных лет: так сразу
        # видно, если в дате рождения промахнулись мимо нужного года
        field["age"] = True
    if hint:
        field["hint"] = hint
    if placeholder:
        field["placeholder"] = placeholder
    if options:
        field["options"] = options
    if note:
        field["note"] = note
    if numeric:
        field["numeric"] = True
    return field


def build_schema(award_id: str) -> dict:
    """Возвращает описание анкеты: шаги, поля, правила обязательности."""
    award = reg.get_award(award_id)
    docs = set(award["documents"])

    has_nagrlist_ko = reg.DOC_NAGRLIST_KO in docs
    has_nagrlist_mp = reg.DOC_NAGRLIST_MP in docs
    has_predstavlenie = reg.DOC_PREDSTAVLENIE in docs
    has_kadrovaya = reg.DOC_KADROVAYA in docs
    is_mp_style = has_nagrlist_mp or has_predstavlenie
    any_nagrlist = has_nagrlist_ko or is_mp_style

    steps: List[dict] = []

    # --- шаг 1: личные данные ---
    steps.append({
        "title": "Личные данные",
        "hint": "Сведения указываются строго по паспорту и трудовой книжке.",
        "fields": [
            _f("surname", "Фамилия", True, placeholder="Иванова"),
            _f("name", "Имя", True, placeholder="Мария"),
            _f("patronymic", "Отчество", False,
               hint="Оставьте пустым, если отчества нет",
               placeholder="Петровна"),
            _f("gender", "Пол", True, kind="select",
               options=["женский", "мужской"]),
            _f("birth_date", "Дата рождения", True, kind="date",
               placeholder="15.03.1975", age=True),
            _f("birth_place", "Место рождения", True,
               hint="Республика, край, область, округ, город, район, "
                    "посёлок, село, деревня",
               placeholder="город Калуга, Калужская область",
               note=ADDRESS_NOTE),
        ],
    })
    if is_mp_style:
        steps[-1]["fields"].append(
            _f("fio_genitive", "Фамилия, имя и отчество в родительном падеже",
               False,
               hint="Так, как в бланке: «Кандидатура Иванова Романа Юрьевича "
                    "рекомендована…». Если оставить пустым, будет "
                    "подставлен именительный падеж",
               placeholder="Ивановой Марии Петровны"))
    if has_kadrovaya or has_nagrlist_ko:
        steps[-1]["fields"].append(
            _f("home", "Домашний адрес", True,
               placeholder="248000, Калужская область, г. Калуга, "
                           "ул. Кирова, д. 5, кв. 10",
               note=ADDRESS_NOTE))

    # --- шаг 2: работа и образование ---
    work_fields = [
        _f("org_full", "Полное наименование организации", True,
           hint="Как в уставе и трудовой книжке, без сокращений",
           placeholder=ORG_EXAMPLE, note=ORG_NOTE),
        _f("org_genitive", "То же наименование в родительном падеже", False,
           hint="Отвечает на вопрос «кого? чего?». Если оставить пустым, "
                "программа просклоняет название сама",
           placeholder=ORG_GENITIVE_EXAMPLE,
           note="Заполните это поле, если сомневаетесь в автоматическом "
                "склонении: русский язык слишком богат, чтобы программа "
                "справлялась с ним безошибочно."),
        _f("position", "Занимаемая должность", True,
           hint="Только должность из трудовой книжки, без указания предмета",
           placeholder="учитель", note=POSITION_NOTE),
        _f("education", "Образование", True,
           hint="Уровень образования, полное наименование учебного "
                "заведения, год окончания",
           placeholder="высшее, Калужский государственный университет "
                       "имени К.Э. Циолковского, 1997 год"),
        _f("degree", "Учёная степень, учёное звание", False,
           hint="Оставьте пустым, если их нет",
           placeholder="кандидат педагогических наук"),
    ]
    if is_mp_style:
        work_fields.append(
            _f("qualification", "Квалификационная категория", False,
               hint="Для педагогических работников",
               placeholder="высшая"))
    work_fields.append(
        _f("signer_position", "Должность руководителя, подписывающего "
                              "документы", True,
           hint="Должность и полное наименование организации — так, как это "
                "будет напечатано в бланке вместо формулировки "
                "«Руководитель организации»",
           placeholder="Директор " + ORG_GENITIVE_EXAMPLE,
           note="Одного слова «директор» недостаточно: в документах "
                "указывается, чего именно он директор."))
    if has_kadrovaya or has_predstavlenie:
        work_fields.append(
            _f("hr_position", "Должность работника кадровой службы", False,
               hint="Кадровую справку и представление подписывает кадровый "
                    "работник, а не руководитель. Если такой должности в "
                    "организации нет, оставьте поле пустым — подпишет "
                    "руководитель",
               placeholder="Специалист по кадрам " + ORG_GENITIVE_EXAMPLE))
    steps.append({
        "title": "Работа и образование",
        "hint": "Эти сведения попадут в кадровую справку и наградные бланки.",
        "fields": work_fields,
    })

    # --- шаг 3: стаж ---
    stazh_fields = [_f("stazh_total", "Общий стаж работы, лет", True,
                       placeholder="28", numeric=True)]
    if has_kadrovaya:
        stazh_fields += [
            _f("stazh_sphere", "Стаж в сфере, лет", True, placeholder="28",
               numeric=True),
            _f("stazh_org", "Стаж в организации, лет", True, placeholder="16",
               numeric=True),
            _f("stazh_position", "Стаж в должности в организации, лет", True,
               placeholder="16", numeric=True, note=STAZH_POSITION_NOTE),
        ]
    steps.append({
        "title": "Стаж работы",
        "hint": "Укажите полное число лет. Каждый следующий вид стажа входит "
                "в предыдущий, поэтому он не может быть больше него.",
        "fields": stazh_fields,
    })

    # --- шаг 4: имеющиеся награды ---
    if any_nagrlist:
        note = AWARDS_NOTE
        if award_id == reg.OTLICHNIK:
            note += "\n\n" + OTLICHNIK_NOTE
        steps.append({
            "title": "Имеющиеся награды",
            "hint": "Государственные, ведомственные и региональные награды "
                    "с годом награждения.",
            "fields": [
                _f("awards_received", "Какими наградами награждён(а) и когда",
                   False, kind="textarea",
                   hint="Каждую награду — с новой строки. Если наград нет, "
                        "оставьте поле пустым",
                   placeholder="Почётная грамота Министерства просвещения "
                               "Российской Федерации, 2018 год",
                   note=note),
            ],
        })

    # --- шаг 5: трудовая деятельность ---
    history_cols = [
        {"key": "from", "label": "Поступление (мм.гггг)", "width": "narrow",
         "placeholder": "09.1997"},
        {"key": "to", "label": "Уход (мм.гггг)", "width": "narrow",
         "placeholder": "08.2004",
         "note": "Для текущего места работы напишите «По настоящее время» "
                 "полностью, без сокращений. Графа в бланке узкая, поэтому "
                 "запись перенесётся на несколько строк — это нормально."},
        {"key": "position", "label": "Должность с указанием организации",
         "width": "wide",
         "placeholder": "Учитель " + ORG_GENITIVE_EXAMPLE},
    ]
    if has_nagrlist_ko:
        history_cols.append({"key": "address", "label": "Адрес организации",
                             "width": "wide", "note": ADDRESS_NOTE})
    steps.append({
        "title": "Трудовая деятельность",
        "hint": "Записи в хронологическом порядке, включая обучение и "
                "военную службу. В последней строке в графе «Уход» обычно "
                "указывают «По настоящее время».",
        "table": {"key": "work_history", "columns": history_cols},
        "fields": [],
    })

    # --- шаг 6: характеристика ---
    steps.append({
        "title": "Характеристика",
        "hint": "Опишите конкретные заслуги кандидата. Текст войдёт в пакет "
                "документов и при необходимости продолжится на следующих "
                "страницах.",
        "fields": [
            _f("characteristic", "Характеристика с указанием конкретных заслуг",
               True, kind="textarea",
               hint="Абзацы разделяйте переводом строки"),
        ],
    })

    # --- шаг 7: рекомендация коллегиального органа ---
    if is_mp_style:
        steps.append({
            "title": "Рекомендация",
            "hint": "Сведения о коллегиальном органе, рекомендовавшем "
                    "кандидатуру.",
            "fields": [
                _f("collegial_body", "Кем рекомендована кандидатура",
                   False,
                   hint="В творительном падеже и со строчной буквы: в бланке "
                        "это продолжение фразы «Кандидатура … рекомендована …»",
                   placeholder="общим собранием трудового коллектива "
                               + ORG_INSTRUMENTAL_EXAMPLE,
                   note="Отвечает на вопрос «кем?». Предложение уже начато "
                        "словом «Кандидатура», поэтому заглавная буква здесь "
                        "не нужна."),
                _f("discussion_date", "Дата обсуждения", False, kind="date",
                   placeholder="10.02.2026"),
                _f("protocol_no", "№ протокола", False, placeholder="3"),
            ],
        })
        if has_nagrlist_mp:
            steps[-1]["fields"].append(
                _f("chair_position", "Председатель общего собрания "
                                     "трудового коллектива", False,
                   hint="Должность с полным наименованием организации в "
                        "родительном падеже — она печатается в бланке "
                        "вместо надписи «Председатель коллегиального "
                        "органа организации»",
                   placeholder="Председатель общего собрания трудового "
                               "коллектива " + ORG_GENITIVE_EXAMPLE))
        if has_predstavlenie:
            steps[-1]["fields"].append(
                _f("secretary_position", "Секретарь общего собрания "
                                         "трудового коллектива", False,
                   hint="Должность с полным наименованием организации в "
                        "родительном падеже — она печатается в бланке "
                        "вместо надписи «Секретарь коллегиального "
                        "органа организации»",
                   placeholder="Секретарь общего собрания трудового "
                               "коллектива " + ORG_GENITIVE_EXAMPLE))

    # --- пункт 1: минимальный стаж, установленный требованиями к награде ---
    rules = req.rules_for(award_id)
    if rules:
        for step in steps:
            for field in step["fields"]:
                rule = rules.get(field["key"])
                if not rule:
                    continue
                field["min"] = rule["min"]
                field["minMessage"] = (
                    f"По условиям награждения {rule['label']} должен "
                    f"составлять не менее {rule['min']} лет."
                )
                field["minQuote"] = rule["quote"]

    # --- пункт 17: повышенное требование при отсутствии ведомственных наград ---
    sphere_note = req.sphere_note(award_id)
    if sphere_note:
        for step in steps:
            for field in step["fields"]:
                if field["key"] == "stazh_sphere":
                    field["note"] = sphere_note

    # --- пункт 7: стаж не может расти от общего к частному ---
    present = {f["key"] for step in steps for f in step["fields"]}
    chain = [{"key": key, "label": label}
             for key, label in STAZH_CHAIN if key in present]

    return {
        "award_id": award_id,
        "stazh_chain": chain,
        "stazh_rules": rules,
        "award_title": award["titlePlain"],
        "award_title_html": award["title"],
        "level": award["level"],
        "level_title": award["levelTitle"],
        "documents": [reg.DOC_TITLES[c] for c in award["documents"]],
        "steps": steps,
    }
