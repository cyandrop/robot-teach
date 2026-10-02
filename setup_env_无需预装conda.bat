@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ==========================================================
echo   机器人仿真环境 一键安装（电脑上没装 conda 也能跑）
echo   环境内容: conda 环境 robot = Python 3.11 + pybullet + opencv + numpy
echo   适用项目: PyBullet 机械臂教学仿真（robot_teach）
echo ==========================================================
echo.

set "MIRROR=https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge/"
set "CONDA_EXE="

rem ---------- [1/4] 先找 conda ----------
where conda >nul 2>nul && set "CONDA_EXE=conda"
if not defined CONDA_EXE for %%P in (
    "%USERPROFILE%\miniforge3\Scripts\conda.exe"
    "%USERPROFILE%\miniconda3\Scripts\conda.exe"
    "%USERPROFILE%\anaconda3\Scripts\conda.exe"
    "%LOCALAPPDATA%\miniforge3\Scripts\conda.exe"
    "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe"
    "C:\ProgramData\miniforge3\Scripts\conda.exe"
    "C:\ProgramData\miniconda3\Scripts\conda.exe"
    "C:\ProgramData\anaconda3\Scripts\conda.exe"
) do if not defined CONDA_EXE if exist %%P set "CONDA_EXE=%%~P"

rem ---------- [2/4] 没有 conda 就自动装 Miniforge（原版脚本就是在这里挂掉的） ----------
if not defined CONDA_EXE (
    echo [1/4] 没检测到 conda，自动下载并安装 Miniforge3（约 150MB，清华镜像）...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try{Invoke-WebRequest -Uri 'https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease/Miniforge3-Windows-x86_64.exe' -OutFile '%TEMP%\Miniforge3-Windows-x86_64.exe' -UseBasicParsing}catch{exit 1}"
    if not exist "%TEMP%\Miniforge3-Windows-x86_64.exe" (
        echo.
        echo [x] Miniforge 下载失败。请手动装一个 Miniconda 再重跑本脚本：
        echo     https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/
        echo.
        pause & exit /b 1
    )
    echo       正在静默安装到 %USERPROFILE%\miniforge3 ...
    start /wait "" "%TEMP%\Miniforge3-Windows-x86_64.exe" /InstallationType=JustMe /RegisterPython=0 /AddToPath=0 /S /D=%USERPROFILE%\miniforge3
    if exist "%USERPROFILE%\miniforge3\Scripts\conda.exe" set "CONDA_EXE=%USERPROFILE%\miniforge3\Scripts\conda.exe"
)
if not defined CONDA_EXE (
    echo [x] 仍然找不到 conda，请手动安装 Miniconda 后重跑本脚本。
    pause & exit /b 1
)
echo [1/4] 使用 conda: %CONDA_EXE%
echo.

rem ---------- [3/4] 建环境 ----------
echo [2/4] 创建/更新环境 robot，并安装 pybullet / opencv / numpy
echo        （首次约 500MB，走清华镜像，视网速 3~10 分钟）
echo.
"%CONDA_EXE%" create -y -n robot --override-channels -c %MIRROR% python=3.11 pybullet opencv numpy pip
if errorlevel 1 (
    echo.
    echo [x] 环境创建失败。常见原因：
    echo     1. 网络中断 —— 直接重跑本脚本，已下载的包不会重复下
    echo     2. 磁盘不足 —— 需要约 3GB 空闲空间
    echo.
    pause & exit /b 1
)

rem 推导环境里的 python.exe（不走 conda run，避免中文输出变乱码）
set "CONDA_DIR="
set "ROBOT_PY="
for %%I in ("%CONDA_EXE%") do set "CONDA_DIR=%%~dpI"
if exist "%CONDA_DIR%..\envs\robot\python.exe" for %%I in ("%CONDA_DIR%..") do set "ROBOT_PY=%%~fI\envs\robot\python.exe"

echo.
echo [3/4] 验证依赖能否导入 ...
if defined ROBOT_PY (
    "%ROBOT_PY%" -c "import sys, pybullet, pybullet_data, cv2, numpy; print('OK  python', sys.version.split()[0], '| pybullet', pybullet.getAPIVersion(), '| opencv', cv2.__version__, '| numpy', numpy.__version__)"
) else (
    "%CONDA_EXE%" run -n robot --no-capture-output python -c "import sys, pybullet, pybullet_data, cv2, numpy; print('OK  python', sys.version.split()[0], '| pybullet', pybullet.getAPIVersion(), '| opencv', cv2.__version__, '| numpy', numpy.__version__)"
)
if errorlevel 1 (
    echo [x] 依赖导入失败。把上面的报错整段发给队友，不要自己乱改。
    pause & exit /b 1
)

rem ---------- [4/4] 冒烟测试 ----------
echo.
echo [4/4] 跑冒烟测试验收（smoke.py，约 1 分钟）...
echo.
if not exist smoke.py (
    echo   当前目录里没有 smoke.py，跳过自动验收。
    echo   请把本脚本放在 robot_teach 项目根目录下再运行。
    echo.
    pause & exit /b 0
)
if defined ROBOT_PY (
    "%ROBOT_PY%" smoke.py
) else (
    "%CONDA_EXE%" run -n robot --no-capture-output python smoke.py
)

echo.
echo ==========================================================
echo   验收标准：上面出现「抓取环节：成功」，并且 results\ 下生成了
echo   smoke_raw.png / smoke_before.png / smoke_after.png。
echo   拿 results\smoke_after.png 对照标准场景图，口诀：数方块 ——
echo   红/绿/蓝 三个方块 + 黄/紫 两块区域 + Panda 机械臂 + 深色整块方桌。
echo ==========================================================
echo.
echo 以后每次跑项目（在本目录打开命令行）：
echo   conda activate robot
echo   python main.py --cam --demo --realtime
echo.
pause
