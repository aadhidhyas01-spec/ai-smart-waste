@echo off
title ESP32-CAM YOLO Trash Detection
cd /d "%~dp0"
echo =========================================================================
echo   Testing YOLOv8 on ESP32-CAM Live Feed
echo   Stream URL: http://192.168.137.234:81/stream
echo   DevKit IP : 192.168.137.117:8888
echo =========================================================================
echo.
python test_manual_ml_cam.py --source http://192.168.137.234:81/stream
pause
