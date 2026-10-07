"""
YOLOv8 Training and Fine-Tuning Script
Dataset: yolov8-trash-detections
Classes: battery, can, cardboard, drink carton, glass bottle, paper, plastic bag, plastic bottle, plastic bottle cap, pop tab
"""

import os
import sys
import argparse
from pathlib import Path
import torch
from ultralytics import YOLO

# Root directory of this script / dataset
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_YAML = str(SCRIPT_DIR / "data.yaml")
DEFAULT_PROJECT = str(SCRIPT_DIR / "runs" / "detect")

def get_default_device() -> str:
    """Detect and return the best available compute device ('0' for CUDA GPU, 'cpu' otherwise)."""
    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        print(f"[Device] NVIDIA CUDA GPU detected: {gpu_name}")
        return "0"
    else:
        print("[Device] CUDA not available. Running on CPU.")
        return "cpu"

def train_model(
    data_yaml: str = DEFAULT_DATA_YAML,
    base_model: str = "yolov8n.pt",
    epochs: int = 60,
    batch_size: int = 16,
    imgsz: int = 640,
    device: str = None,
    project: str = DEFAULT_PROJECT,
    name: str = "trash_detection",
    lr0: float = 0.01,
    patience: int = 15,
    workers: int = 4,
    save_period: int = -1,
    exist_ok: bool = True
):
    """
    Finetune a YOLOv8 model on the trash detection dataset.
    
    Args:
        data_yaml: Path to data.yaml
        base_model: Initial weights ('yolov8n.pt', 'yolov8s.pt', or custom .pt path)
        epochs: Number of training epochs
        batch_size: Batch size (reduce if out of memory on GPU/CPU)
        imgsz: Target image resolution (default 640)
        device: '0', 'cpu', or None (auto-detect)
        project: Directory where training runs are saved
        name: Name for this training experiment run
        lr0: Initial learning rate
        patience: Early stopping patience epochs
        workers: DataLoader worker threads (set to 0 or 2 on Windows if issues occur)
        save_period: Save checkpoint every N epochs (-1 for disabled)
        exist_ok: Overwrite existing run directory if same name
    """
    if device is None:
        device = get_default_device()

    print("=" * 60)
    print(" YOLOv8 Model Fine-Tuning")
    print("=" * 60)
    print(f" Dataset YAML   : {data_yaml}")
    print(f" Base Model     : {base_model}")
    print(f" Epochs         : {epochs}")
    print(f" Batch Size     : {batch_size}")
    print(f" Image Size     : {imgsz}")
    print(f" Device         : {device}")
    print(f" Output Project : {project}/{name}")
    print("=" * 60)

    # Validate data.yaml existence
    if not os.path.exists(data_yaml):
        raise FileNotFoundError(f"data.yaml not found at '{data_yaml}'. Please check the path.")

    # Initialize model with base weights
    print(f"\n[1/3] Loading base model weights: {base_model}...")
    model = YOLO(base_model)

    # Adjust workers for Windows stability
    if os.name == 'nt' and workers > 2 and device == 'cpu':
        workers = 2

    # Start training
    print(f"\n[2/3] Starting training for {epochs} epochs...")
    train_results = model.train(
        data=data_yaml,
        epochs=epochs,
        batch=batch_size,
        imgsz=imgsz,
        device=device,
        project=project,
        name=name,
        lr0=lr0,
        cos_lr=True,
        mixup=0.1,
        patience=patience,
        workers=workers,
        save_period=save_period,
        exist_ok=exist_ok,
        verbose=True
    )

    # Evaluate validation metrics
    print("\n[3/3] Evaluating validation set metrics...")
    val_results = model.val(data=data_yaml, split="val", imgsz=imgsz, device=device)

    # Output paths
    save_dir = Path(train_results.save_dir) if hasattr(train_results, 'save_dir') else Path(project) / name
    best_weights = save_dir / "weights" / "best.pt"
    last_weights = save_dir / "weights" / "last.pt"

    print("\n" + "=" * 60)
    print(" Training Finished Successfully!")
    print("=" * 60)
    print(f" Best model weights : {best_weights.resolve()}")
    print(f" Last model weights : {last_weights.resolve()}")
    print(f" Experiment results : {save_dir.resolve()}")
    print("=" * 60)

    return model, train_results, val_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train / Finetune YOLOv8 for Trash Detection")
    parser.add_argument("--data", type=str, default=DEFAULT_DATA_YAML, help="Path to data.yaml")
    parser.add_argument("--model", type=str, default="yolov8n.pt", help="Base model weights (e.g. yolov8n.pt)")
    parser.add_argument("--epochs", type=int, default=60, help="Number of epochs (default: 60)")
    parser.add_argument("--batch", type=int, default=16, help="Batch size (default: 16)")
    parser.add_argument("--imgsz", type=int, default=640, help="Image resolution (default: 640)")
    parser.add_argument("--device", type=str, default=None, help="Device to use ('0' for GPU, 'cpu', or leave empty for auto)")
    parser.add_argument("--project", type=str, default=DEFAULT_PROJECT, help="Save directory")
    parser.add_argument("--name", type=str, default="trash_finetune", help="Experiment name")
    parser.add_argument("--workers", type=int, default=2, help="DataLoader workers")
    parser.add_argument("--lr0", type=float, default=0.01, help="Initial learning rate")

    args = parser.parse_args()

    train_model(
        data_yaml=args.data,
        base_model=args.model,
        epochs=args.epochs,
        batch_size=args.batch,
        imgsz=args.imgsz,
        device=args.device,
        project=args.project,
        name=args.name,
        lr0=args.lr0,
        workers=args.workers
    )
