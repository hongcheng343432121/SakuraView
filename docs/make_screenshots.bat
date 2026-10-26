@echo off
rem 给示例库截图（README 用）：双击本文件即可
rem 结果在 docs\screenshots\01-index.png / 02-group.png / 03-video.png
setlocal
set "HERE=%~dp0"

set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    echo 没找到 Python，请先安装 Python 3.11+ 并勾选 Add to PATH
    pause & exit /b 1
)

%PY% "%HERE%make_screenshots.py"
echo.
pause
