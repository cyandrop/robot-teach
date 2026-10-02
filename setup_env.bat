@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   一键装环境（只需跑一次）
echo ==========================================
echo.
echo [1/3] 创建 conda 环境 robot（Python 3.11）
call conda create -n robot python=3.11 -y
echo.
echo [2/3] 安装 pybullet / opencv / numpy
call conda activate robot
call conda install -c conda-forge pybullet opencv numpy -y
echo.
echo [3/3] 跑冒烟测试验收
call conda activate robot
python smoke.py
echo.
echo 如果上面打印出 PASS / 成功，并在 results 文件夹生成了 png，说明环境 OK。
echo 把生成的截图发到群里，和 A 发的「仿真截图_有物料.png」对照：
echo   红绿蓝 三个方块 + 黄紫 两块区域 + Panda 机械臂 + 深色整块方桌
echo   数不对就是没跑对，别硬往下做。
echo.
pause
