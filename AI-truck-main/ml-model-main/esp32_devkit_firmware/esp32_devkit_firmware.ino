/*
 * ==============================================================================
 * ESP32 NodeMCU-32S / DevKit - Wireless Smart Waste Robot Receiver & Arm
 * Controller
 * ==============================================================================
 * Features:
 *   - Wi-Fi UDP (Port 8888) Command & Telemetry Receiver
 *   - 4-Wheel Drive Base: 2x L298N Motor Drivers
 *     * SMOOTH PIVOT STEERING: Stops one side wheels and drives the opposite
 * side, eliminating wheel fight, stalling, and ground friction!
 *   - 6-DOF Robotic Arm: PCA9685 16-Channel I2C PWM Driver (GPIO 21 SDA, 22
 * SCL)
 *   - Obstacle Guard: HC-SR04 Ultrasonic Sensor (TRIG 4, ECHO 23)
 * ==============================================================================
 * CONNECTION PINOUT:
 * ------------------------------------------------------------------------------
 *  MODULE            MODULE PIN   ESP32 GPIO
 *  -----------------------------------------------------------------------------
 *  PCA9685           SDA          GPIO 21 (D21/P21)
 *  PCA9685           SCL          GPIO 22 (D22/P22)
 *  PCA9685           VCC (Side)   3.3V or 5V (Logic Power)
 *  PCA9685           GND (Side)   GND (Common Ground)
 *  PCA9685           V+ (Green)   External 5V-6V Battery (+) [Servo Power]
 *  PCA9685           GND (Green)  External 5V-6V Battery (-) [Common Ground]
 *
 *  L298N #1 (Left)   IN1          GPIO 25 (FL Forward)
 *  L298N #1 (Left)   IN2          GPIO 26 (FL Reverse)
 *  L298N #1 (Left)   IN3          GPIO 27 (RL Forward)
 *  L298N #1 (Left)   IN4          GPIO 14 (RL Reverse)
 *
 *  L298N #2 (Right)  IN1          GPIO 32 (FR Forward)
 *  L298N #2 (Right)  IN2          GPIO 33 (FR Reverse)
 *  L298N #2 (Right)  IN3          GPIO 18 (RR Forward)
 *  L298N #2 (Right)  IN4          GPIO 19 (RR Reverse)
 *
 *  Ultrasonic        TRIG         GPIO 4
 *  Ultrasonic        ECHO         GPIO 23
 * ==============================================================================
 */

#include <Adafruit_PWMServoDriver.h>
#include <NetworkUdp.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>

// ------------------------------------------------------------------------------
// 1. WI-FI CONFIGURATION
// ------------------------------------------------------------------------------
const char *ssid = "AADHIDHYA";
const char *password = "12345678";
const unsigned int localUdpPort = 8888;

WiFiUDP udp;
char packetBuffer[255];

// ------------------------------------------------------------------------------
// 2. PCA9685 16-CHANNEL SERVO DRIVER CONFIGURATION (Address 0x40)
//
// YOUR ARM SERVO LAYOUT:
//   CH0 (CH_BASE)        : SG996R  360° CONTINUOUS rotation
//                          Neutral (STOP) = 1500 μs pulse → ~307 ticks
//                          CW  rotation  > 1500 μs pulse
//                          CCW rotation  < 1500 μs pulse
//   CH1 (CH_SHOULDER)    : SG996R  180° positional  (high torque)
//   CH2 (CH_ELBOW)       : SG996R  180° positional  (high torque)
//   CH3 (CH_WRIST_PITCH) : MG90S   180° positional  (small/light)
//   CH4 (CH_WRIST_ROLL)  : MG90S   180° positional  (small/light)
//   CH5 (CH_GRIPPER)     : MG90S   180° positional  (small/light)
// ------------------------------------------------------------------------------
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

#define SERVO_FREQ 50 // 50 Hz for all analog servos

// SG996R (CH1 & CH2): 500–2500 μs gives full 180° range
//   At 50Hz  → 4096 ticks/period (20ms)
//   1 tick   = 20000μs / 4096 ≈ 4.88 μs
#define SERVO996_MIN 102 //  500 μs →  0°
#define SERVO996_MAX 512 // 2500 μs → 180°

// MG90S (CH3 CH4 CH5): standard 1000–2000 μs range
#define SERVOMG90_MIN 205 // 1000 μs →  0°
#define SERVOMG90_MAX 410 // 2000 μs → 180°

// SG996R 360° continuous rotation (CH0 BASE):
//   Neutral STOP  = 1500 μs ≈ 307 ticks
//   Full CW       = 2000 μs ≈ 410 ticks  (or higher for faster)
//   Full CCW      = 1000 μs ≈ 205 ticks  (or lower for faster)
#define BASE_NEUTRAL 307  // 1500 μs → motor stops
#define BASE_FULL_CW 410  // 2000 μs → max CW speed
#define BASE_FULL_CCW 205 // 1000 μs → max CCW speed

