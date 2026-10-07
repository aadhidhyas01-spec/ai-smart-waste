"""
Interactive Truck Camera Dataset Collector & Live Annotator
============================================================
Collect real-world training samples directly from your Robot Truck's ESP32-CAM!
- Real-time video stream from ESP32-CAM (http://192.168.137.234:81/stream) or webcam
- Live YOLO detection preview + Click-and-Drag manual bounding box
- One-key capture directly into train/ and valid/ dataset folders
- Supports all 11 waste categories with instant hotkeys
"""

import os
import sys
import time
import socket
import argparse
import threading
from pathlib import Path
import cv2
import numpy as np
import torch
from ultralytics import YOLO

ROOT_DIR = Path(__file__).resolve().parent
TRAIN_IMG = ROOT_DIR / "train" / "images"
TRAIN_LBL = ROOT_DIR / "train" / "labels"
VALID_IMG = ROOT_DIR / "valid" / "images"
VALID_LBL = ROOT_DIR / "valid" / "labels"

for p in [TRAIN_IMG, TRAIN_LBL, VALID_IMG, VALID_LBL]:
    p.mkdir(parents=True, exist_ok=True)

# 11 Waste Classes matching data.yaml
CLASSES = [
    "battery",             # 0
    "can",                 # 1
    "cardboard",           # 2
    "drink carton",        # 3
    "glass bottle",        # 4
    "paper",               # 5
    "plastic bag",         # 6
    "plastic bottle",      # 7
    "plastic bottle cap",  # 8
    "pop tab",             # 9
    "cup"                  # 10
]

KEY_TO_CLASS = {
    ord('1'): 1,   # can
    ord('2'): 2,   # cardboard (Amazon box)
    ord('3'): 7,   # plastic bottle
    ord('4'): 10,  # cup
    ord('5'): 5,   # paper
    ord('6'): 6,   # plastic bag
    ord('7'): 4,   # glass bottle
    ord('8'): 8,   # plastic bottle cap
    ord('9'): 0,   # battery
    ord('0'): 3,   # drink carton
    ord('t'): 9,   # pop tab
}

# Mouse callback state for drawing boxes
drawing = False
ix, iy = -1, -1
rx, ry = -1, -1
manual_box = None

def mouse_callback(event, x, y, flags, param):
    global ix, iy, rx, ry, drawing, manual_box
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        ix, iy = x, y
        rx, ry = x, y
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            rx, ry = x, y
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        rx, ry = x, y
        x1, y1 = min(ix, rx), min(iy, ry)
        x2, y2 = max(ix, rx), max(iy, ry)
        if (x2 - x1) > 15 and (y2 - y1) > 15:
            manual_box = (x1, y1, x2, y2)
    elif event == cv2.EVENT_RBUTTONDOWN:
        # Right click to clear manual box
        manual_box = None

class SmartStreamCapture:
    """Threaded zero-latency MJPEG stream receiver with auto-reconnection."""
    def __init__(self, source_str: str):
        self.source_str = source_str
        self.is_http = str(source_str).startswith("http://") or str(source_str).startswith("https://")
        self.cap = None
        self.latest_frame = None
        self.stopped = False
        self.lock = threading.Lock()

        if not self.is_http:
            src = int(source_str) if str(source_str).isdigit() else source_str
            self.cap = cv2.VideoCapture(src)
            if self.cap is not None:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        else:
            self.thread = threading.Thread(target=self._stream_worker, daemon=True)
            self.thread.start()

    def _stream_worker(self):
        import urllib.request
        while not self.stopped:
            stream = None
            try:
                req = urllib.request.Request(self.source_str, headers={'User-Agent': 'Mozilla/5.0'})
                stream = urllib.request.urlopen(req, timeout=5.0)
                bytes_buf = b""
                while not self.stopped:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    bytes_buf += chunk
                    a = bytes_buf.find(b'\xff\xd8')
                    b = bytes_buf.find(b'\xff\xd9')
                    if a != -1 and b != -1:
                        jpg = bytes_buf[a:b+2]
                        bytes_buf = bytes_buf[b+2:]
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            with self.lock:
                                self.latest_frame = frame
            except Exception as e:
                time.sleep(1.0)
            finally:
                if stream:
                    try:
                        stream.close()
                    except Exception:
                        pass

    def read(self):
        if self.is_http:
            with self.lock:
                if self.latest_frame is not None:
                    return True, self.latest_frame.copy()
            return False, None
        else:
            if self.cap and self.cap.isOpened():
                return self.cap.read()
            return False, None

    def release(self):
        self.stopped = True
        if self.cap:
            self.cap.release()

