"""
YOLOv8 Maximum Accuracy Training Script
Dataset: yolov8-trash-detections (10 classes)
Strategy: YOLOv8m + augmentation + optimized for Windows
NOTE: All code inside if __name__ == "__main__" for Windows multiprocessing.
"""

import argparse
import os
import shutil
import time
from pathlib import Path
import torch
from ultralytics import YOLO


def play_completion_alert():
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1200, 200)
            winsound.Beep(1800, 250)
            time.sleep(0.1)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="YOLOv8 Maximum Accuracy Training")
    parser.add_argument("--epochs", type=int, default=30, help="Number of epochs to train (default: 30)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--base", type=str, default=None, help="Base weights file")
    parser.add_argument("--patience", type=int, default=25, help="Early stopping patience (default: 25)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size (default: 640)")
    args = parser.parse_args()

    # --- Paths ---
    SCRIPT_DIR  = Path(__file__).resolve().parent
    DATA_YAML   = str(SCRIPT_DIR / "data.yaml")
    PROJECT_DIR = str(SCRIPT_DIR / "runs" / "detect")
    EXPERIMENT  = "trash_max_accuracy"

    # --- Detect best device ---
    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_name(0)
        device = "0"
        print(f"[OK] CUDA GPU detected: {gpu}")
        batch_size = args.batch
        workers    = 2
    else:
        device     = "cpu"
        batch_size = 4
        workers    = 0
        print("[WARN] No GPU found. Training on CPU.")

    # --- Validate dataset ---
    if not os.path.exists(DATA_YAML):
        raise FileNotFoundError(f"data.yaml not found at '{DATA_YAML}'")

    # --- Model selection: prioritize existing trained trash weights ---
    if args.base:
        BASE_MODEL = args.base
    else:
        existing_best = SCRIPT_DIR / "weights" / "best_trash_yolov8m.pt"
        if existing_best.exists():
            BASE_MODEL = str(existing_best)
        elif (SCRIPT_DIR / "yolov8m.pt").exists():
            BASE_MODEL = str(SCRIPT_DIR / "yolov8m.pt")
        else:
            BASE_MODEL = "yolov8m.pt"

    print("\n" + "=" * 65)
    print("  🚀 YOLOv8m - Maximum Accuracy Training Engine")
    print("=" * 65)
    print(f"  Base Weights: {BASE_MODEL}")
    print(f"  Data Config : {DATA_YAML}")
    print(f"  Epochs      : {args.epochs}")
    print(f"  Batch Size  : {batch_size}  |  Workers: {workers}")
    print(f"  Resolution  : {args.imgsz}x{args.imgsz}")
    print(f"  Device      : {device}")
    print(f"  Output      : {PROJECT_DIR}/{EXPERIMENT}")
    print("=" * 65 + "\n")

    # --- Load model ---
    model = YOLO(BASE_MODEL)

    # --- TRAINING ---
    print("[1/3] Starting high-accuracy training...\n")
    results = model.train(
        # Core
        data        = DATA_YAML,
        epochs      = args.epochs,
        batch       = batch_size,
        imgsz       = args.imgsz,
        device      = device,
        workers     = workers,
        # Output
        project     = PROJECT_DIR,
        name        = EXPERIMENT,
        exist_ok    = True,
        save_period = 5,
        # LR schedule
        optimizer     = "AdamW",
        lr0           = 0.0008,
        lrf           = 0.01,
        cos_lr        = True,
        warmup_epochs = 3,
        # Loss weighting for tight boxes and strong class discrimination
        box           = 7.5,
        cls           = 1.2,
        dfl           = 1.5,
        # Regularisation
        weight_decay  = 0.0005,
        dropout       = 0.1,
        # Early stopping
        patience      = args.patience,
        # Augmentation
        hsv_h         = 0.015,
        hsv_s         = 0.7,
        hsv_v         = 0.4,
        degrees       = 10.0,
        translate     = 0.1,
        scale         = 0.5,
        shear         = 2.0,
        perspective   = 0.0005,
        flipud        = 0.05,
        fliplr        = 0.5,
        mosaic        = 1.0,
        mixup         = 0.15,
        copy_paste    = 0.25,
        close_mosaic  = 10,
        cache         = False,
        verbose       = True,
        plots         = True,
    )

    # --- Validation ---
    print("\n[2/3] Running final validation on best weights...\n")
    best_weights_path = Path(results.save_dir) / "weights" / "best.pt"
    if not best_weights_path.exists():
        best_weights_path = Path(results.save_dir) / "weights" / "last.pt"

    eval_model = YOLO(str(best_weights_path))
    val_results = eval_model.val(
        data   = DATA_YAML,
        split  = "val",
        imgsz  = args.imgsz,
        device = device,
        plots  = True,
    )

    # --- Backup & Copy best weights to /weights/ ---
    dest_folder = SCRIPT_DIR / "weights"
    dest_folder.mkdir(exist_ok=True)
    dest_best   = dest_folder / "best_trash_yolov8m.pt"
    backup_best = dest_folder / "best_trash_yolov8m.pt.bak"

    if best_weights_path.exists():
        if dest_best.exists():
            shutil.copy2(dest_best, backup_best)
            print(f"[Backup] Saved original weights backup to: {backup_best}")
        shutil.copy2(best_weights_path, dest_best)
        print(f"\n[3/3] Newly trained best weights copied to: {dest_best}")
    else:
        print(f"\n[3/3] WARNING: Could not find weights at {best_weights_path}")

    # --- Summary ---
    print("\n" + "=" * 65)
    print("  TRAINING COMPLETE - RESULTS SUMMARY")
    print("=" * 65)
    try:
        maps = val_results.box
        print(f"  mAP50       : {maps.map50:.4f}  ({maps.map50*100:.2f}%)")
        print(f"  mAP50-95    : {maps.map:.4f}  ({maps.map*100:.2f}%)")
        print(f"  Precision   : {maps.mp:.4f}  ({maps.mp*100:.2f}%)")
        print(f"  Recall      : {maps.mr:.4f}  ({maps.mr*100:.2f}%)")
    except Exception:
        pass
    print(f"\n  Best weights  : {dest_best}")
    print(f"  Run directory : {results.save_dir}")
    print("=" * 65)

    play_completion_alert()


if __name__ == "__main__":
    main()