// 6-DOF Servo Channels on PCA9685
#define CH_BASE 0        // SG996R 360° CONTINUOUS (base yaw)
#define CH_SHOULDER 1    // SG996R 180° positional (shoulder pitch)
#define CH_ELBOW 2       // SG996R 180° positional (elbow pitch)
#define CH_WRIST_PITCH 3 // MG90S  180° positional (wrist tilt)
#define CH_WRIST_ROLL 4  // MG90S  180° positional (wrist roll)
#define CH_GRIPPER 5     // MG90S  180° positional (claw)

int currentAngles[6] = {-1, -1, -1, -1, -1, -1};
bool pcaReady = false;

// ---------- Helper: return correct SERVOMIN for a given channel ----------
inline int servoMin(uint8_t ch) {
  return (ch <= 2) ? SERVO996_MIN : SERVOMG90_MIN;
}
inline int servoMax(uint8_t ch) {
  return (ch <= 2) ? SERVO996_MAX : SERVOMG90_MAX;
}

// ---------- Positional servo angle setter (CH1-CH5 only) -----------------
void setServoAngle(uint8_t channel, int angle) {
  if (channel == 0 || channel >= 6 || !pcaReady)
    return; // CH0 is continuous!
  angle = constrain(angle, 0, 180);
  int pulse = map(angle, 0, 180, servoMin(channel), servoMax(channel));
  pca.setPWM(channel, 0, pulse);
  currentAngles[channel] = angle;
}

void smoothMoveServo(uint8_t channel, int targetAngle, int stepDelay = 10) {
  if (channel == 0 || channel >= 6 || !pcaReady)
    return;
  targetAngle = constrain(targetAngle, 0, 180);
  int startAngle = currentAngles[channel];
  if (startAngle < 0) {
    setServoAngle(channel, targetAngle);
    return;
  }
  if (startAngle == targetAngle) {
    setServoAngle(channel, targetAngle);
    return;
  }
  int step = (targetAngle > startAngle) ? 1 : -1;
  for (int a = startAngle; a != targetAngle; a += step) {
    int pulse = map(a, 0, 180, servoMin(channel), servoMax(channel));
    pca.setPWM(channel, 0, pulse);
    delay(stepDelay);
  }
  setServoAngle(channel, targetAngle);
}

// ============================================================
// BASE 360° CONTINUOUS ROTATION (SG996R) CONTROL
// speed: -100 (full CCW) … 0 (STOP) … +100 (full CW)
// ============================================================
void baseStop() {
  // Send exact neutral pulse to stop the 360° servo
  pca.setPWM(CH_BASE, 0, BASE_NEUTRAL);
  currentAngles[CH_BASE] = 0; // use 0 as "parked / unknown" marker
  Serial.println("[ARM BASE] STOP (neutral 1500us)");
}

void baseSetSpeed(int speed) {
  // speed -100..+100, maps to CCW_FULL..NEUTRAL..CW_FULL pulse range
  speed = constrain(speed, -100, 100);
  int pulse;
  if (speed == 0) {
    pulse = BASE_NEUTRAL;
  } else if (speed > 0) {
    pulse = map(speed, 0, 100, BASE_NEUTRAL, BASE_FULL_CW);
  } else {
    pulse = map(speed, -100, 0, BASE_FULL_CCW, BASE_NEUTRAL);
  }
  pca.setPWM(CH_BASE, 0, pulse);
  Serial.printf("[ARM BASE] Speed=%d%%  pulse=%d ticks\n", speed, pulse);
}

void baseRotateCW(int speed, unsigned int durationMs) {
  Serial.printf("[ARM BASE] Rotate CW  speed=%d%%  for %d ms\n", speed,
                durationMs);
  int safeSpeed = (speed < 0) ? -speed : speed;
  baseSetSpeed(safeSpeed);
  delay(durationMs);
  baseStop();
}

void baseRotateCCW(int speed, unsigned int durationMs) {
  Serial.printf("[ARM BASE] Rotate CCW speed=%d%%  for %d ms\n", speed,
                durationMs);
  int safeSpeed = (speed < 0) ? -speed : speed;
  baseSetSpeed(-safeSpeed);
  delay(durationMs);
  baseStop();
}

// ------------------------------------------------------------------------------
// 3. MOTOR DRIVER PIN ASSIGNMENTS (2x L298N Drivers -> 4 DC Motors)
//
// *** FF-130 / FA-130 MOTOR WIRING FOR PWM SPEED CONTROL ***
// Remove the ENA & ENB jumpers from BOTH L298N boards, then wire:
//   L298N Driver 1  ENA ──┐
//                   ENB ──┴──── GPIO 12 (EN_LEFT)
//   L298N Driver 2  ENA ──┐
//                   ENB ──┴──── GPIO 13 (EN_RIGHT)
// This gives independent left/right speed via PWM.
// ------------------------------------------------------------------------------
// DRIVER 1: LEFT MOTORS (Front-Left & Rear-Left)
#define D1_IN1 25 // Front-Left  Forward
#define D1_IN2 26 // Front-Left  Reverse
#define D1_IN3 27 // Rear-Left   Forward
#define D1_IN4 14 // Rear-Left   Reverse

