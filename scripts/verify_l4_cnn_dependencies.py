#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "config/l4_cnn_python.lock.json").read_text())

import numpy
import pytest
import torch
import torchvision
from torchvision.models import MobileNet_V2_Weights, ResNet50_Weights

actual = {
    "python": sys.version.split()[0],
    "torch": torch.__version__,
    "torchvision": torchvision.__version__,
    "numpy": numpy.__version__,
    "pytest": pytest.__version__,
}
expected = {"python": LOCK["python"], **LOCK["packages"]}
if actual != expected:
    raise SystemExit(f"L4_CNN_DEPENDENCY_FAIL versions actual={actual} expected={expected}")

urls = {
    "resnet50_imagenet1k_v2": ResNet50_Weights.IMAGENET1K_V2.url,
    "mobilenet_v2_imagenet1k_v2": MobileNet_V2_Weights.IMAGENET1K_V2.url,
}
for name, entry in LOCK["weights"].items():
    path = Path(entry["cache_path"])
    if urls[name] != entry["url"] or not path.is_file() or path.stat().st_size != entry["bytes"]:
        raise SystemExit(f"L4_CNN_DEPENDENCY_FAIL artifact={name}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(f"L4_CNN_DEPENDENCY_FAIL sha256={name}:{digest}")

if not hasattr(torch.ops.torchvision, "nms"):
    raise SystemExit("L4_CNN_DEPENDENCY_FAIL torchvision_native_ops")
print("L4_CNN_DEPENDENCY_PASS weights=2 native_ops=1")
