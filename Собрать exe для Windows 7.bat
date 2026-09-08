@echo off
rem Сборка версии для Windows 7 (нужен отдельно установленный Python 3.8).
rem Файл сохранён в кодировке CP866 - так его читает командная строка Windows.
rem
rem Результат: папка dist\Портал наград для Windows 7
rem Обычная версия собирается файлом "Собрать exe.bat" - это разные сборки.

title Портал наград - сборка для Windows 7
cd /d "%~dp0"

rem Здесь нужен именно Python 3.8: более новые версии на Windows 7 не работают
py -3.8 --version >nul 2>&1
if errorlevel 1 goto nopython

echo.
echo ================================================================
echo    Сборка версии для Windows 7
echo ================================================================
echo.
py -3.8 --version
echo.
echo [1/3] Устанавливаем библиотеки...
py -3.8 -m pip install -r requirements-win7.txt --disable-pip-version-check
if errorlevel 1 goto err

echo.
echo [2/3] Устанавливаем PyInstaller...
py -3.8 -m pip install pyinstaller --disable-pip-version-check
if errorlevel 1 goto err

echo.
echo [3/4] Собираем приложение. Это занимает 1-3 минуты...
py -3.8 -m PyInstaller minobr-win7.spec --noconfirm --clean
if errorlevel 1 goto err

echo.
echo [4/4] Собираем комплект для флешки...
py -3.8 "tools\pack_win7.py"
if errorlevel 1 goto err

echo.
echo ================================================================
echo    Готово.
echo ================================================================
echo.
echo    Это версия ТОЛЬКО для Windows 7. Она всегда открывается
echo    в браузере и не требует компонента WebView2.
echo.
echo    Пользователю отдают ПАПКУ целиком, а не один .exe:
echo    в ней лежит файл запуска, который сам поставит
echo    обновление Windows, если его на компьютере не окажется.
echo.
echo    Проверить сборку: "Проверить сборку.bat"
echo.
pause
exit /b 0

:nopython
echo.
echo    ОШИБКА: не найден Python 3.8.
echo.
echo    Для версии под Windows 7 нужен именно Python 3.8 -
echo    это последняя версия, работающая на этой системе.
echo    Более новые версии для неё не годятся.
echo.
echo    Скачать: https://www.python.org/downloads/release/python-3810/
echo    Внизу страницы выберите "Windows installer (64-bit)".
echo    При установке отметьте галочку "Add Python 3.8 to PATH".
echo.
echo    Обычную версию для Windows 10/11 это никак не затрагивает:
echo    она собирается файлом "Собрать exe.bat".
echo.
pause
exit /b 1

:err
echo.
echo    Сборка не удалась. Текст ошибки показан выше.
echo.
echo    Частая причина: библиотека не поддерживает Python 3.8.
echo    В файле requirements-win7.txt версии намеренно не закреплены,
echo    чтобы pip подобрал подходящие сам.
echo.
pause
exit /b 1