// DRIVER 2: RIGHT MOTORS (Front-Right & Rear-Right)
#define D2_IN1 32 // Front-Right Forward
#define D2_IN2 33 // Front-Right Reverse
#define D2_IN3 18 // Rear-Right  Forward
#define D2_IN4 19 // Rear-Right  Reverse

// PWM Enable pins (connect to ENA+ENB of each L298N board after removing
// jumpers)
#define EN_LEFT 12  // GPIO 12 -> L298N Driver 1 ENA & ENB (left motors)
#define EN_RIGHT 13 // GPIO 13 -> L298N Driver 2 ENA & ENB (right motors)

// LEDC PWM settings — 5 kHz is optimal for small brushed DC motors
#define PWM_FREQ 5000 // Hz
#define PWM_RES 8     // bits: 0 = stop, 255 = full speed

// Default drive speed (0-255).
// For FF-130 motor on 5V supply  -> use 180-220
// For FF-130 motor on 12V supply -> use 80-120  (keeps motor cool!)
int motorSpeed = 180;

bool isDrivingForward = false;

// ---------- PWM helpers (call these instead of direct ledcWrite) ----------
inline void setLeftPWM(int spd) { ledcWrite(EN_LEFT, constrain(spd, 0, 255)); }
inline void setRightPWM(int spd) {
  ledcWrite(EN_RIGHT, constrain(spd, 0, 255));
}
inline void enableDrive() {
  setLeftPWM(motorSpeed);
  setRightPWM(motorSpeed);
}
inline void disableDrive() {
  setLeftPWM(0);
  setRightPWM(0);
}

// Safety Watchdog: Stops motors if no command received within 2500ms
unsigned long lastPacketTime = 0;
const unsigned long SAFETY_TIMEOUT_MS = 2500;

// ------------------------------------------------------------------------------
// 4. ULTRASONIC OBSTACLE SENSOR (HC-SR04)
// ------------------------------------------------------------------------------
#define ENABLE_ULTRASONIC false // Set to true if HC-SR04 is installed
#define TRIG_PIN 4              // Trigger output pin (P4)
#define ECHO_PIN 23             // Echo input pin (P23)
#define OBSTACLE_LIMIT_CM 18.0  // Safety stop threshold (cm)

float currentDistanceCm = 999.0;
bool obstacleDetected = false;

// Wireless UDP Telemetry
IPAddress clientIP;
unsigned int clientPort = 0;
bool clientKnown = false;
unsigned long lastTelemetryTime = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 1000;

float readUltrasonicCm() {
#if ENABLE_ULTRASONIC
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 25000);
  if (duration == 0)
    return -1.0;
  return (duration * 0.0343) / 2.0;
#else
  return 999.0;
#endif
}

void updateSensors() {
#if ENABLE_ULTRASONIC
  static unsigned long lastSensorPoll = 0;
  if (millis() - lastSensorPoll >= 80) {
    lastSensorPoll = millis();

    float d = readUltrasonicCm();
    if (d > 0.0 && d < 400.0) {
      currentDistanceCm = d;
      obstacleDetected = (currentDistanceCm <= OBSTACLE_LIMIT_CM);
    } else {
      obstacleDetected = false;
    }
  }
#endif
}

void sendTelemetry() {
  if (!clientKnown)
    return;

  char teleBuf[100];
  snprintf(teleBuf, sizeof(teleBuf), "TELEM:DIST=%.1f,OBST=%d",
           currentDistanceCm, obstacleDetected ? 1 : 0);

  udp.beginPacket(clientIP, clientPort);
  udp.print(teleBuf);
  udp.endPacket();
}

// ==============================================================================
// MOTOR CONTROL FUNCTIONS (SMOOTH PIVOT STEERING & FULL POWER)
// ==============================================================================

// ==============================================================================
// MOTOR CONTROL FUNCTIONS (PWM speed via LEDC on EN_LEFT / EN_RIGHT)
// Wiring reminder: remove L298N ENA/ENB jumpers, connect GPIO 12 & 13
// ==============================================================================

void moveForward() {
  if (obstacleDetected) {
    stopMotors();
    Serial.printf("[GUARD] Forward blocked! Obstacle at %.1f cm\n",
                  currentDistanceCm);
    return;
  }
  isDrivingForward = true;
  Serial.printf(">>> [MOTORS] FORWARD  speed=%d/255\n", motorSpeed);

  // Direction: both sides FORWARD
  digitalWrite(D1_IN1, HIGH);
  digitalWrite(D1_IN2, LOW);
  digitalWrite(D1_IN3, HIGH);
  digitalWrite(D1_IN4, LOW);
  digitalWrite(D2_IN1, HIGH);
  digitalWrite(D2_IN2, LOW);
  digitalWrite(D2_IN3, HIGH);
  digitalWrite(D2_IN4, LOW);

  // Enable at configured speed
  setLeftPWM(motorSpeed);
  setRightPWM(motorSpeed);
}

