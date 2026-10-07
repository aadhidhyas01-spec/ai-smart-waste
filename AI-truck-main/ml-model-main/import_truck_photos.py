"""
Import & Annotate Truck Photos from Disk
========================================
Have photos taken with your phone or camera of the truck and waste?
Drop your JPG/PNG files into the 'truck_photos/' folder and run this script!
- Displays each photo with automatic AI bounding-box suggestions
- Click-and-drag mouse to adjust or draw new bounding boxes
- Hit [SPACE] to approve and inject into YOLO dataset (train & valid sets)
- Hit [S] to skip an image
"""

import os
import sys
import shutil
import time
import argparse
from pathlib import Path
import cv2
import numpy as np
from ultralytics import YOLO

ROOT_DIR = Path(__file__).resolve().parent
PHOTOS_DIR = ROOT_DIR / "truck_photos"
TRAIN_IMG = ROOT_DIR / "train" / "images"
TRAIN_LBL = ROOT_DIR / "train" / "labels"
VALID_IMG = ROOT_DIR / "valid" / "images"
VALID_LBL = ROOT_DIR / "valid" / "labels"

PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
for p in [TRAIN_IMG, TRAIN_LBL, VALID_IMG, VALID_LBL]:
    p.mkdir(parents=True, exist_ok=True)

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
    ord('2'): 2,   # cardboard
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
        manual_box = None

def main():
    parser = argparse.ArgumentParser(description="Annotate & import offline truck photos into dataset")
    parser.add_argument("--folder", type=str, default=str(PHOTOS_DIR), help="Folder containing photo files")
    args = parser.parse_args()

    photo_dir = Path(args.folder)
    valid_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = [p for p in photo_dir.iterdir() if p.suffix.lower() in valid_exts]

    if not images:
        print("\n" + "=" * 70)
        print(f"  📁 No images found in: {photo_dir.resolve()}")
        print("  Place your photo files (.jpg / .png) into this folder and run again!")
        print("=" * 70 + "\n")
        return

    print("\n" + "=" * 70)
    print(f"  📸 FOUND {len(images)} PHOTOS IN {photo_dir.name}/")
    print("=" * 70)
    print("  Controls:")
    print("    [SPACE] or [ENTER] : Save image & label into dataset")
    print("    [S]                : Skip this image")
    print("    [1..9, 0, T]       : Switch Target Waste Class")
    print("    [Click & Drag]     : Draw bounding box around waste object")
    print("    [Right Click]      : Clear custom box")
    print("    [Q] or [ESC]       : Quit")
    print("=" * 70 + "\n")

    weights_path = ROOT_DIR / "weights" / "best_trash_yolov8m.pt"
    if not weights_path.exists():
        weights_path = "yolov8m.pt"
    try:
        model = YOLO(str(weights_path))
    except Exception:
        model = YOLO("yolov8n.pt")

    win_name = "Truck Photo Annotator"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_name, 1024, 768)
    cv2.setMouseCallback(win_name, mouse_callback)

    global manual_box
    current_class_id = 2  # default cardboard
    imported_count = 0

    for idx, img_path in enumerate(images, 1):
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue

        h, w = frame.shape[:2]
        manual_box = None

        # Auto detection suggestion
        detected_box = None
        suggested_class_id = current_class_id
        try:
            results = model(frame, verbose=False, conf=0.25)[0]
            for b in results.boxes:
                cid = int(b.cls[0])
                if detected_box is None:
                    detected_box = b.xywhn[0].tolist()
                    if cid in range(len(CLASSES)):
                        suggested_class_id = cid
        except Exception:
            pass

        class_id_for_this = suggested_class_id

        # Annotation loop for this single image
        while True:
            display = frame.copy()

            # Draw AI suggestion in green if exists
            if detected_box is not None and manual_box is None:
                bx, by, bw, bh = detected_box
                x1 = int((bx - bw / 2) * w)
                y1 = int((by - bh / 2) * h)
                x2 = int((bx + bw / 2) * w)
                y2 = int((by + bh / 2) * h)
                cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 120), 2)
                cv2.putText(display, f"SUGGESTION: {CLASSES[class_id_for_this].upper()}", (x1, max(20, y1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 120), 2)

            # Draw manual box if user dragged
            if drawing and ix != -1 and rx != -1:
                cv2.rectangle(display, (ix, iy), (rx, ry), (0, 0, 255), 2)
            elif manual_box is not None:
                mx1, my1, mx2, my2 = manual_box
                cv2.rectangle(display, (mx1, my1), (mx2, my2), (255, 0, 255), 2)
                cv2.putText(display, f"BOX: {CLASSES[class_id_for_this].upper()}", (mx1, max(20, my1 - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)

            # Top Header Bar
            cv2.rectangle(display, (0, 0), (w, 60), (25, 25, 25), -1)
            cv2.putText(display, f"[{idx}/{len(images)}] {img_path.name} | CLASS: [{class_id_for_this}] {CLASSES[class_id_for_this].upper()}",
                        (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(display, "Press [SPACE] to Save, [S] to Skip, [1..9, 0, T] to change class, [Drag Mouse] to box",
                        (15, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (200, 200, 200), 1)

            cv2.imshow(win_name, display)
            key = cv2.waitKey(20) & 0xFF

            if key in [ord('q'), 27]:
                cv2.destroyAllWindows()
                print(f"\nExited. Imported {imported_count} photos.")
                return

            if key in KEY_TO_CLASS:
                class_id_for_this = KEY_TO_CLASS[key]

            elif key == ord('s'):
                print(f"⏩ Skipped: {img_path.name}")
                break

            elif key in [ord(' '), 13]:  # SPACE or ENTER
                final_box = None
                if manual_box is not None:
                    mx1, my1, mx2, my2 = manual_box
                    bw = (mx2 - mx1) / w
                    bh = (my2 - my1) / h
                    bx = (mx1 + mx2) / (2 * w)
                    by = (my1 + my2) / (2 * h)
                    final_box = (bx, by, bw, bh)
                elif detected_box is not None:
                    final_box = detected_box
                else:
                    final_box = (0.5, 0.5, 0.6, 0.6)

                # Save into dataset (80% train, 20% valid)
                is_val = (imported_count % 5 == 0)
                dest_img_dir = VALID_IMG if is_val else TRAIN_IMG
                dest_lbl_dir = VALID_LBL if is_val else TRAIN_LBL

                stem = f"imported_truck_{CLASSES[class_id_for_this].replace(' ', '_')}_{int(time.time()*1000)}"
                cv2.imwrite(str(dest_img_dir / f"{stem}.jpg"), frame)
                bx, by, bw, bh = final_box
                with open(dest_lbl_dir / f"{stem}.txt", "w") as f:
                    f.write(f"{class_id_for_this} {bx:.6f} {by:.6f} {bw:.6f} {bh:.6f}\n")

                split_str = "VALID" if is_val else "TRAIN"
                print(f"✅ Imported [{CLASSES[class_id_for_this].upper()}] -> {split_str}: {stem}.jpg")
                imported_count += 1
                break

    cv2.destroyAllWindows()
    print("\n" + "=" * 70)
    print("  IMPORT COMPLETE")
    print(f"  Successfully imported & labeled {imported_count} images into dataset!")
    print("  Ready to train: Run train_truck_model.bat")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
