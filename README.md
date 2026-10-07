# AI Smart Waste Truck & Autonomous Robotic Sorter

An autonomous intelligent waste management vehicle that navigates towards detected trash, executes closed-loop closed-range inch-by-inch alignment, grabs waste from the ground using a 6-DOF robotic arm, and deposits it into an onboard sorting bin.

---

## 🌟 System Highlights

- **YOLOv8 Real-Time AI Vision**: Fine-tuned on real truck perspective photos and battery/cup waste datasets, running at ~10ms latency on GPU.
- **Inch-by-Inch Visual Servoing**: Closed-loop tracking steers the truck with proportional curve commands (`CMD:FORWARD_LEFT`, `CMD:FORWARD_RIGHT`), locks the bumper, and computes base offset direction and timing (`ARM:PICK_TARGET:<CLASS>:<DIR>:<MS>`).
- **6-DOF Precision Robotic Arm**: Smooth interpolation via PCA9685 I2C driver (1500us center, ground pickup descent, 180° swing to rear bed, container dip, drop, rim clearance, and return home).
- **Dual ESP32 Wireless Architecture**:
  - **ESP32-CAM**: Low-latency MJPEG video stream over Wi-Fi (`http://<CAM_IP>:81/stream`).
  - **ESP32 DevKit**: Real-time motion and actuator execution over UDP port `8888`.
- **4WD Chassis Control**: 2x L298N dual H-bridge motor drivers driving 4 DC motors with soft PWM speed control and safety halt during arm sequences.

---

## 📂 Project Directory Structure

```text
AI-truck/
├── robot_wireless_controller.py      # Root launcher for AI autonomous tracking & arm control
├── run_smart_waste_robot.bat         # 1-click Windows runner for full autonomous pipeline
├── test_devkit_control.py            # Hardware diagnostic for chassis motors & arm servos
├── AI-truck-main/
│   └── ml-model-main/
│       ├── esp32_devkit_firmware/    # ESP32 DevKit C++ firmware (Motors, PCA9685 6-DOF arm, UDP)
│       ├── esp32_cam_firmware/       # ESP32-CAM Wi-Fi video streaming firmware
│       ├── weights/
│       │   └── best_trash_yolov8m.pt # Fine-tuned YOLOv8m model weights (~93% precision)
│       ├── auto_train_test_loop.py   # Automated training and test evaluation script
│       ├── train_truck_model.py      # Truck-perspective fine-tuning script
│       ├── test_manual_ml_cam.py     # Standalone camera + HUD detection tester
│       ├── data.yaml                 # Dataset configuration
│       ├── train/ & valid/           # Training and validation datasets
│       └── README.md                 # Detailed pinout & technical specifications
```

---

## ⚡ Quick Start

### 1. Upload Firmware
1. **ESP32 DevKit**:
   - Open `AI-truck-main/ml-model-main/esp32_devkit_firmware/esp32_devkit_firmware.ino` in Arduino IDE.
   - Set board to **ESP32 Dev Module**.
   - Configure your Wi-Fi SSID and Password in the sketch.
   - Upload and note the IP address printed on Serial Monitor (115200 baud).

2. **ESP32-CAM**:
   - Open `AI-truck-main/ml-model-main/esp32_cam_firmware/esp32_cam_firmware.ino`.
   - Set board to **AI Thinker ESP32-CAM**.
   - Configure the same Wi-Fi SSID and Password.
   - Upload and open Serial Monitor to get the stream URL (e.g. `http://192.168.1.50:81/stream`).

### 2. Run the Autonomous AI Truck
Open a terminal or double-click `run_smart_waste_robot.bat`, or run:
```bash
python robot_wireless_controller.py
```
To run directly with specific ESP32 IP addresses:
```bash
python robot_wireless_controller.py --devkit-ip 192.168.1.100 --cam-ip 192.168.1.50
```

### 3. Hardware Test & Diagnostics
To test individual motor directions or servo joints:
```bash
python test_devkit_control.py --devkit-ip 192.168.1.100
```
Use options:
- `w` / `s` / `a` / `d` / `x`: Drive forward, backward, left, right, stop
- `t`: Execute full pick-and-place smart arm cycle
- `home`: Move arm to compact resting position