void moveBackward() {
  isDrivingForward = false;
  Serial.printf(">>> [MOTORS] BACKWARD  speed=%d/255\n", motorSpeed);

  // Direction: both sides REVERSE
  digitalWrite(D1_IN1, LOW);
  digitalWrite(D1_IN2, HIGH);
  digitalWrite(D1_IN3, LOW);
  digitalWrite(D1_IN4, HIGH);
  digitalWrite(D2_IN1, LOW);
  digitalWrite(D2_IN2, HIGH);
  digitalWrite(D2_IN3, LOW);
  digitalWrite(D2_IN4, HIGH);

  setLeftPWM(motorSpeed);
  setRightPWM(motorSpeed);
}

// ------------------------------------------------------------------------------
// PIVOT LEFT: right side full forward, left side stopped  (pure in-place turn)
// ------------------------------------------------------------------------------
void steerLeft() {
  isDrivingForward = false;
  Serial.println(">>> [MOTORS] PIVOT LEFT");

  // Left motors: direction forward (will be stopped via PWM)
  digitalWrite(D1_IN1, HIGH);
  digitalWrite(D1_IN2, LOW);
  digitalWrite(D1_IN3, HIGH);
  digitalWrite(D1_IN4, LOW);
  // Right motors: forward
  digitalWrite(D2_IN1, HIGH);
  digitalWrite(D2_IN2, LOW);
  digitalWrite(D2_IN3, HIGH);
  digitalWrite(D2_IN4, LOW);

  setLeftPWM(0);           // LEFT stopped
  setRightPWM(motorSpeed); // RIGHT full forward
}

// ------------------------------------------------------------------------------
// PIVOT RIGHT: left side full forward, right side stopped  (pure in-place turn)
// ------------------------------------------------------------------------------
void steerRight() {
  isDrivingForward = false;
  Serial.println(">>> [MOTORS] PIVOT RIGHT");

  // Left motors: forward
  digitalWrite(D1_IN1, HIGH);
  digitalWrite(D1_IN2, LOW);
  digitalWrite(D1_IN3, HIGH);
  digitalWrite(D1_IN4, LOW);
  // Right motors: forward (will be stopped via PWM)
  digitalWrite(D2_IN1, HIGH);
  digitalWrite(D2_IN2, LOW);
  digitalWrite(D2_IN3, HIGH);
  digitalWrite(D2_IN4, LOW);

  setLeftPWM(motorSpeed); // LEFT full forward
  setRightPWM(0);         // RIGHT stopped
}

void stopMotors() {
  isDrivingForward = false;

  // Disable both enable pins first (motor coasts to stop)
  setLeftPWM(0);
  setRightPWM(0);

  // Then clear direction pins
  digitalWrite(D1_IN1, LOW);
  digitalWrite(D1_IN2, LOW);
  digitalWrite(D1_IN3, LOW);
  digitalWrite(D1_IN4, LOW);
  digitalWrite(D2_IN1, LOW);
  digitalWrite(D2_IN2, LOW);
  digitalWrite(D2_IN3, LOW);
  digitalWrite(D2_IN4, LOW);
}

// ------------------------------------------------------------------------------
// FORWARD + CURVE LEFT (WA): right full speed, left at 40% speed
// Produces a wide arc-left while rolling forward
// ------------------------------------------------------------------------------
void forwardCurveLeft() {
  if (obstacleDetected) {
    stopMotors();
    return;
  }
  isDrivingForward = true;
  Serial.println(">>> [MOTORS] FORWARD + CURVE LEFT");

  // Both sides FORWARD direction
  digitalWrite(D1_IN1, HIGH);
  digitalWrite(D1_IN2, LOW);
  digitalWrite(D1_IN3, HIGH);
  digitalWrite(D1_IN4, LOW);
  digitalWrite(D2_IN1, HIGH);
  digitalWrite(D2_IN2, LOW);
  digitalWrite(D2_IN3, HIGH);
  digitalWrite(D2_IN4, LOW);

  setLeftPWM(motorSpeed * 4 / 10); // Left ~40% (inner wheel)
  setRightPWM(motorSpeed);         // Right 100% (outer wheel)
}

// ------------------------------------------------------------------------------
// FORWARD + CURVE RIGHT (WD): left full speed, right at 40% speed
// Produces a wide arc-right while rolling forward
// ------------------------------------------------------------------------------
void forwardCurveRight() {
  if (obstacleDetected) {
    stopMotors();
    return;
  }
  isDrivingForward = true;
  Serial.println(">>> [MOTORS] FORWARD + CURVE RIGHT");

  digitalWrite(D1_IN1, HIGH);
  digitalWrite(D1_IN2, LOW);
  digitalWrite(D1_IN3, HIGH);
  digitalWrite(D1_IN4, LOW);
  digitalWrite(D2_IN1, HIGH);
  digitalWrite(D2_IN2, LOW);
  digitalWrite(D2_IN3, HIGH);
  digitalWrite(D2_IN4, LOW);

  setLeftPWM(motorSpeed);           // Left 100% (outer wheel)
  setRightPWM(motorSpeed * 4 / 10); // Right ~40% (inner wheel)
}

