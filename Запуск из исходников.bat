@echo off
rem Запуск приложения из исходных файлов (без сборки exe).
rem Файл сохранён в кодировке CP866 - так его читает командная строка Windows.

title Портал наград - запуск
cd /d "%~dp0"
set "PYCMD="

rem --- ищем Python: сначала лаунчер py, затем python ---
py -3 --version >nul 2>&1
if not errorlevel 1 set "PYCMD=py -3"

if defined PYCMD goto found
python --version >nul 2>&1
if not errorlevel 1 set "PYCMD=python"

:found
if not defined PYCMD goto nopython

echo.
echo ================================================================
echo    Портал для подачи документов на награды
echo ================================================================
echo.
echo [1/2] Проверяем библиотеки. При первом запуске это займёт минуту.
echo.
%PYCMD% -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto piperror

echo.
echo [2/2] Запускаем приложение...
echo.
%PYCMD% main.py
if errorlevel 1 goto apperror

exit /b 0

:nopython
echo.
echo    ОШИБКА: на компьютере не найден Python.
echo.
echo    Скачайте его здесь:  https://www.python.org/downloads/windows/
echo    При установке обязательно отметьте галочку
echo    "Add python.exe to PATH", иначе запуск не сработает.
echo.
pause
exit /b 1

:piperror
echo.
echo    ОШИБКА: не удалось установить библиотеки.
echo    Обычно это значит, что нет доступа в интернет.
echo.
pause
exit /b 1

:apperror
echo.
echo    Приложение завершилось с ошибкой.
echo    Текст ошибки показан выше - пришлите его разработчику.
echo.
pause
exit /b 1
