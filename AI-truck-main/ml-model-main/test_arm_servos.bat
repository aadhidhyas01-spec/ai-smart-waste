@echo off
title 6-DOF Robotic Arm Servo Diagnostic Tester
cd /d "%~dp0"
echo =========================================================================
echo   PCA9685 6-DOF Robotic Arm Servo Diagnostic Tester
echo   Target ESP32 DevKit: 192.168.137.241:8888
echo =========================================================================
echo.
python test_arm_servos.py %*
pause
