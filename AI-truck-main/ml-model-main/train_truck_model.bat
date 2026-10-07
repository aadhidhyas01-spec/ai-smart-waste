@echo off
title Train YOLOv8 with Truck Pictures
cd /d "%~dp0"
echo ======================================================================
echo           TRAIN YOLOV8 WITH REAL TRUCK PICTURES
echo ======================================================================
echo.
echo Select training speed / epochs:
echo   [1] Fast Fine-Tuning  (15 epochs - approx 8 to 15 mins on CPU)  [Recommended]
echo   [2] Standard Training (30 epochs - deeper adaptation)
echo   [3] Custom Epochs
echo.
set /p opt="Enter choice [1, 2, or 3] (Default 1): "
if "%opt%"=="" set opt=1

if "%opt%"=="1" (
    python train_truck_model.py --epochs 15
) else if "%opt%"=="2" (
    python train_truck_model.py --epochs 30
) else if "%opt%"=="3" (
    set /p custom_ep="Enter number of epochs: "
    python train_truck_model.py --epochs %custom_ep%
) else (
    python train_truck_model.py --epochs 15
)

echo.
echo ======================================================================
echo Training process finished.
echo The model has been saved to: weights\best_trash_yolov8m.pt
echo ======================================================================
pause
