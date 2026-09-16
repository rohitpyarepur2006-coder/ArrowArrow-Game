@echo off
chcp 65001 >nul
REM 将游戏打包为单文件可执行程序（输出到 dist\ArrowArrow.exe）
REM 打包前请确保已安装依赖：pip install -r requirements.txt pyinstaller
cd /d %~dp0..

pyinstaller --onefile --windowed --name ArrowArrow main.py

echo.
echo 打包完成，可执行文件位于 dist\ArrowArrow.exe
echo 运行游戏生成的存档 save.json 保存在 exe 所在目录。
pause