// ------------------------------------------------------------------------------
// BACKWARD + CURVE LEFT (SA): right reverse full, left reverse slow
// ------------------------------------------------------------------------------
void backCurveLeft() {
  isDrivingForward = false;
  Serial.println(">>> [MOTORS] BACKWARD + CURVE LEFT");

  // Both sides REVERSE direction
  digitalWrite(D1_IN1, LOW);
  digitalWrite(D1_IN2, HIGH);
  digitalWrite(D1_IN3, LOW);
  digitalWrite(D1_IN4, HIGH);
  digitalWrite(D2_IN1, LOW);
  digitalWrite(D2_IN2, HIGH);
  digitalWrite(D2_IN3, LOW);
  digitalWrite(D2_IN4, HIGH);

  setLeftPWM(motorSpeed * 4 / 10); // Left  ~40%
  setRightPWM(motorSpeed);         // Right 100%
}

// ------------------------------------------------------------------------------
// BACKWARD + CURVE RIGHT (SD): left reverse full, right reverse slow
// ------------------------------------------------------------------------------
void backCurveRight() {
  isDrivingForward = false;
  Serial.println(">>> [MOTORS] BACKWARD + CURVE RIGHT");

  digitalWrite(D1_IN1, LOW);
  digitalWrite(D1_IN2, HIGH);
  digitalWrite(D1_IN3, LOW);
  digitalWrite(D1_IN4, HIGH);
  digitalWrite(D2_IN1, LOW);
  digitalWrite(D2_IN2, HIGH);
  digitalWrite(D2_IN3, LOW);
  digitalWrite(D2_IN4, HIGH);

  setLeftPWM(motorSpeed);           // Left 100%
  setRightPWM(motorSpeed * 4 / 10); // Right ~40%
}

// ==============================================================================
// 6-DOF ROBOTIC ARM SEQUENCES (PCA9685)
//
// BASE (CH0) is a 360° CONTINUOUS servo → controlled by time, not angle.
// Bin rotation times are APPROXIMATE — tune BASE_CW_MS_PER_DEG for your setup.
// Measure: run baseRotateCW(60, 1000) and see how many degrees it turns.
// Then adjust BIN_x_MS to match your physical bin positions.
// ==============================================================================

// Tuning constants — adjust these after physical testing!
// Run ARM:BASE:CW:60:500 in the tester and measure how far it turns.
#define BASE_SPEED 60 // % speed (0-100) used for base rotations
int binRear180Ms =
    1100; // ms to rotate 180° from front to onboard rear container
int binPlasticMs = 1200; // ms to rotate CW to reach side Plastic bin (if used)
int binMetalMs = 800;    // ms to rotate CW to reach side Metal bin (if used)
int binGlassMs = 400;    // ms to rotate CCW to reach side Glass bin (if used)

void armHome() {
  if (!pcaReady)
    return;
  Serial.println(">>> [ARM] Moving to HOME position...");

  // !! BASE is 360° continuous: send neutral pulse to STOP it !!
  baseStop();

  // Return all positional joints to resting pose
  setServoAngle(CH_GRIPPER, 30);
  delay(120); // open claw
  setServoAngle(CH_WRIST_ROLL, 90);
  delay(120); // center roll
  setServoAngle(CH_WRIST_PITCH, 90);
  delay(120); // level wrist
  setServoAngle(CH_ELBOW, 90);
  delay(120); // elbow up
  setServoAngle(CH_SHOULDER, 100);
  delay(200); // shoulder raised
}

// ==============================================================================
// PICK & DROP INTO ONBOARD REAR CARGO CONTAINER (Matches Photo Sequence)
// Sequence:
//   1. Ground grab (Shoulder 50°, Elbow 60°, Wrist 70°, Grip 105°)
//   2. High lift clearance (Shoulder 110°, Elbow 100°, Wrist 90°)
//   3. 180° CW rotation to rear cargo box
//   4. Dip inside container (Shoulder 65°, Elbow 75°, Wrist 80°)
//   5. Open claw (Grip 30°) -> Drop object inside
//   6. Lift out of container (Shoulder 110°, Elbow 100°, Wrist 90°)
//   7. 180° CCW rotation back to front
//   8. Reset to Home pose
// ==============================================================================
void dropIntoOnboardRearBin() {
  Serial.printf(
      "[ARM] Rotating 180° CW towards onboard rear container (%d ms)...\n",
      binRear180Ms);
  baseRotateCW(BASE_SPEED, binRear180Ms);
  delay(300);

  // Dip arm down into the clear container box
  Serial.println("[ARM] Dipping inside rear container...");
  smoothMoveServo(CH_SHOULDER, 65, 12);
  smoothMoveServo(CH_ELBOW, 75, 12);
  smoothMoveServo(CH_WRIST_PITCH, 80, 10);
  delay(350);

  // Release object gently inside the box
  Serial.println("[ARM] Opening gripper -> Object dropped!");
  smoothMoveServo(CH_GRIPPER, 30, 10);
  delay(400);

  // Lift arm back up over the container walls
  Serial.println("[ARM] Lifting out of rear container...");
  smoothMoveServo(CH_SHOULDER, 110, 12);
  smoothMoveServo(CH_ELBOW, 100, 12);
  smoothMoveServo(CH_WRIST_PITCH, 90, 10);
  delay(300);

  // Rotate 180° CCW back to front facing position
  Serial.printf("[ARM] Returning 180° CCW to front (%d ms)...\n", binRear180Ms);
  baseRotateCCW(BASE_SPEED, binRear180Ms);
  delay(300);
}

