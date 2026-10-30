# AI Smart Waste Truck & Autonomous Robotic Sorter — Earlier Prototype

This repository preserves an earlier YOLOv8 + ESP32 prototype for an autonomous waste-collection truck. It includes truck-perspective training samples, ESP32 firmware, a wireless controller and six-degree-of-freedom arm experiments.

<blockquote>
<strong>Current consolidated project:</strong> <a href="https://github.com/aadhidhyas01-spec/ML-TRUCK">ML-TRUCK</a> is the newer and more structured project containing the latest 12-class dataset configuration, modular source tree, scripts, hardware firmware, tests and documentation.
</blockquote>

## What this snapshot contains

- YOLOv8 training and test scripts for truck-perspective images.
- ESP32-CAM MJPEG streaming firmware.
- ESP32 DevKit firmware for the 4WD chassis and PCA9685-controlled arm.
- Wireless Python controller and manual hardware test tools.
- Additional real truck-perspective battery and cup samples.

## Run the earlier prototype

Use the instructions and IP configuration in the original project README below. Update the ESP32 camera and DevKit IP addresses to match your current Wi-Fi network before running any controller.

For active development, use the [ML-TRUCK repository](https://github.com/aadhidhyas01-spec/ML-TRUCK).

## Benchmark note

Any accuracy or latency values shown in this historical README are outputs reported by the earlier project's own scripts and hardware setup. They have not been independently reproduced in this review and should not be treated as guaranteed performance.
