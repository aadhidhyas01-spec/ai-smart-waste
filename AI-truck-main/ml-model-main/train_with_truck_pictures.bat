@echo off
title Smart Waste Truck AI - Camera Training Hub
cd /d "%~dp0"

:MENU
cls
echo ======================================================================
echo          🚛 SMART WASTE TRUCK AI - DATASET & TRAINING HUB 🚛
echo ======================================================================
echo.
echo   [1] CAPTURE LIVE PHOTOS FROM TRUCK CAMERA (ESP32-CAM)
echo       - Connects to http://192.168.137.234:81/stream
echo       - Shows live feed + AI preview
echo       - Press [SPACE] to capture & save into dataset
echo.
echo   [2] IMPORT PHOTOS FROM 'truck_photos' FOLDER
echo       - Have photos taken with your phone?
echo       - Place them in truck_photos\ and label them here
echo.
echo   [3] TRAIN / FINE-TUNE YOLO MODEL
echo       - Fine-tunes model on your exact truck pictures
echo       - Auto-deploys to weights\best_trash_yolov8m.pt
echo.
echo   [4] TEST MODEL ON LIVE TRUCK CAMERA STREAM
echo       - Verify detection accuracy on your waste objects
echo.
echo   [5] LAUNCH ROBOT WIRELESS CONTROLLER
echo       - Runs full autonomous pick-and-place with your new model
echo.
echo   [Q] Quit
echo.
echo ======================================================================
set /p choice="Select an option [1-5 or Q]: "

if /i "%choice%"=="1" goto CAPTURE
if /i "%choice%"=="2" goto IMPORT
if /i "%choice%"=="3" goto TRAIN
if /i "%choice%"=="4" goto TEST_CAM
if /i "%choice%"=="5" goto LAUNCH_ROBOT
if /i "%choice%"=="q" goto EXIT

goto MENU

:CAPTURE
cls
echo Starting Live Truck Camera Collector...
python collect_truck_samples.py --source http://192.168.137.234:81/stream
pause
goto MENU

:IMPORT
cls
echo Opening Offline Photo Annotator for 'truck_photos\' folder...
python import_truck_photos.py
pause
goto MENU

:TRAIN
cls
call train_truck_model.bat
goto MENU

:TEST_CAM
cls
echo Launching Live Object Detection Test...
python test_manual_ml_cam.py --source http://192.168.137.234:81/stream
pause
goto MENU

:LAUNCH_ROBOT
cls
echo Launching Full Robot Controller...
python robot_wireless_controller.py
pause
goto MENU

:EXIT
echo Exiting. Goodbye!
exit /b
