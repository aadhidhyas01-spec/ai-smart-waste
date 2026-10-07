@echo off
title Smart Waste Management Robot - AI Vision & Autonomous Controller
cd /d "%~dp0"
echo =========================================================================
echo   Smart Waste Management Robot: AI Vision + Robotic Manipulation
echo   Camera Feed : http://192.168.137.234:81/stream
echo   Robot DevKit: 192.168.137.22:8888
echo   AI Model    : YOLOv8m (NVIDIA RTX 4060 GPU)
echo =========================================================================
echo.
python robot_wireless_controller.py %*
pause
