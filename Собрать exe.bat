@echo off
rem Сборка приложения в один файл ПорталНаград.exe
rem Файл сохранён в кодировке CP866 - так его читает командная строка Windows.

title Портал наград - сборка для Windows 10 и 11
cd /d "%~dp0"
set "PYCMD="

py -3 --version >nul 2>&1
if not errorlevel 1 set "PYCMD=py -3"

if defined PYCMD goto found
python --version >nul 2>&1
if not errorlevel 1 set "PYCMD=python"

:found
if not defined PYCMD goto nopython

echo.
echo ================================================================
echo    Сборка ОБЫЧНОЙ версии - для Windows 10 и 11
echo ================================================================
echo.
echo [1/3] Устанавливаем библиотеки...
%PYCMD% -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto err

echo.
echo [2/3] Устанавливаем PyInstaller...
%PYCMD% -m pip install pyinstaller --disable-pip-version-check
if errorlevel 1 goto err

echo.
echo [3/3] Собираем приложение. Это занимает 1-3 минуты...
%PYCMD% -m PyInstaller minobr.spec --noconfirm --clean
if errorlevel 1 goto err

echo.
echo ================================================================
echo    Готово. Файл: %CD%\dist\ПорталНаград.exe
echo.
echo    Это версия для Windows 10 и 11.
echo    Для Windows 7 нужна отдельная сборка:
echo       "Собрать exe для Windows 7.bat"
echo.
echo    Проверьте сборку командой:
echo       dist\ПорталНаград.exe --selftest
echo ================================================================
echo.
pause
exit /b 0

:nopython
echo.
echo    ОШИБКА: на компьютере не найден Python.
echo    Скачайте его здесь:  https://www.python.org/downloads/windows/
echo    При установке отметьте галочку "Add python.exe to PATH".
echo.
pause
exit /b 1

:err
echo.
echo    Сборка не удалась. Текст ошибки показан выше.
echo.
pause
exit /b 1
