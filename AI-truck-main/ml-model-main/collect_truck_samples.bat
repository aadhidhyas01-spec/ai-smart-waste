@echo off
title Truck Camera Photo Collector
cd /d "%~dp0"
echo ======================================================================
echo  [1/2] Checking ESP32-CAM Connection at http://192.168.137.234:81/stream ...
echo ======================================================================
python collect_truck_samples.py --source http://192.168.137.234:81/stream
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] ESP32-CAM stream was not reachable or was closed.
    echo If you want to use your laptop webcam to test, run:
    echo   python collect_truck_samples.py --source 0
    echo.
)
pause
