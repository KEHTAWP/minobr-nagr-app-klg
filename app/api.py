# -*- coding: utf-8 -*-
"""
Программный интерфейс, доступный из окна приложения.

Персональные данные нигде не сохраняются: они живут только в памяти во время
заполнения анкеты и стираются сразу после формирования PDF-файла.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime
from typing import Dict, Optional, Tuple

from . import awards as reg
from . import diag
from . import periods
from .builder import MissingTemplate, build_package
from .schema import build_schema


def _translit(text: str) -> str:
    """Латинская транслитерация для имени файла."""
    table = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    out = []
    for ch in text.lower():
        if ch in table:
            out.append(table[ch])
        elif ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("_")
    return "".join(out).strip("_") or "dokumenty"


#: Служебный режим снимает ограничение по срокам подачи — он нужен, чтобы
#: проверять формирование документов в любое время года. Пароль хранится
#: не сам по себе, а его отпечаток: так его не видно в готовом файле
#: программы, даже если открыть её текстовым редактором.
_SERVICE_HASH = "3ddc8c531265f1a79f0e5da6e11166dd1fcd64f8f0a2774cb786a1cd7c8590bc"


def _check_password(value: str) -> bool:
    """Сверяет пароль служебного режима, не сравнивая его посимвольно."""
    import hashlib
    import secrets as _secrets
    digest = hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
    return _secrets.compare_digest(digest, _SERVICE_HASH)


class Api:
    """Методы, вызываемые из интерфейса приложения."""

    def __init__(self):
        self.window = None
        #: файлы, ожидающие скачивания в браузерном режиме: ключ -> (путь, имя)
        self._downloads: Dict[str, Tuple[str, str]] = {}
        #: служебный режим: живёт только в памяти и гаснет при закрытии
        #: программы — включать его заново приходится осознанно
        self.developer = False

    @property
    def browser_mode(self) -> bool:
        """True, если интерфейс открыт в браузере, а не в окне приложения."""
        return self.window is None

    def take_download(self, token: str) -> Optional[Tuple[str, str]]:
        """Отдаёт готовый файл по одноразовому ключу и забывает о нём."""
        return self._downloads.pop(token, None)

    # --- сроки подачи ---

    def _status(self, award_id: str) -> dict:
        """
        Сведения о сроке подачи с учётом служебного режима.

        В служебном режиме награда считается открытой всегда, но настоящий
        срок из справочника остаётся виден — иначе при проверке не понять,
        что увидит обычный пользователь.
        """
        status = dict(periods.status_for(award_id))
        status["really_open"] = status["open"]
        if self.developer:
            status["open"] = True
        return status

    def _refuse_if_closed(self, award_id: str) -> Optional[dict]:
        """Отказ, если приём документов на эту награду сейчас закрыт."""
        status = self._status(award_id)
        if status["open"]:
            return None
        return {"ok": False, "closed": True,
                "error": status["message"] or
                         "Приём документов на эту награду сейчас закрыт."}

    def toggle_developer(self, password: str) -> dict:
        """
        Включает или выключает служебный режим по паролю.

        Вызывается со скрытого сочетания на главном экране. Неверный пароль
        ничего не меняет и не сообщает, чем именно он не подошёл.
        """
        if not _check_password(password):
            return {"ok": False, "error": "Пароль не подошёл."}
        self.developer = not self.developer
        return {"ok": True, "developer": self.developer}

    # --- справочные данные ---

    def get_levels(self) -> dict:
        """Уровни наград и входящие в них награды — для главного экрана."""
        try:
            levels = []
            for level in reg.all_levels():
                awards = []
                for award in level["awards"]:
                    item = dict(award)
                    item["status"] = self._status(award["id"])
                    awards.append(item)
                levels.append(dict(level, awards=awards))
            return {"ok": True, "levels": levels, "developer": self.developer}
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)

    def get_award(self, award_id: str) -> dict:
        """Карточка награды: описание, требования, нормативный акт."""
        try:
            award = reg.get_award(award_id)
            return {"ok": True, "award": award,
                    "status": self._status(award_id),
                    "documents": [reg.DOC_TITLES[c] for c in award["documents"]]}
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)

    def get_schema(self, award_id: str) -> dict:
        """Состав анкеты для выбранной награды."""
        try:
            refusal = self._refuse_if_closed(award_id)
            if refusal:
                return refusal
            return {"ok": True, "schema": build_schema(award_id)}
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)

    # --- формирование пакета документов ---

    def generate(self, data: dict) -> dict:
        """
        Формирует PDF и предлагает сохранить его.

        Возвращает путь к файлу и текст завершающего сообщения.
        """
        tmp_path: Optional[str] = None
        try:
            refusal = self._refuse_if_closed(data["award_id"])
            if refusal:
                return refusal
            award = reg.get_award(data["award_id"])
            fio = " ".join(filter(None, [data.get("surname"), data.get("name"),
                                         data.get("patronymic")]))
            suggested = f"Награждение_{_translit(fio) or 'kandidat'}_" \
                        f"{datetime.now():%Y-%m-%d}.pdf"

            from .forms import org_genitive
            message = reg.completion_message(
                award["level"], data["award_id"], org_genitive(data))
            documents = [reg.DOC_TITLES[c] for c in award["documents"]]

            if self.browser_mode:
                # в браузере системного диалога нет — отдаём файл на скачивание
                fd, ready = tempfile.mkstemp(suffix=".pdf")
                os.close(fd)
                build_package(data, ready)
                token = secrets.token_urlsafe(18)
                self._downloads[token] = (ready, suggested)
                return {"ok": True, "download": "/download/" + token,
                        "filename": suggested, "message": message,
                        "documents": documents}

            target = self._ask_save_path(suggested)
            if not target:
                return {"ok": False, "cancelled": True}

            # сначала во временный файл — чтобы при ошибке не портить целевой
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            build_package(data, tmp_path)

            with open(tmp_path, "rb") as src, open(target, "wb") as dst:
                dst.write(src.read())

            return {"ok": True, "path": target, "message": message,
                    "documents": documents}
        except MissingTemplate as exc:
            return {"ok": False, "error": str(exc)}
        except PermissionError:
            return {"ok": False, "error":
                    "Не удалось записать файл: он открыт в другой программе "
                    "или папка защищена от записи. Закройте файл или выберите "
                    "другое расположение."}
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    # --- работа с файлами ---

    def open_file(self, path: str) -> dict:
        """Открывает готовый PDF в программе просмотра по умолчанию."""
        try:
            if not os.path.exists(path):
                return {"ok": False, "error": "Файл не найден."}
            if sys.platform.startswith("win"):
                os.startfile(path)                     # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return {"ok": True}
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)

    def open_folder(self, path: str) -> dict:
        """Показывает папку с готовым файлом."""
        try:
            folder = os.path.dirname(os.path.abspath(path))
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.abspath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", folder])
            return {"ok": True}
        except Exception as exc:                       # noqa: BLE001
            return self._fail(exc)

    # --- внутреннее ---

    def _ask_save_path(self, suggested: str) -> Optional[str]:
        """Диалог сохранения файла средствами операционной системы."""
        import webview
        result = self.window.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=os.path.join(os.path.expanduser("~"), "Documents")
            if os.path.isdir(os.path.join(os.path.expanduser("~"), "Documents"))
            else os.path.expanduser("~"),
            save_filename=suggested,
            file_types=("Документ PDF (*.pdf)",),
        )
        if not result:
            return None
        path = result if isinstance(result, str) else result[0]
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return path

    @staticmethod
    def _fail(exc: Exception) -> dict:
        # раньше здесь был traceback.print_exc(): в собранной программе
        # консоли нет, и он сам падал, пряча настоящую ошибку
        diag.report_exception("Ошибка при обработке запроса от интерфейса:")
        return {"ok": False,
                "error": f"Не удалось выполнить операцию: {exc}"}
