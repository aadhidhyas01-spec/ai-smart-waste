import os
import sys
import subprocess
from pathlib import Path

# Forward to the actual script in AI-truck-main/ml-model-main
target_dir = Path(__file__).resolve().parent / "AI-truck-main" / "ml-model-main"
script_path = target_dir / "test_devkit_control.py"

if not script_path.exists():
    print(f"Error: Could not find target script at {script_path}")
    sys.exit(1)

os.chdir(str(target_dir))
cmd = [sys.executable, str(script_path)] + sys.argv[1:]
subprocess.run(cmd)
