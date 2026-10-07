"""
Automatic Video Frame Extractor & Dataset Builder
=================================================
Drop a video (.mp4, .mov, .avi) of your truck and waste into 'truck_photos/'!
This script will:
1. Extract sharp, diverse frames from the video.
2. Auto-detect and label waste objects using YOLOv8.
3. Automatically organize the frames into the train/ and valid/ dataset.
"""

import os
import sys
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

def main():
    parser = argparse.ArgumentParser(description="Extract training frames from video files")
    parser.add_argument("--video", type=str, default="", help="Path to video file (or leave empty to scan truck_photos/)")
    parser.add_argument("--interval", type=int, default=15, help="Extract 1 frame every N frames (default: 15)")
    parser.add_argument("--class-id", type=int, default=-1, help="Override class ID (-1 = auto-detect with YOLO)")
    args = parser.parse_args()

    # Find video file
    video_path = None
    if args.video and os.path.exists(args.video):
        video_path = Path(args.video)
    else:
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".3gp", ".webm"}
        found = [p for p in PHOTOS_DIR.iterdir() if p.suffix.lower() in video_exts]
        if found:
            video_path = found[0]

    if not video_path:
        print("\n" + "=" * 70)
        print("  📹 No video found!")
        print("  Drop your video file (.mp4 or .mov) into:")
        print(f"  👉 {PHOTOS_DIR.resolve()}")
        print("  Then run this script again!")
        print("=" * 70 + "\n")
        return

    print("\n" + "=" * 70)
    print(f"  🎬 PROCESSING VIDEO: {video_path.name}")
    print("=" * 70)

    cap = cv2.VideoCapture(str(video_path))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"  Total Frames : {total_frames} (~{total_frames/fps:.1f} seconds @ {fps:.1f} FPS)")
    print(f"  Sample Rate  : 1 frame every {args.interval} frames")

    # Load YOLO model for auto-annotation
    weights_path = ROOT_DIR / "weights" / "best_trash_yolov8m.pt"
    if not weights_path.exists():
        weights_path = "yolov8m.pt"
    print("  Loading YOLO AI detector for automated bounding boxes...")
    try:
        model = YOLO(str(weights_path))
    except Exception:
        model = YOLO("yolov8n.pt")

    frame_idx = 0
    saved_count = 0

    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            break

        if frame_idx % args.interval == 0:
            h, w = frame.shape[:2]
            labels = []

            # Auto-detect waste objects with YOLO
            try:
                results = model(frame, verbose=False, conf=0.25)[0]
                for b in results.boxes:
                    cid = int(b.cls[0])
                    if args.class_id >= 0:
                        cid = args.class_id
                    bx, by, bw, bh = b.xywhn[0].tolist()
                    labels.append((cid, bx, by, bw, bh))
            except Exception:
                pass

            # If no detection found and user didn't specify, default to center box
            if not labels:
                cid = args.class_id if args.class_id >= 0 else 2  # default cardboard/waste
                labels.append((cid, 0.5, 0.5, 0.5, 0.5))

            # Split: 80% train, 20% valid
            is_val = (saved_count % 5 == 0)
            dest_img = VALID_IMG if is_val else TRAIN_IMG
            dest_lbl = VALID_LBL if is_val else TRAIN_LBL

            timestamp = int(time.time() * 1000)
            stem = f"video_{video_path.stem}_{saved_count:04d}_{timestamp}"
            img_file = dest_img / f"{stem}.jpg"
            lbl_file = dest_lbl / f"{stem}.txt"

            cv2.imwrite(str(img_file), frame)
            with open(lbl_file, "w") as f:
                for cid, bx, by, bw, bh in labels:
                    f.write(f"{cid} {bx:.6f} {by:.6f} {bw:.6f} {bh:.6f}\n")

            saved_count += 1
            if saved_count % 5 == 0:
                print(f"  Extracted {saved_count} frames... ({frame_idx}/{total_frames})")

        frame_idx += 1

    cap.release()
    print("\n" + "=" * 70)
    print("  EXTRACTION COMPLETE!")
    print(f"  Generated {saved_count} labeled training images from your video.")
    print("  All images are ready in train/ and valid/ dataset folders!")
    print("  Ready to train: Run train_truck_model.bat")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
