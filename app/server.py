# -*- coding: utf-8 -*-
"""
Запасной режим работы: приложение открывается в браузере по умолчанию.

Нужен, если на компьютере нет компонента Microsoft Edge WebView2, который
рисует обычное окно программы. Тогда запускается локальный веб-сервер
(только на этом компьютере, наружу ничего не открывается), и интерфейс
показывается в браузере — выглядит и работает точно так же.

Доступ защищён одноразовым ключом: он выдаётся странице при открытии и
требуется во всех запросах, поэтому посторонние программы на том же
компьютере обратиться к данным не могут. Интернет для работы не нужен.
"""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import quote, unquote, urlparse

from . import diag
from .paths import resource

#: методы, которые разрешено вызывать со страницы
ALLOWED = {"get_levels", "get_award", "get_schema", "generate",
           "open_file", "open_folder", "toggle_developer"}


class _Handler(BaseHTTPRequestHandler):
    server_version = "MinobrPortal"

    # --- служебное ---

    def log_message(self, fmt, *args):        # noqa: A003
        pass                                   # молчим: консоли всё равно нет

    def _send(self, code: int, body: bytes, ctype: str,
              extra: Optional[dict] = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _authorized(self) -> bool:
        return self.headers.get("X-Portal-Key") == self.server.key

    # --- обработка запросов ---

    def do_GET(self) -> None:                  # noqa: N802
        path = unquote(urlparse(self.path).path)

        if path in ("/", "/index.html"):
            return self._serve_index()

        if path.startswith("/download/"):
            return self._serve_download(path.rsplit("/", 1)[-1])

        return self._serve_static(path)

    def do_POST(self) -> None:                 # noqa: N802
        path = unquote(urlparse(self.path).path)
        if not path.startswith("/api/"):
            return self._json(404, {"ok": False, "error": "Неизвестный запрос."})
        if not self._authorized():
            return self._json(403, {"ok": False, "error": "Доступ запрещён."})

        method = path[len("/api/"):]
        if method not in ALLOWED:
            return self._json(404, {"ok": False, "error": "Неизвестный метод."})

        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"[]"
            args = json.loads(raw.decode("utf-8") or "[]")
            result = getattr(self.server.api, method)(*args)
            return self._json(200, result)
        except Exception as exc:               # noqa: BLE001
            return self._json(200, {"ok": False,
                                    "error": f"Ошибка обработки: {exc}"})

    # --- отдача файлов ---

    def _serve_index(self) -> None:
        path = os.path.join(self.server.web_root, "index.html")
        with open(path, encoding="utf-8") as fh:
            html = fh.read()
        # Странице передаётся ключ доступа и то, в каком окружении она
        # открыта. Через сервер работают оба режима, но в собственном окне
        # программы доступны системные диалоги — сохранение файла, открытие
        # папки, — а во вкладке браузера их нет.
        native = "true" if not self.server.api.browser_mode else "false"
        inject = (f'<script>window.PORTAL_KEY="{self.server.key}";'
                  f'window.PORTAL_NATIVE={native};</script>')
        html = html.replace("</head>", inject + "</head>", 1)
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_static(self, path: str) -> None:
        rel = path.lstrip("/").replace("\\", "/")
        full = os.path.normpath(os.path.join(self.server.web_root, rel))
        # не выпускаем за пределы папки с интерфейсом
        if not full.startswith(os.path.normpath(self.server.web_root)):
            return self._send(403, b"", "text/plain")
        if not os.path.isfile(full):
            return self._send(404, b"", "text/plain")
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype.endswith("javascript"):
            ctype += "; charset=utf-8"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), ctype)

    def _serve_download(self, token: str) -> None:
        item = self.server.api.take_download(token)
        if not item:
            return self._send(404, "Файл не найден или уже скачан.".encode("utf-8"),
                              "text/plain; charset=utf-8")
        path, filename = item
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            return self._send(404, b"", "text/plain")
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        # В заголовках HTTP допустима только латиница, поэтому русское имя
        # передаётся по RFC 5987, а рядом даётся упрощённый запасной вариант.
        ascii_name = "".join(ch if ch.isascii() and ch not in '"\\' else "_"
                             for ch in filename) or "documents.pdf"
        self._send(200, data, "application/pdf", {
            "Content-Disposition": f'attachment; filename="{ascii_name}"; '
                                   f"filename*=UTF-8''{quote(filename)}",
        })


class AppServer(ThreadingHTTPServer):
    """Локальный сервер интерфейса — слушает только этот компьютер."""

    daemon_threads = True

    #: Сколько запросов система придержит, пока сервер занят. По умолчанию
    #: их всего пять, и при всплеске обращений лишние соединения обрываются
    #: с ошибкой. Страница обычно спрашивает по одному, но запас не мешает.
    request_queue_size = 64

    def __init__(self, api, host: str = "127.0.0.1", port: int = 0):
        super().__init__((host, port), _Handler)
        self.api = api
        self.web_root = resource("web")
        self.key = secrets.token_urlsafe(24)

    def server_bind(self) -> None:
        """
        Занимает порт, не спрашивая у системы сетевое имя компьютера.

        Штатная реализация из ``http.server`` вызывает ``socket.getfqdn()``.
        На русской Windows имя компьютера нередко записано кириллицей в
        кодировке CP1251, а Python ждёт UTF-8 — и запуск падал с ошибкой
        «'utf-8' codec can't decode byte 0xe1». Имя нам не нужно вовсе:
        сервер слушает только этот компьютер по адресу 127.0.0.1, поэтому
        подставляем адрес напрямую и обходим опасный вызов.
        """
        socketserver.TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        self.server_name = str(host)
        self.server_port = port

    def handle_error(self, request, client_address) -> None:
        """
        Сообщает о сбое при обработке запроса.

        Штатная реализация печатает ошибку в ``sys.stderr``, которого в
        собранной программе нет, и падала сама. Пишем в журнал запуска.
        """
        diag.report_exception("Сбой при обработке запроса интерфейса:")

    @property
    def url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}/"

    def start_background(self) -> str:
        """Запускает сервер в отдельном потоке и возвращает адрес страницы."""
        thread = threading.Thread(target=self.serve_forever, daemon=True)
        thread.start()
        return self.url