// ==============================================================================
// SMART ML TARGET PICK & ONBOARD REAR BIN DEPOSIT
// Dynamically aims base toward left/right side if waste is offset, grabs
// object, rotates 180° into rear container, releases, and returns front center!
// ==============================================================================
void executeSmartTargetPickSequence(String wasteClass, String offsetDir,
                                    int offsetMs) {
  if (!pcaReady) {
    Serial.println("[ARM ERROR] PCA9685 not ready!");
    return;
  }
  stopMotors();
  Serial.printf("[ARM] Smart Pick: Class=%s  Dir=%s  Offset=%d ms\n",
                wasteClass.c_str(), offsetDir.c_str(), offsetMs);

  // ── Step 1: Base stopped, gripper open, arm lifted ────────────────────
  baseStop();
  smoothMoveServo(CH_GRIPPER, 30, 8);
  smoothMoveServo(CH_WRIST_ROLL, 90, 8);
  delay(150);

  // ── Step 2: AIM BASE TOWARDS WASTE ITEM (Left / Right Offset from ML) ──
  offsetMs = constrain(offsetMs, 0, 800);
  if (offsetDir == "LEFT" && offsetMs > 0) {
    Serial.printf("[ARM BASE] Aiming LEFT toward item (%d ms CCW)...\n",
                  offsetMs);
    baseRotateCCW(BASE_SPEED, offsetMs);
    delay(200);
  } else if (offsetDir == "RIGHT" && offsetMs > 0) {
    Serial.printf("[ARM BASE] Aiming RIGHT toward item (%d ms CW)...\n",
                  offsetMs);
    baseRotateCW(BASE_SPEED, offsetMs);
    delay(200);
  } else {
    Serial.println("[ARM BASE] Item is CENTERED, reaching straight ahead.");
  }

  // ── Step 3: Reach forward & down to ground level ──────────────────────
  Serial.println("[ARM] Reaching down to ground level...");
  smoothMoveServo(CH_SHOULDER, 50, 15);
  smoothMoveServo(CH_ELBOW, 60, 15);
  smoothMoveServo(CH_WRIST_PITCH, 70, 12);
  delay(350);

  // ── Step 4: Clamp gripper on waste item (battery / dust) ──────────────
  Serial.println("[ARM] Clamping gripper on object...");
  smoothMoveServo(CH_GRIPPER, 105, 12);
  delay(400);

  // ── Step 5: Lift arm up to clear chassis ──────────────────────────────
  Serial.println("[ARM] Lifting object from ground...");
  smoothMoveServo(CH_SHOULDER, 110, 15);
  smoothMoveServo(CH_ELBOW, 100, 15);
  smoothMoveServo(CH_WRIST_PITCH, 90, 12);
  delay(300);

  // ── Step 6: ROTATE 180° TOWARDS ONBOARD REAR CARGO BIN ────────────────
  // Geometry calculation:
  // If we turned LEFT (CCW) by offsetMs, to reach rear (180° CW from center),
  // we rotate CW by (binRear180Ms + offsetMs)!
  // If we turned RIGHT (CW) by offsetMs, we rotate CW by (binRear180Ms -
  // offsetMs)!
  int rearRotateMs = binRear180Ms;
  if (offsetDir == "LEFT") {
    rearRotateMs += offsetMs;
  } else if (offsetDir == "RIGHT") {
    rearRotateMs -= offsetMs;
  }
  rearRotateMs = max(400, rearRotateMs);

  Serial.printf("[ARM] Rotating CW toward onboard rear container (%d ms)...\n",
                rearRotateMs);
  baseRotateCW(BASE_SPEED, rearRotateMs);
  delay(300);

  // ── Step 7: Dip inside rear cargo box ─────────────────────────────────
  Serial.println("[ARM] Dipping inside rear container...");
  smoothMoveServo(CH_SHOULDER, 65, 12);
  smoothMoveServo(CH_ELBOW, 75, 12);
  smoothMoveServo(CH_WRIST_PITCH, 80, 10);
  delay(350);

  // ── Step 8: Open gripper -> Drop object inside ────────────────────────
  Serial.println("[ARM] Opening gripper -> Object dropped!");
  smoothMoveServo(CH_GRIPPER, 30, 10);
  delay(400);

  // ── Step 9: Lift arm out of container ─────────────────────────────────
  Serial.println("[ARM] Lifting out of rear container...");
  smoothMoveServo(CH_SHOULDER, 110, 12);
  smoothMoveServo(CH_ELBOW, 100, 12);
  smoothMoveServo(CH_WRIST_PITCH, 90, 10);
  delay(300);

  // ── Step 10: Rotate 180° CCW back to FRONT CENTER (0°) ────────────────
  Serial.printf("[ARM] Returning 180° CCW to front center (%d ms)...\n",
                binRear180Ms);
  baseRotateCCW(BASE_SPEED, binRear180Ms);
  delay(300);

  // ── Step 11: Return arm to driving HOME pose ──────────────────────────
  armHome();
}

