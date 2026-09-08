# -*- coding: utf-8 -*-
"""
Портал для подачи документов на награды в Калужской области.

Настольное приложение: пользователь выбирает награду, заполняет анкету, и
программа формирует готовый пакет документов одним PDF-файлом.

Запуск из исходников:   python main.py
Сборка .exe:            см. СБОРКА.md
"""
from __future__ import annotations

import os
import sys
from typing import Optional


def resource_dir() -> str:
    """
    Каталог с ресурсами приложения.

    При запуске собранного .exe файлы распаковываются во временную папку,
    путь к которой PyInstaller кладёт в ``sys._MEIPASS``.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    return os.path.dirname(os.path.abspath(__file__))


#: Журнал запуска. Нужен потому, что у собранной программы нет консоли:
#: если что-то пойдёт не так, показать причину больше негде. Файл
#: перезаписывается при каждом запуске и содержит только технические
#: сведения — ничего из того, что пользователь вводит в анкету.
LOG_NAME = "ПорталНаград-запуск.log"
_log_path: Optional[str] = None


def log_path() -> Optional[str]:
    """
    Куда писать журнал запуска.

    Кладём рядом с программой — там пользователю проще всего его найти.
    Если папка защищена от записи (например, программу запустили с
    диска только для чтения), уходим во временную папку.
    """
    global _log_path
    if _log_path is not None:
        return _log_path or None

    if getattr(sys, "frozen", False):
        folders = [os.path.dirname(os.path.abspath(sys.executable))]
    else:
        folders = [os.path.dirname(os.path.abspath(__file__))]
    try:
        import tempfile
        folders.append(tempfile.gettempdir())
    except Exception:                                  # noqa: BLE001
        pass

    for folder in folders:
        candidate = os.path.join(folder, LOG_NAME)
        try:
            with open(candidate, "w", encoding="utf-8") as fh:
                fh.write("")
            _log_path = candidate
            return candidate
        except Exception:                              # noqa: BLE001
            continue

    _log_path = ""                                     # писать некуда
    return None


def log(message: str) -> None:
    """
    Записывает, что происходит при запуске.

    В собранном .exe консольного окна нет, и Python подставляет вместо
    потоков вывода пустое значение (None). Обращение к нему выбрасывало
    свою собственную ошибку и подменяло собой настоящую причину сбоя —
    поэтому вывод здесь защищён и при отсутствии консоли просто молчит,
    а всё сказанное дополнительно уходит в файл журнала.
    """
    try:
        from datetime import datetime
        stamp = f"{datetime.now():%H:%M:%S}"
    except Exception:                                  # noqa: BLE001
        stamp = ""

    path = log_path()
    if path:
        try:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(f"{stamp}  {message}\n")
        except Exception:                              # noqa: BLE001
            pass

    for stream in (sys.stderr, sys.stdout):
        if stream is None:
            continue
        try:
            stream.write(message + "\n")
            stream.flush()
        except Exception:                              # noqa: BLE001
            continue
        return


def report(message: str) -> None:
    """
    Показывает сообщение об ошибке.

    В собранном .exe окна консоли нет, поэтому текст дополнительно выводится
    системным окном — иначе пользователь не увидит причину сбоя.
    """
    log(message)
    path = log_path()
    if path:
        message += f"\n\nПодробности записаны в файл:\n{path}"
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, message, "Портал наград — ошибка запуска", 0x10)
    except Exception:                                  # noqa: BLE001
        pass


def selftest() -> int:
    """
    Самопроверка сборки: шрифты, шаблоны бланков, формирование PDF.

    Запуск:  ПорталНаград.exe --selftest
    Нужна, чтобы на чужом компьютере сразу увидеть, всё ли на месте,
    не заполняя анкету целиком.
    """
    root = resource_dir()
    if root not in sys.path:
        sys.path.insert(0, root)

    lines, ok = [], True

    try:
        from app import compat
        note = " (включена совместимость со старым Python)" if compat.PATCHED else ""
        lines.append(f"Python .......... {compat.PYTHON_VERSION}{note}")
    except Exception as exc:                           # noqa: BLE001
        lines.append(f"Python .......... не удалось определить: {exc}")

    try:
        from app.pdfkit import ensure_fonts
        ensure_fonts()
        lines.append("Шрифты .......... в порядке")
    except Exception as exc:                           # noqa: BLE001
        ok = False
        lines.append(f"Шрифты .......... ОШИБКА: {exc}")

    try:
        from app.pdfkit import load_template
        names = ["kadrovaya", "nagrlist_ko", "nagrlist_mp",
                 "predstavlenie", "soglasie_ko", "soglasie_mp"]
        missing = []
        for name in names:
            try:
                load_template(name)
            except Exception:                          # noqa: BLE001
                missing.append(name)
        if missing:
            ok = False
            lines.append("Бланки .......... НЕ НАЙДЕНЫ: " + ", ".join(missing))
        else:
            lines.append(f"Бланки .......... в порядке ({len(names)} шт.)")
    except Exception as exc:                           # noqa: BLE001
        ok = False
        lines.append(f"Бланки .......... ОШИБКА: {exc}")

    try:
        import tempfile
        from app.awards import all_levels
        from app.builder import build_package
        count = sum(len(lvl["awards"]) for lvl in all_levels())
        lines.append(f"Справочник ...... в порядке ({count} наград)")

        sample = {
            "award_id": "nagrko1", "surname": "Проверкина", "name": "Тест",
            "patronymic": "Тестовна", "gender": "женский",
            "birth_date": "01.01.1980", "birth_place": "город Калуга",
            "org_full": "Тестовая организация", "position": "специалист",
            "education": "высшее", "home": "г. Калуга",
            "stazh_total": "20", "stazh_sphere": "20", "stazh_org": "10",
            "stazh_position": "10", "sphere_name": "образование",
            "work_history": [{"from": "01.2005", "to": "По настоящее время",
                              "position": "специалист", "address": "г. Калуга"}],
            "characteristic": "Проверка формирования документа.",
        }
        out = os.path.join(tempfile.gettempdir(), "proverka_portala.pdf")
        build_package(sample, out)
        size = os.path.getsize(out) // 1024
        lines.append(f"Создание PDF .... в порядке ({size} КБ)")
        lines.append("")
        lines.append(f"Пробный файл: {out}")
    except Exception as exc:                           # noqa: BLE001
        ok = False
        lines.append(f"Создание PDF .... ОШИБКА: {exc}")

    head = "Проверка пройдена успешно." if ok else "Обнаружены проблемы!"
    text = head + "\n\n" + "\n".join(lines)
    print(text)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, text, "Портал наград — самопроверка", 0x40 if ok else 0x10)
    except Exception:                                  # noqa: BLE001
        pass
    return 0 if ok else 1


def webview2_installer() -> Optional[str]:
    """
    Путь к вложенному установщику Microsoft Edge WebView2, если он есть.

    Файл кладут в папку `assets/webview2`. Он не обязателен: без него
    приложение просто откроется в браузере.
    """
    folder = os.path.join(resource_dir(), "assets", "webview2")
    if not os.path.isdir(folder):
        return None
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".exe"):
            return os.path.join(folder, name)
    return None


def offer_webview2_install() -> bool:
    """
    Предлагает установить WebView2 из вложенного установщика.

    Возвращает True, если установка выполнена и окно стоит попробовать снова.
    """
    installer = webview2_installer()
    if not installer or not sys.platform.startswith("win"):
        return False

    try:
        import ctypes
        answer = ctypes.windll.user32.MessageBoxW(
            None,
            "Для обычного окна программы нужен компонент\n"
            "Microsoft Edge WebView2 — на этом компьютере его нет.\n\n"
            "Установить его сейчас? Это займёт около минуты.\n\n"
            "Если отказаться, программа откроется в браузере —\n"
            "работать можно и так.",
            "Портал наград — установка компонента",
            0x24)                                      # ДА/НЕТ + вопрос
        if answer != 6:                                # 6 = «Да»
            return False
    except Exception:                                  # noqa: BLE001
        return False

    try:
        import subprocess
        subprocess.run([installer, "/silent", "/install"], timeout=600, check=False)
        return True
    except Exception:                                  # noqa: BLE001
        return False


#: Держим замок открытым всё время работы: как только он закроется,
#: система освободит имя и следующая копия сочтёт себя первой.
_instance_lock = None


def already_running() -> bool:
    """
    Проверяет, не запущена ли уже копия программы.

    Две копии сразу — частая причина странного поведения: движок окна
    (Microsoft Edge WebView2) хранит служебные файлы в одной папке на все
    запуски, и второй копии приходится ждать, пока первая их отпустит.
    Внешне это выглядит как зависший при запуске пустой экран.
    """
    global _instance_lock
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "MinobrPortalNagrad")
        if not handle:
            return False
        _instance_lock = handle
        return kernel32.GetLastError() == 183          # ERROR_ALREADY_EXISTS
    except Exception:                                  # noqa: BLE001
        return False


def ask_open_second_copy() -> bool:
    """Спрашивает, открывать ли вторую копию. Без ответа — открываем."""
    try:
        import ctypes
        answer = ctypes.windll.user32.MessageBoxW(
            None,
            "Программа уже запущена — где-то открыто её окно.\n\n"
            "Если то окно не отвечает, закройте его: правая кнопка мыши\n"
            "по значку программы на панели задач → «Закрыть окно».\n"
            "Если не помогает — Диспетчер задач (Ctrl+Shift+Esc),\n"
            "найдите «Портал наград» и снимите задачу.\n\n"
            "Открыть ещё одно окно всё равно?",
            "Портал наград — программа уже запущена",
            0x24)                                      # ДА/НЕТ + вопрос
        return answer == 6                             # 6 = «Да»
    except Exception:                                  # noqa: BLE001
        return True


def browser_only_build() -> bool:
    """Сборка предназначена для Windows 7: окно не создаём, сразу браузер."""
    return os.path.exists(os.path.join(resource_dir(), "assets",
                                       "browser_only.marker"))


#: Браузеры, пригодные для работы приложения, в порядке предпочтения.
#: Internet Explorer в списке отсутствует намеренно: он не поддерживает
#: возможностей, на которых построен интерфейс.
_BROWSERS = [
    (r"Google\Chrome\Application\chrome.exe", "Google Chrome"),
    (r"Yandex\YandexBrowser\Application\browser.exe", "Яндекс.Браузер"),
    (r"Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
    (r"Mozilla Firefox\firefox.exe", "Mozilla Firefox"),
    (r"Opera\opera.exe", "Opera"),
]


def find_browser():
    """
    Ищет установленный подходящий браузер.

    Нужно потому, что браузером по умолчанию на старых системах нередко
    остаётся Internet Explorer, в котором интерфейс не работает.
    Возвращает (путь, название) или (None, None).
    """
    if not sys.platform.startswith("win"):
        return None, None

    roots = [os.environ.get(v) for v in
             ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    for rel, title in _BROWSERS:
        for root in roots:
            if not root:
                continue
            path = os.path.join(root, rel)
            if os.path.exists(path):
                return path, title
    return None, None


def start_server(api):
    """
    Поднимает локальный сервер интерфейса и возвращает (сервер, адрес).

    Сервер работает в обоих режимах — и в собственном окне программы, и
    во вкладке браузера. Раньше окно общалось с Python напрямую через
    мост pywebview, и это оказалось причиной зависаний: мост обслуживает
    вызовы тем же потоком, который рисует окно, и два одновременных
    обращения могли заблокировать его насмерть. Сервер такого недостатка
    лишён: каждый запрос обрабатывается отдельным потоком.

    Слушает только 127.0.0.1 — этот компьютер и никто больше; наружу
    ничего не открывается, интернет не нужен.
    """
    from app.server import AppServer

    server = AppServer(api)
    url = server.start_background()
    log(f"Локальный сервер интерфейса поднят: {url}")
    return server, url


def run_in_browser(api, server, url: str, reason: str = "") -> int:
    """
    Интерфейс открывается в браузере.

    Основной режим для Windows 7 и запасной для остальных систем, если
    на компьютере нет Microsoft Edge WebView2. Возможности приложения
    те же, интернет не требуется.
    """
    import webbrowser

    api.window = None                                  # без окна — без диалогов
    path, title = find_browser()
    note = ("Программа открыта во вкладке браузера.\n\n"
            "На работу это не влияет: всё считается на вашем компьютере,\n"
            "интернет не нужен, готовый документ попадёт в папку «Загрузки».\n\n"
            "Не закрывайте это окно, пока работаете с программой.")
    if title:
        note = note.replace("во вкладке браузера.",
                            f"во вкладке браузера {title}.")
    else:
        note += ("\n\nВНИМАНИЕ: подходящий браузер не найден.\n"
                 "Если открылся Internet Explorer и страница пустая —\n"
                 "установите Google Chrome или Яндекс.Браузер,\n"
                 "затем откройте в нём адрес, указанный ниже.")
    if reason:
        note += f"\n\nТехническая причина: {reason}"
    log(note)
    log(f"Адрес: {url}")

    opened = False
    if path:
        try:
            webbrowser.register("portal", None,
                                webbrowser.BackgroundBrowser(path))
            webbrowser.get("portal").open(url)
            opened = True
        except Exception:                              # noqa: BLE001
            opened = False
    if not opened:
        webbrowser.open(url)

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, note + f"\n\nАдрес: {url}",
            "Портал наград — работа в браузере", 0x40)
    except Exception:                                  # noqa: BLE001
        # не Windows или окно недоступно — держим сервер до Ctrl+C
        try:
            input("\nНажмите Enter, чтобы завершить работу программы...")
        except (Exception, KeyboardInterrupt):         # noqa: BLE001
            pass

    log("Пользователь завершил работу в браузерном режиме.")
    return 0                                           # сервер остановит main()


#: Заголовок окна программы
TITLE = "Портал для подачи документов на награды в Калужской области"


def open_window(webview, api, url: str) -> None:
    """
    Создаёт окно программы и ведёт его до закрытия пользователем.

    Окно показывает ту же страницу, что и браузерный режим, — по адресу
    локального сервера. Мост pywebview (`js_api`) сознательно не
    подключается: именно он раньше приводил к зависанию окна.
    """
    window = webview.create_window(
        title=TITLE,
        url=url,
        width=1280,
        height=860,
        min_size=(900, 640),
        text_select=True,
    )
    api.window = window
    webview.start(debug=bool(os.environ.get("MINOBR_DEBUG")))


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    root = resource_dir()
    if root not in sys.path:
        sys.path.insert(0, root)

    log("=" * 60)
    log(f"Запуск программы. Python {sys.version.split()[0]}, "
        f"{'собранный .exe' if getattr(sys, 'frozen', False) else 'из исходников'}")

    from app import diag
    diag.set_sink(log)                                 # ошибки внутри — в журнал

    if already_running():
        log("Обнаружена уже запущенная копия программы")
        if not ask_open_second_copy():
            log("Пользователь отказался открывать вторую копию.")
            return 0

    from app.api import Api

    index = os.path.join(root, "web", "index.html")
    if not os.path.exists(index):
        report(f"Не найден интерфейс приложения:\n{index}")
        return 1

    api = Api()
    try:
        server, url = start_server(api)
    except Exception as exc:                           # noqa: BLE001
        import traceback
        log(traceback.format_exc())
        report("Не удалось запустить программу: не открывается внутреннее\n"
               "соединение на этом компьютере (адрес 127.0.0.1).\n\n"
               "Обычно это значит, что обращение блокирует антивирус или\n"
               "сетевой экран. Разрешите программе работать и запустите\n"
               f"её ещё раз.\n\nТехническая причина: {exc}")
        return 1

    try:
        # Сборка для Windows 7 или явное указание — сразу в браузер
        if "--browser" in sys.argv or browser_only_build():
            log("Режим: вкладка браузера (так задано сборкой или ключом --browser)")
            return run_in_browser(api, server, url)

        try:
            import webview
        except ImportError:
            log("Библиотека pywebview недоступна — уходим в браузер")
            return run_in_browser(api, server, url,
                                  "не установлена библиотека pywebview")

        # pywebview сам выбирает движок; в Windows это Microsoft Edge WebView2.
        # Если открыть окно не удалось, приложение не падает, а показывает
        # интерфейс в браузере — работать можно в любом случае.
        log("Режим: собственное окно программы (Microsoft Edge WebView2)")
        try:
            open_window(webview, api, url)
            log("Окно закрыто пользователем. Завершаем работу.")
            return 0
        except Exception as exc:                       # noqa: BLE001
            import traceback
            log(traceback.format_exc())
            first_error = str(exc)

        # Окно не открылось. Если в комплекте есть установщик WebView2 —
        # предлагаем поставить компонент и пробуем ещё раз.
        if offer_webview2_install():
            log("WebView2 установлен, пробуем открыть окно ещё раз")
            try:
                open_window(webview, api, url)
                return 0
            except Exception:                          # noqa: BLE001
                import traceback
                log(traceback.format_exc())

        log("Окно открыть не удалось — переходим в браузер")
        return run_in_browser(api, server, url, first_error)
    finally:
        try:
            server.shutdown()
        except Exception:                              # noqa: BLE001
            pass


if __name__ == "__main__":
    # Верхний перехватчик: в собранном .exe консоли нет, и без него
    # любая ошибка запуска выглядела бы как безымянное системное окно.
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:                                  # noqa: BLE001
        import traceback
        details = traceback.format_exc()
        log(details)
        report(
            "Приложение не смогло запуститься.\n\n"
            "Покажите этот текст разработчику:\n\n"
            + details.strip()[-1200:]
        )
        sys.exit(1)
