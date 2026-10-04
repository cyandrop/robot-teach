@echo off
chcp 65001 >nul
setlocal
set "PROJ=C:\Users\wyd27\WorkBuddy\2026-09-30-23-22-28\robot_teach"
if not exist "%PROJ%\main.py" set "PROJ=%~dp0"
cd /d "%PROJ%"
if not exist "main.py" (
    echo [x] 没找到 main.py。请把本脚本放到 robot_teach 项目根目录里运行。
    pause
    exit /b 1
)

set "PY="
for %%P in (
    "C:\Users\wyd27\miniforge3\envs\robot\python.exe"
    "%USERPROFILE%\miniforge3\envs\robot\python.exe"
    "%USERPROFILE%\miniconda3\envs\robot\python.exe"
    "%USERPROFILE%\anaconda3\envs\robot\python.exe"
) do if not defined PY if exist %%P set "PY=%%~P"
if not defined PY (
    echo [x] 没找到 conda 环境 robot 里的 python.exe。
    echo     先双击 setup_env_无需预装conda.bat 把环境装好。
    pause
    exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ==========================================================
echo   机器人教学仿真平台 一键启动（录演示视频用）
echo   项目目录: %PROJ%
echo   python  : %PY%
echo ==========================================================
echo.
echo   [1] 图形界面 + 相机窗口  -  推荐录视频：自己敲中文指令，日志区显示解析结果
echo   [2] 自动演示三条指令 + 相机窗口  -  省事，但画面上看不到输入指令的过程
echo   [3] 快速自检 smoke.py  -  只有文字、不弹窗口，约 1 分钟
echo   [4] 带窗口自检  -  弹出 PyBullet 窗口跑一次抓取，约 20 秒（想看画面先试这个）
echo.

set "MODE=%~1"
if not defined MODE set /p MODE=输入 1 或 2 或 3 然后回车: 

if "%MODE%"=="1" goto MODE1
if "%MODE%"=="2" goto MODE2
if "%MODE%"=="3" goto MODE3
if "%MODE%"=="4" goto MODE4

echo.
echo 没选对，重新双击运行吧。
goto END

:MODE1
echo.
echo 提示：先摆好窗口再开录 -- PyBullet 窗口放左边，相机窗口放右边。
echo       输入框里敲「把红色方块放到紫色区域」回车，等动作走完再敲下一条。
"%PY%" main.py --cam --realtime
goto END

:MODE2
echo.
echo 提示：动作是 1:1 真实速度，三条指令大约 1 分半，中途别关窗口。
"%PY%" main.py --cam --demo --realtime
goto END

:MODE3
"%PY%" smoke.py
goto END

:MODE4
echo.
echo 正在打开 PyBullet 窗口并跑一次抓取，约 20 秒...
"%PY%" tools\check_gui.py
goto END

:END
echo.
pause
