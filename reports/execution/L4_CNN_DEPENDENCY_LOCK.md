# L4 CNN dependency lock

Status: PASS dependency readiness; L4 remains `IN_PROGRESS`.

A dedicated local Python 3.12 environment is available at
`work/toolchain/cnn_py312`. It uses the machine's pinned torch installation and
installs torchvision locally, without modifying the project Python 3.14 EDA
environment. Verified versions are Python 3.12.7, torch 2.9.1+cu128,
torchvision 0.24.1+cu128, NumPy 1.26.4 and pytest 7.4.4. Native torchvision ops
load successfully.

Official `IMAGENET1K_V2` artifacts were downloaded through torchvision with
`check_hash=True`:

- ResNet50: 102,540,417 bytes, SHA256
  `11ad3fa62ca79e40addfd354a8ec4b7c75143b3038b8d2a807fbc68deab379ca`.
- MobileNetV2: 14,258,573 bytes, SHA256
  `7ebf99e03e254b273379b23edca7ec0da9f48273b23a332b93c1c99d49e86e8f`.

The environment and weight files are ignored build inputs. Only the lock,
URLs, sizes, hashes and verifier are tracked. This does not close any L4
numerical or RTL subgate.