void executePickSequence(String wasteClass) {
  executeSmartTargetPickSequence(wasteClass, "CENTER", 0);
}

// ==============================================================================
// SETUP
// ==============================================================================
void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println("\n========================================================");
  Serial.println(" Smart Waste Management Robot Controller (ESP32)");
  Serial.println("========================================================");

  // 1. Setup Motor Direction Pins
  pinMode(D1_IN1, OUTPUT);
  pinMode(D1_IN2, OUTPUT);
  pinMode(D1_IN3, OUTPUT);
  pinMode(D1_IN4, OUTPUT);
  pinMode(D2_IN1, OUTPUT);
  pinMode(D2_IN2, OUTPUT);
  pinMode(D2_IN3, OUTPUT);
  pinMode(D2_IN4, OUTPUT);

  // 2. Setup PWM Enable channels via LEDC (ESP32 hardware PWM)
  //    Frequency: 5 kHz, 8-bit resolution (0-255)
  ledcAttach(EN_LEFT, PWM_FREQ, PWM_RES);  // Channel for left motors
  ledcAttach(EN_RIGHT, PWM_FREQ, PWM_RES); // Channel for right motors

  stopMotors();
  Serial.printf("Chassis Motors Initialized. PWM speed=%d/255 (~%.0f%%)\n",
                motorSpeed, motorSpeed * 100.0 / 255.0);

  // 2. Setup Ultrasonic Sensor
#if ENABLE_ULTRASONIC
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  Serial.println("HC-SR04 Ultrasonic Sensor Initialized.");
#endif

  // 3. Setup I2C & PCA9685 Servo Driver
  Wire.begin(21, 22); // SDA = GPIO 21 (P21), SCL = GPIO 22 (P22)
  delay(100);

  Wire.beginTransmission(0x40);
  byte i2cErr = Wire.endTransmission();
  if (i2cErr == 0) {
    pcaReady = true;
    Serial.println("✅ [I2C SUCCESS] PCA9685 detected at address 0x40!");
    pca.begin();
    pca.setPWMFreq(SERVO_FREQ);
    delay(100);
    armHome();
    Serial.println("PCA9685 6-DOF Arm Initialized to Home Position.");
  } else {
    pcaReady = false;
    Serial.printf(
        "❌ [I2C ERROR] PCA9685 NOT detected at 0x40 (Error Code: %d)!\n",
        i2cErr);
    Serial.println("   --> Check SDA wire is connected to GPIO 21");
    Serial.println("   --> Check SCL wire is connected to GPIO 22");
    Serial.println("   --> Check PCA9685 VCC (side pin) is connected to 3.3V "
                   "or 5V and GND is connected");
    Serial.println("   --> Check Green Terminal block (V+) has dedicated 5V-6V "
                   "battery power!");
  }

  // 4. Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);

  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);

  int wifiAttempts = 0;
  while (WiFi.status() != WL_CONNECTED && wifiAttempts < 35) {
    delay(350);
    Serial.print(".");
    wifiAttempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nWi-Fi Connected!");
    Serial.print("ESP32 DevKit IP Address: ");
    Serial.println(WiFi.localIP());
    udp.begin(localUdpPort);
    Serial.printf("Listening on UDP port %d for AI commands & telemetry...\n",
                  localUdpPort);
  } else {
    Serial.println(
        "\nWi-Fi not yet connected (Will retry in background loop).");
  }
}

