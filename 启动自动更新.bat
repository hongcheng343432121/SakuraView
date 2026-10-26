@echo off
chcp 65001 >nul
title SakuraView 自动更新（关掉这个窗口就停止）
cd /d "%~dp0"

rem 用 PATH 里的 python；找不到就提示，不猜路径
set "PY=python"
where python >nul 2>nul || (
  echo 没找到 python，请先安装 Python 3.11+ 并勾选 "Add python.exe to PATH"
  pause
  exit /b 1
)

echo ============================================
echo  自动更新：往 CG 目录里加/删图片视频后，
echo  会自动重建对应图库（默认每 90 秒检查一次）
echo  关闭本窗口 = 停止监视
echo ============================================
echo.

"%PY%" watch_update.py --interval 90

echo.
echo 已退出，按任意键关闭
pause >nul