def save_sample(frame, class_id: int, box_xywhn: tuple, sample_count: int):
    """Saves frame and label in YOLO format with 80/20 train/valid split."""
    is_val = (sample_count % 5 == 0)
    dest_img_dir = VALID_IMG if is_val else TRAIN_IMG
    dest_lbl_dir = VALID_LBL if is_val else TRAIN_LBL

    class_name = CLASSES[class_id]
    timestamp = int(time.time() * 1000)
    stem = f"truck_{class_name.replace(' ', '_')}_{timestamp}"
    img_path = dest_img_dir / f"{stem}.jpg"
    lbl_path = dest_lbl_dir / f"{stem}.txt"

    cv2.imwrite(str(img_path), frame)
    bx, by, bw, bh = box_xywhn
    with open(lbl_path, "w") as f:
        f.write(f"{class_id} {bx:.6f} {by:.6f} {bw:.6f} {bh:.6f}\n")

    split_str = "VALID" if is_val else "TRAIN"
    print(f"📸 Saved [{class_name.upper()}] (Class {class_id}) -> {split_str}: {img_path.name}")
    return split_str

def main():
    parser = argparse.ArgumentParser(description="Collect real truck camera samples for YOLO fine-tuning")
    parser.add_argument("--source", type=str, default="http://192.168.137.234:81/stream",
                        help="Camera URL (e.g. http://192.168.137.234:81/stream) or '0' for laptop webcam")
    args = parser.parse_args()

    # Load existing YOLO weights to assist with auto-bounding boxes
    weights_path = ROOT_DIR / "weights" / "best_trash_yolov8m.pt"
    if not weights_path.exists():
        weights_path = ROOT_DIR / "yolov8m.pt"
    if not weights_path.exists():
        weights_path = "yolov8m.pt"

    print("=" * 70)
    print("  🚛 TRUCK CAMERA DATASET COLLECTOR & ANNOTATOR 🚛")
    print("=" * 70)
    print(f"  Camera Source : {args.source}")
    print(f"  Base Model    : {weights_path}")
    print("  Controls:")
    print("    [SPACE] or [ENTER] : Capture photo & Save annotation")
    print("    [1..9, 0, T]       : Switch Target Waste Class")
    print("    [Click & Drag]     : Draw custom bounding box with mouse")
    print("    [Right Click]      : Clear custom box")
    print("    [Q] or [ESC]       : Finish and exit")
    print("=" * 70 + "\n")

    print("Loading AI assistant for auto-detection preview...")
    try:
        model = YOLO(str(weights_path))
    except Exception as e:
        print(f"Note: Using lightweight yolo fallback ({e})")
        model = YOLO("yolov8n.pt")

    cap = SmartStreamCapture(args.source)

    win_name = "Truck Camera Dataset Collector (Press Q to quit)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 960, 720)
    cv2.setMouseCallback(win_name, mouse_callback)

    current_class_id = 2  # Default to 'cardboard' (Amazon box)
    saved_count = 0
    class_counts = {i: 0 for i in range(len(CLASSES))}
    global manual_box

    flash_timer = 0
    flash_text = ""

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            # Render a connecting screen
            waiting = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(waiting, "Connecting to Truck Camera...", (100, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            cv2.putText(waiting, f"Source: {args.source}", (80, 280),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)
            cv2.imshow(win_name, waiting)
            if (cv2.waitKey(50) & 0xFF) in [ord('q'), 27]:
                break
            continue

        h, w = frame.shape[:2]
        display = frame.copy()

        # Run model to detect potential objects
        detected_box = None
        detected_label = ""
        try:
            results = model(frame, verbose=False, conf=0.30)[0]
            for b in results.boxes:
                cid = int(b.cls[0])
                name = model.names[cid] if hasattr(model, 'names') and cid in model.names else str(cid)
                conf = float(b.conf[0])
                x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]

                # Draw auto-detected objects in green/cyan
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 120), 2)
                cv2.putText(display, f"{name}: {conf:.2f}", (x1, max(15, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 120), 2)

                if detected_box is None:
                    detected_box = b.xywhn[0].tolist()
                    detected_label = name
        except Exception:
            pass

        # Draw manual box if user is dragging or set
        if drawing and ix != -1 and rx != -1:
            cv2.rectangle(display, (ix, iy), (rx, ry), (0, 0, 255), 2)
        elif manual_box is not None:
            mx1, my1, mx2, my2 = manual_box
            cv2.rectangle(display, (mx1, my1), (mx2, my2), (255, 0, 255), 2)
            cv2.putText(display, f"MANUAL BOX: {CLASSES[current_class_id].upper()}", (mx1, max(15, my1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 2)

        # Top Control Banner
        cv2.rectangle(display, (0, 0), (w, 65), (25, 25, 25), -1)
        cur_name = CLASSES[current_class_id].upper()
        cv2.putText(display, f"TARGET CLASS: [{current_class_id}] {cur_name}", (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
        cv2.putText(display, f"Total Captured: {saved_count} | This Class: {class_counts[current_class_id]}", (12, 54),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1)

        # Instructions / Shortcut Guide at bottom
        cv2.rectangle(display, (0, h - 30), (w, h), (20, 20, 20), -1)
        shortcuts = "[1]Can [2]Cardboard [3]PlasticBot [4]Cup [5]Paper [6]Bag [7]Glass [8]Cap [SPACE]Capture [Q]Quit"
        cv2.putText(display, shortcuts, (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (170, 220, 255), 1)

        # Flash alert when sample saved
        if flash_timer > 0:
            cv2.rectangle(display, (0, 0), (w, h), (0, 255, 0), 8)
            cv2.putText(display, flash_text, (w // 4, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 3)
            flash_timer -= 1

        cv2.imshow(win_name, display)
        key = cv2.waitKey(1) & 0xFF

        if key in [ord('q'), 27]:
            break

        # Class switching shortcuts
        if key in KEY_TO_CLASS:
            current_class_id = KEY_TO_CLASS[key]
            print(f"👉 Switched target class to: [{current_class_id}] {CLASSES[current_class_id]}")

        # Capture and save
        elif key in [ord(' '), 13]:  # SPACE or ENTER
            final_box = None
            if manual_box is not None:
                mx1, my1, mx2, my2 = manual_box
                bw = (mx2 - mx1) / w
                bh = (my2 - my1) / h
                bx = (mx1 + mx2) / (2 * w)
                by = (my1 + my2) / (2 * h)
                final_box = (bx, by, bw, bh)
                manual_box = None
            elif detected_box is not None:
                final_box = detected_box
            else:
                # Default centered region box (60% width, 50% height)
                final_box = (0.5, 0.55, 0.55, 0.45)
                print("ℹ️ Auto-box not locked. Saved center frame region. (Tip: drag mouse to set exact box)")

            split = save_sample(frame, current_class_id, final_box, saved_count)
            saved_count += 1
            class_counts[current_class_id] += 1
            flash_timer = 5
            flash_text = f"SAVED {CLASSES[current_class_id].upper()} ({split})"

        elif key == ord('c'):
            # Clear manual box
            manual_box = None

    cap.release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 70)
    print("  COLLECTION SUMMARY")
    print("=" * 70)
    print(f"  Total samples collected: {saved_count}")
    for cid, cnt in class_counts.items():
        if cnt > 0:
            print(f"   - {CLASSES[cid]:<20} : {cnt} images")
    print("=" * 70)
    print("  All photos have been added directly to your dataset.")
    print("  Next Step: Run train_truck_model.bat to train YOLO with your pictures!")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
