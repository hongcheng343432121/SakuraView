@echo off
rem SakuraView 一键处理 —— 把游戏文件夹拖到本文件上即可
rem 注意：本文件必须以 GBK 保存，否则 cmd 会把中文当成乱码并解析失败
setlocal
set "HERE=%~dp0"

if "%~1"=="" goto help

set "PY="
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY goto nopython

echo.
%PY% "%HERE%oneclick.py" %*
set "CODE=%ERRORLEVEL%"
echo.
if not "%CODE%"=="0" echo 处理结束，但有错误（退出码 %CODE%），看上面日志。
pause
exit /b %CODE%

:help
echo ==========================================================
echo   SakuraView 一键处理
echo ----------------------------------------------------------
echo   把「游戏文件夹」拖到本文件上，或用命令行：
echo       一键处理.bat "D://game//某游戏"
echo.
echo   可选参数（放最后）：
echo       --name "标题"     指定显示标题
echo       --key  mygame     指定 key（小写字母+数字，不能和已有库重名）
echo       --out  D://某目录  指定输出目录（默认 游戏目录\CG）
echo       --no-extract      跳过解包（已有 extracted 时用）
echo       --no-media        不转视频/不做缩略图，只出页面（快）
echo       --no-hub          不登记总收藏页
echo       --no-open         结束后不自动开浏览器
echo       --dry             只打印识别结果，不动文件
echo.
echo   支持引擎：QLIE（万华镜 0-5）、Ren'Py、Godot
echo   Unity 需要先用 AssetStudioModCLI 把纹理导出来
echo ==========================================================
pause
exit /b 1

:nopython
echo.
echo 没找到 Python。请先安装 Python 3.11 或更高版本，
echo 安装时勾选 "Add python.exe to PATH"，然后重开本窗口。
echo 下载地址: https://www.python.org/downloads/
pause
exit /b 1