// ==============================================================================
// MAIN LOOP
// ==============================================================================
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastWifiRetry = 0;
    if (millis() - lastWifiRetry > 4000) {
      lastWifiRetry = millis();
      WiFi.begin(ssid, password);
      if (WiFi.status() == WL_CONNECTED) {
        udp.begin(localUdpPort);
      }
    }
  }

  updateSensors();

  if (isDrivingForward && obstacleDetected) {
    stopMotors();
    Serial.printf("[AUTO-HALT] Obstacle detected at %.1f cm! Stopped.\n",
                  currentDistanceCm);
  }

  if (millis() - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = millis();
    sendTelemetry();
  }

  int packetSize = udp.parsePacket();

  if (packetSize > 0) {
    clientIP = udp.remoteIP();
    clientPort = udp.remotePort();
    clientKnown = true;

    int len = udp.read(packetBuffer, 254);
    if (len > 0) {
      packetBuffer[len] = 0;
    }

    String cmd = String(packetBuffer);
    cmd.trim();
    Serial.printf("📡 [UDP RECEIVED] '%s'\n", cmd.c_str());
    lastPacketTime = millis();

    if (cmd == "CMD:FORWARD") {
      moveForward();
    } else if (cmd == "CMD:BACKWARD") {
      moveBackward();
    } else if (cmd == "CMD:LEFT") {
      steerLeft();
    } else if (cmd == "CMD:RIGHT") {
      steerRight();
    } else if (cmd == "CMD:FORWARD_LEFT") {
      forwardCurveLeft();
    } else if (cmd == "CMD:FORWARD_RIGHT") {
      forwardCurveRight();
    } else if (cmd == "CMD:BACK_LEFT") {
      backCurveLeft();
    } else if (cmd == "CMD:BACK_RIGHT") {
      backCurveRight();
    } else if (cmd == "CMD:STOP") {
      stopMotors();

      // ── Speed control: CMD:SPEED:<0-255> ──────────────────────────────────
      // Example: CMD:SPEED:150 sets motors to ~59% power (good for FF-130 on
      // 5V)
      //          CMD:SPEED:220 sets to ~86% (good for FF-130 on 5V with load)
      //          CMD:SPEED:100 gentle / safe for testing on 12V
    } else if (cmd.startsWith("CMD:SPEED:")) {
      int spd = cmd.substring(10).toInt();
      motorSpeed = constrain(spd, 0, 255);
      Serial.printf("[SPEED] Motor speed set to %d/255 (%.0f%%)\n", motorSpeed,
                    motorSpeed * 100.0 / 255.0);

    } else if (cmd.startsWith("ARM:PICK_TARGET:")) {
      // Format: ARM:PICK_TARGET:<CLASS>:<DIR>:<MS>
      // Example: ARM:PICK_TARGET:BATTERY:LEFT:200
      //          ARM:PICK_TARGET:BATTERY:RIGHT:150
      //          ARM:PICK_TARGET:BATTERY:CENTER:0
      String rest = cmd.substring(16);
      int c1 = rest.indexOf(':');
      if (c1 > 0) {
        String item = rest.substring(0, c1);
        String remain = rest.substring(c1 + 1);
        int c2 = remain.indexOf(':');
        if (c2 > 0) {
          String dir = remain.substring(0, c2);
          int offsetMs = remain.substring(c2 + 1).toInt();
          executeSmartTargetPickSequence(item, dir, offsetMs);
        } else {
          executeSmartTargetPickSequence(item, "CENTER", 0);
        }
      } else {
        executePickSequence(rest);
      }
    } else if (cmd.startsWith("ARM:PICK:")) {
      String itemType = cmd.substring(9);
      executePickSequence(itemType);
    } else if (cmd == "ARM:HOME") {
      armHome();
    } else if (cmd.startsWith("ARM:CALIB:180:")) {
      int ms = cmd.substring(14).toInt();
      if (ms > 100 && ms < 10000) {
        binRear180Ms = ms;
        Serial.printf("[CALIB] binRear180Ms set to %d ms\n", binRear180Ms);
      }
    } else if (cmd.startsWith("ARM:SERVO:")) {
      // Format: ARM:SERVO:<channel>:<value>
      // CH0 (360° base): value = speed (-100..+100),  0=stop
      // CH1-CH5 (positional): value = angle (0..180 degrees)
      int firstColon = cmd.indexOf(':', 10);
      if (firstColon > 0) {
        int ch = cmd.substring(10, firstColon).toInt();
        int val = cmd.substring(firstColon + 1).toInt();
        if (ch == 0) {
          // 360° continuous base — val is speed, NOT angle!
          baseSetSpeed(val);
        } else {
          setServoAngle(ch, val);
        }
      }

    } else if (cmd.startsWith("ARM:BASE:")) {
      // Timed base rotation: ARM:BASE:CW:<speed>:<durationMs>
      //                      ARM:BASE:CCW:<speed>:<durationMs>
      //                      ARM:BASE:STOP
      // Example: ARM:BASE:CW:60:1000  (rotate CW at 60% for 1 second)
      if (cmd == "ARM:BASE:STOP") {
        baseStop();
      } else {
        // parse ARM:BASE:<DIR>:<speed>:<ms>
        String rest = cmd.substring(9); // "CW:60:1000" or "CCW:60:1000"
        int c1 = rest.indexOf(':');
        if (c1 > 0) {
          String dir = rest.substring(0, c1);     // "CW" or "CCW"
          String remain = rest.substring(c1 + 1); // "60:1000"
          int c2 = remain.indexOf(':');
          if (c2 > 0) {
            int spd = remain.substring(0, c2).toInt(); // 60
            int ms = remain.substring(c2 + 1).toInt(); // 1000
            if (dir == "CW")
              baseRotateCW(spd, ms);
            else
              baseRotateCCW(spd, ms);
          } else {
            // Only speed given: ARM:BASE:CW:60 (continuous, no auto-stop)
            int spd = remain.toInt();
            if (dir == "CW")
              baseSetSpeed(spd);
            else
              baseSetSpeed(-spd);
          }
        }
      }
    } else if (cmd == "CMD:TELEMETRY" || cmd == "CMD:GET_SENSORS") {
      sendTelemetry();
    } else if (cmd == "CMD:I2C_SCAN") {
      Wire.beginTransmission(0x40);
      byte err = Wire.endTransmission();
      char res[64];
      if (err == 0) {
        snprintf(res, sizeof(res), "I2C_STATUS:PCA9685_FOUND_AT_0x40");
      } else {
        snprintf(res, sizeof(res), "I2C_STATUS:FAILED_CODE_%d", err);
      }
      udp.beginPacket(clientIP, clientPort);
      udp.print(res);
      udp.endPacket();
    }
  }

  // Safety Watchdog
  if (millis() - lastPacketTime > SAFETY_TIMEOUT_MS) {
    if (isDrivingForward) {
      stopMotors();
    }
  }
}