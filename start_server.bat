@echo off
echo ========================================
echo 晶体生长实验记录助手 - 一键启动脚本
echo ========================================

cd /d "%~dp0"

echo.
echo 1. 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo 错误: 未找到Python，请安装Python 3.10+
    pause
    exit /b 1
)

echo.
echo 2. 安装依赖...
pip install -r requirements.txt

echo.
echo 3. 创建存储目录...
mkdir storage\images 2>nul

echo.
echo 4. 启动API服务...
echo 服务将在 http://localhost:8000 启动
echo.
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000

pause