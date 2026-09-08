# -*- coding: utf-8 -*-
"""
Сборка готового комплекта для Windows 7.

PyInstaller делает только сам .exe. Отдать пользователю один этот файл
нельзя: на "чистой" Windows 7 нет системного компонента Universal C
Runtime, и система не даёт программе даже стартовать - а значит, и
проверить что-либо изнутри программа не может.

Поэтому рядом кладётся файл запуска: он проверяет компонент, при
необходимости ставит вложенное обновление Microsoft (KB2999226) и только
потом открывает программу. Этот скрипт собирает такую папку целиком.

Почему на Python, а не в .bat: здесь встречаются русские имена файлов и
папок, а командная строка Windows с ними обращается ненадёжно.

Запуск (обычно вызывается из "Собрать exe для Windows 7.bat"):
    py -3.8 tools\\pack_win7.py
"""
from __future__ import annotations

import os
import shutil
import sys

#: имя папки, которую отдают пользователю
BUNDLE = "Портал наград для Windows 7"

#: файл, отсутствие которого на Windows 7 и ломает запуск
CRT_DLL = "api-ms-win-crt-runtime-l1-1-0.dll"


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dist = os.path.join(root, "dist")
    bundle = os.path.join(dist, BUNDLE)
    name = "ПорталНаград-Win7.exe"

    # Свежесобранный .exe лежит прямо в dist. Если скрипт запускают
    # повторно, без пересборки, берём его из уже готового комплекта.
    exe = os.path.join(dist, name)
    if not os.path.exists(exe):
        exe = os.path.join(bundle, name)
    if not os.path.exists(exe):
        print("Не найден собранный файл:", os.path.join(dist, name))
        print("Сначала должна пройти сборка PyInstaller.")
        return 1

    # 1. Сама программа. Копируем во временное место: папку комплекта
    #    сейчас пересоздадим, а исходный .exe может лежать внутри неё.
    keep = os.path.join(dist, "~" + name)
    shutil.copy2(exe, keep)

    shutil.rmtree(bundle, ignore_errors=True)
    os.makedirs(bundle)
    shutil.move(keep, os.path.join(bundle, name))

    # В самой папке dist копию не оставляем: пользователю нужен весь
    # комплект, а одинокий .exe на чистой Windows 7 не запустится.
    loose = os.path.join(dist, name)
    if os.path.exists(loose):
        os.remove(loose)

    # 2. Файл запуска и памятка для пользователя
    helpers = os.path.join(root, "assets", "win7")
    for name in sorted(os.listdir(helpers)):
        shutil.copy2(os.path.join(helpers, name), os.path.join(bundle, name))

    # 3. Обновление Windows, если его положили в assets/ucrt
    ucrt_dir = os.path.join(root, "assets", "ucrt")
    updates = []
    if os.path.isdir(ucrt_dir):
        updates = [n for n in sorted(os.listdir(ucrt_dir))
                   if n.lower().endswith(".msu")]
    for name in updates:
        shutil.copy2(os.path.join(ucrt_dir, name), os.path.join(bundle, name))

    print()
    print("=" * 64)
    print("  Комплект для Windows 7 собран")
    print("=" * 64)
    print()
    print("  Папка:", bundle)
    print()
    for name in sorted(os.listdir(bundle)):
        size = os.path.getsize(os.path.join(bundle, name)) // 1024
        print(f"    {name}  ({size} КБ)")
    print()

    if updates:
        print("  Обновление Windows вложено: " + ", ".join(updates))
        print("  На компьютере пользователя оно поставится само, если")
        print("  файла " + CRT_DLL + " там ещё нет.")
    else:
        print("  ВНИМАНИЕ: обновления Windows в комплекте нет.")
        print()
        print("  Положите файл Windows6.1-KB2999226-x64.msu в папку")
        print("  assets\\ucrt и соберите ещё раз. Иначе на чистой")
        print("  Windows 7 программа не запустится, а пользователю")
        print("  придётся искать обновление самому.")
        print()
        print("  Подробности: assets\\ucrt\\ПОЛОЖИТЕ_СЮДА_ОБНОВЛЕНИЕ.txt")
    print()
    print("  Пользователю отдают папку целиком, а не отдельный .exe.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
