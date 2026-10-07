"""
Fine-Tune YOLOv8 Model with Real Truck Camera Pictures
======================================================
Takes the pre-trained waste detection model and fine-tunes it with the newly
captured truck pictures, adapting to your exact room lighting, camera lens, and waste items.

- Automatic CPU / GPU hardware optimization
- Safe on Windows (workers=0, prevents multiprocessing deadlocks)
- Automatically updates weights/best_trash_yolov8m.pt when finished
- Sounds an audio alert upon completion
"""

import os
import sys
import shutil
import time
import argparse
from pathlib import Path
import torch
from ultralytics import YOLO

ROOT_DIR = Path(__file__).resolve().parent
DATA_YAML = str(ROOT_DIR / "data.yaml")
WEIGHTS_DIR = ROOT_DIR / "weights"
DEST_MODEL = WEIGHTS_DIR / "best_trash_yolov8m.pt"
BACKUP_MODEL = WEIGHTS_DIR / "best_trash_yolov8m.pt.bak"
PROJECT_DIR = str(ROOT_DIR / "runs" / "detect")
RUN_NAME = "truck_finetuned"

def play_alert():
    """Play notification sound when training finishes."""
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 200)
            winsound.Beep(1500, 250)
            time.sleep(0.1)
    except Exception:
        pass

def main():
    parser = argparse.ArgumentParser(description="Fine-tune YOLO model with real truck camera photos")
    parser.add_argument("--epochs", type=int, default=20, help="Number of fine-tuning epochs (default: 20)")
    parser.add_argument("--batch", type=int, default=0, help="Batch size (0 = auto-detect based on device)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image resolution (default: 640)")
    parser.add_argument("--base", type=str, default=str(DEST_MODEL), help="Base weights path")
    args = parser.parse_args()

    # Hardware detection
    if torch.cuda.is_available():
        device = "0"
        device_name = torch.cuda.get_device_name(0)
        batch_size = 12 if args.batch == 0 else args.batch
        workers = 0  # Safe on Windows
        print(f"🚀 [Hardware] GPU Acceleration Enabled: {device_name}")
    else:
        device = "cpu"
        device_name = "CPU (Intel / AMD)"
        batch_size = 4 if args.batch == 0 else args.batch
        workers = 0  # Crucial on Windows to avoid process spawn deadlocks
        print("💻 [Hardware] Training on CPU (Optimized with batch=4, workers=0)")

    # Verify base weights
    base_weights = args.base
    if not os.path.exists(base_weights):
        alt_base = ROOT_DIR / "yolov8m.pt"
        if alt_base.exists():
            base_weights = str(alt_base)
        else:
            base_weights = "yolov8m.pt"

    print("\n" + "=" * 70)
    print("  🚛 FINE-TUNING YOLOV8 WITH REAL TRUCK PICTURES 🚛")
    print("=" * 70)
    print(f"  Base Model       : {base_weights}")
    print(f"  Dataset Config   : {DATA_YAML}")
    print(f"  Epochs           : {args.epochs}")
    print(f"  Batch Size       : {batch_size}")
    print(f"  Image Size       : {args.imgsz}")
    print(f"  Compute Device   : {device} ({device_name})")
    print(f"  Output Run       : {PROJECT_DIR}/{RUN_NAME}")
    print("=" * 70 + "\n")

    # Load base model for transfer learning
    print("[1/3] Loading base model weights...")
    model = YOLO(base_weights)

    # Train
    print(f"\n[2/3] Training for {args.epochs} epochs with truck photos included...")
    train_results = model.train(
        data=DATA_YAML,
        epochs=args.epochs,
        batch=batch_size,
        imgsz=args.imgsz,
        device=device,
        workers=workers,
        project=PROJECT_DIR,
        name=RUN_NAME,
        exist_ok=True,
        lr0=0.001,       # Lower learning rate for gentle fine-tuning
        lrf=0.01,
        cos_lr=True,
        warmup_epochs=2,
        box=8.5,          # Strong bounding box precision for millimeter arm alignment
        dfl=1.8,          # Distribution focal loss for fine boundary accuracy
        cls=1.2,
        patience=15,
        save_period=5,
        verbose=True,
        plots=True
    )

    # Validate
    print("\n[3/3] Evaluating accuracy metrics on validation set...")
    val_results = model.val(data=DATA_YAML, split="val", imgsz=args.imgsz, device=device)

    # Deploy best weights automatically
    save_dir = Path(train_results.save_dir) if hasattr(train_results, 'save_dir') else Path(PROJECT_DIR) / RUN_NAME
    best_weights = save_dir / "weights" / "best.pt"

    if best_weights.exists():
        WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
        # Create backup if original exists
        if DEST_MODEL.exists():
            try:
                shutil.copy2(DEST_MODEL, BACKUP_MODEL)
                print(f"📦 Backed up previous model to: {BACKUP_MODEL.name}")
            except Exception:
                pass

        # Copy new best weights
        shutil.copy2(best_weights, DEST_MODEL)
        print(f"\n✅ SUCCESS: New fine-tuned model deployed to: {DEST_MODEL.resolve()}")
    else:
        print(f"\n⚠️ Notice: weights/best.pt not found at {best_weights}")

    # Display Metrics Summary
    print("\n" + "=" * 70)
    print("  FINE-TUNING COMPLETE - VALIDATION RESULTS")
    print("=" * 70)
    try:
        maps = val_results.box
        print(f"  Overall Precision (P) : {maps.mp*100:6.2f}%")
        print(f"  Overall Recall    (R) : {maps.mr*100:6.2f}%")
        print(f"  mAP @ 0.50            : {maps.map50*100:6.2f}%")
        print(f"  mAP @ 0.50:0.95       : {maps.map*100:6.2f}%")
    except Exception as e:
        print(f"  Metrics read: {e}")
    print("=" * 70)
    print("  Your robot truck controller (robot_wireless_controller.py)")
    print("  is now configured to use the newly fine-tuned model!")
    print("=" * 70 + "\n")

    play_alert()

if __name__ == "__main__":
    main()
