@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo 个人公开信息搜索系统
echo ============================================================
echo.
echo 选择运行模式:
echo   1. 交互式输入模式
echo   2. 简历文件模式 (支持 PDF/Word/图片/TXT)
echo   3. 启动Web网站 (浏览器访问)
echo   4. 帮助信息
echo.
set /p choice=请输入选项 (1/2/3/4):
echo.

if "%choice%"=="1" goto cli
if "%choice%"=="2" goto file
if "%choice%"=="3" goto web
if "%choice%"=="4" goto help
echo 无效选项，退出。
pause
exit

:cli
echo 启动交互式输入模式...
python main.py --cli
pause
exit

:file
echo 请输入简历文件完整路径:
set /p filepath=文件路径:
echo.
if "%filepath%"=="" (
    echo 未输入文件路径，退出。
    pause
    exit
)
python main.py "%filepath%"
pause
exit

:web
echo 正在启动Web服务器...
echo 服务器启动后，请在浏览器中访问: http://localhost:5000
echo.
echo 按 Ctrl+C 停止服务器
echo.
python app.py
pause
exit

:help
echo.
echo 使用方法:
echo.
echo 1. 交互式输入模式:
echo    python main.py --cli
echo.
echo 2. 简历文件模式:
echo    python main.py "d:\简历\张三.pdf"
echo    python main.py "d:\简历\李四.docx"
echo    python main.py "d:\简历\王五.jpg"
echo.
echo 3. Web网站模式:
echo    python app.py
echo    然后在浏览器访问 http://localhost:5000
echo.
echo 支持的文件格式: .docx, .pdf, .jpg, .jpeg, .png, .bmp, .txt
echo.
echo 报告将保存在 output 目录下。
echo.
pause