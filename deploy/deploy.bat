@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo =============================================
echo  Milk-V Duo 摄像头YOLO检测 部署脚本
echo =============================================
echo.

set BOARD_IP=192.168.42.1
set BOARD_USER=root
set BOARD_DIR=/root/app
set MODEL_FILE=..\best11_ir9.onnx

:: 1. 检查板子连接
echo [1/5] 检查板子连接...
ping -n 1 -w 1000 %BOARD_IP% >nul 2>&1
if %errorlevel% neq 0 (
    echo [警告] 无法 ping 通 %BOARD_IP%
    echo.
    echo 请确认:
    echo   1. Milk-V Duo 已通过前面板 USB 口连接电脑
    echo   2. 已安装 RNDIS 驱动
    echo   3. 板子已上电启动完成
    echo.
    set /p CONTINUE="是否继续? (y/n): "
    if /i not "!CONTINUE!"=="y" exit /b 1
) else (
    echo [OK] 板子在线
)

:: 2. 创建远程目录
echo.
echo [2/5] 创建板端目录...
ssh %BOARD_USER%@%BOARD_IP% "mkdir -p %BOARD_DIR%" 2>nul

:: 3. 传输文件
echo [3/5] 传输文件到板子...
echo   传输 board_camera.py ...
scp board_camera.py %BOARD_USER%@%BOARD_IP%:%BOARD_DIR%/
echo   传输 setup_board.sh ...
scp setup_board.sh %BOARD_USER%@%BOARD_IP%:%BOARD_DIR%/

echo   传输 ONNX 模型 (%MODEL_FILE%)...
if exist "%MODEL_FILE%" (
    scp "%MODEL_FILE%" %BOARD_USER%@%BOARD_IP%:%BOARD_DIR%/
    echo   [OK] 模型传输完成
) else (
    echo   [错误] 找不到模型文件: %MODEL_FILE%
    echo   请在项目根目录放置 best11_ir9.onnx
    goto :end
)

:: 4. 初始化板端环境
echo.
echo [4/5] 初始化板端 Python 环境...
ssh %BOARD_USER%@%BOARD_IP% "cd %BOARD_DIR% && sh setup_board.sh"

:: 5. 启动检测
echo.
echo [5/5] 启动摄像头检测服务...
echo.
echo =============================================
echo  部署完成！接下来启动检测:
echo =============================================
echo.
echo 在板子上运行:
echo   ssh root@%BOARD_IP%
echo   cd %BOARD_DIR%
echo   python board_camera.py --model best11_ir9.onnx
echo.
echo 然后在PC浏览器打开:
echo   http://192.168.42.1:8080
echo   就能看到实时检测画面!
echo =============================================

:end
pause
