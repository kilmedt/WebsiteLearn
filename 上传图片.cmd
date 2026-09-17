@echo off
rem ---------------------------------------------------------------
rem  Upload gallery images  /  shang chuan hua lang tu pian
rem  This file is intentionally ASCII-only: cmd.exe mangles its own
rem  parse position when it re-reads a UTF-8 batch file after chcp,
rem  which corrupts lines containing Chinese. The generator prints
rem  Chinese itself, so the messages below stay readable English.
rem ---------------------------------------------------------------
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Upload gallery images

echo ==========================================
echo   Upload gallery images
echo ==========================================
echo.
echo  Put new images into either folder:
echo    images\AIworks\   - gets an "AI" badge
echo    images\HMworks\   - no badge
echo  then run this file. Nothing else to do.
echo.

rem ---- locate Python: prefer the py launcher over the Store stub ----
set "PY="
if not defined PY (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    if exist "E:\python\python.exe" set "PY=E:\python\python.exe"
)
if not defined PY (
    echo [ERROR] Python 3 not found. Install it, or edit this file and set
    echo         PY to the full path of your python.exe.
    pause
    exit /b 1
)

rem ---- locate Git ----
set "GIT="
if not defined GIT (
    where git >nul 2>&1 && set "GIT=git"
)
if not defined GIT (
    if exist "D:\Git\cmd\git.exe" set "GIT=D:\Git\cmd\git.exe"
)
if not defined GIT (
    if exist "C:\Program Files\Git\cmd\git.exe" set "GIT=C:\Program Files\Git\cmd\git.exe"
)
if not defined GIT (
    if exist "%LOCALAPPDATA%\Programs\Git\cmd\git.exe" set "GIT=%LOCALAPPDATA%\Programs\Git\cmd\git.exe"
)
if not defined GIT (
    echo [ERROR] Git not found.
    pause
    exit /b 1
)

rem ---- commit identity: fall back to the one in this repo's history ----
set "IDF="
set "GOTMAIL="
for /f "delims=" %%e in ('%GIT% config --get user.email 2^>nul') do set "GOTMAIL=%%e"
if not defined GOTMAIL (
    set "IDF=-c user.name=Kilmedt -c user.email=2789097959@qq.com"
    echo  NOTE  git has no commit identity on this machine. This run uses the
    echo        one from the repo history: Kilmedt ^<2789097959@qq.com^>
    echo        To set it permanently:  git config --global user.email "you@example.com"
    echo.
)

echo Python : %PY%
echo Git    : %GIT%
echo.
echo ---- 1/3  Build the gallery ----
%PY% "tools\build_gallery.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Nothing was committed.
    pause
    exit /b 1
)

echo.
echo ---- 2/3  Commit ----
set "NEWLIST="
for /f "delims=" %%f in ('%GIT% ls-files --others --exclude-standard -- images 2^>nul') do (
    set "NEWLIST=!NEWLIST!%%~nxf, "
)

%GIT% add -A
%GIT% diff --cached --quiet
if errorlevel 1 (
    set "MSG2="
    if defined NEWLIST (
        set "NEWLIST=!NEWLIST:~0,-2!"
        set "MSG2=New image^(s^): !NEWLIST!"
    )
    if defined MSG2 (
        %GIT% %IDF% commit -m "Update gallery images" -m "!MSG2!"
    ) else (
        %GIT% %IDF% commit -m "Update gallery images"
    )
    if errorlevel 1 (
        echo.
        echo [ERROR] Commit failed. Nothing was pushed.
        pause
        exit /b 1
    )
) else (
    echo  Nothing to commit.
)

echo.
echo ---- 3/3  Push ----
set "ANS="
set /p "ANS=Push to GitHub so the site updates? (Y/N) "
echo.
if /i "%ANS%"=="Y" (
    %GIT% push origin main
    if errorlevel 1 (
        echo.
        echo [ERROR] Push failed. If it was the network, just run this file
        echo         again later - the local commit is already saved.
        pause
        exit /b 1
    )
    echo.
    echo  Done. The site updates a moment after the push.
) else (
    echo  Cancelled. Changes are committed locally; run this file again
    echo  or push manually when ready.
)

echo.
pause
