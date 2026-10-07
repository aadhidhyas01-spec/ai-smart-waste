@echo off
title ESP32-CAM Connection Tester
cd /d "%~dp0"
echo ========================================================
echo        ESP32-CAM Wireless Video Stream Tester
echo ========================================================
echo.
set /p CAM_IP="Enter your ESP32-CAM IP address (e.g. 192.168.137.10 or 172.16.x.x): "

if "%CAM_IP%"=="" (
    echo No IP entered, scanning local network...
    python test_cam_connection.py --scan
) else (
    python test_cam_connection.py --ip %CAM_IP%
)

echo.
pause
