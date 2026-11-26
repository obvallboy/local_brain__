"""One-time Brain setup for this computer: download the models into ./models and calibrate them.

Usage (from anywhere):
  python brain_setup.py                    # 3B chat model + embedding model, calibrated on the CPU
  python brain_setup.py --gpu-layers -1    # calibrate on an NVIDIA GPU (faster)
  python brain_setup.py --size 1.5b        # the smaller chat model
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "file-cabinet"))

from filecabinet.fetch import main  # noqa: E402

if __name__ == "__main__":
    if "--dest" not in sys.argv:
        sys.argv += ["--dest", os.path.join(ROOT, "models")]  # where the Device Integrator looks
    main()
