# CSRNet Pretrained Checkpoints (ShanghaiTech Part B)

This directory stores pretrained deep-learning weights for the CSRNet crowd-counting model.

## 1. Verified Checkpoint Sources

| Checkpoint | Target Crowd Density | Source Repository / Link | File Name |
| :--- | :--- | :--- | :--- |
| **ShanghaiTech Part B (Default Production)** | Sparse-to-medium crowds (fixed Gaussian kernel $\sigma=15$) | [rootstrap-org/crowd-counting](https://huggingface.co/rootstrap-org/crowd-counting/resolve/main/weights.pth) & [Official leeyeehoo/CSRNet-pytorch](https://drive.google.com/open?id=1zKn6YlLW3Z9ocgPbP99oz7r2nC7_TBXK) | `shanghaitech_part_b.pth` |
| **ShanghaiTech Part A (Dense Benchmark)** | Highly dense crowds (geometry-adaptive kernels $k$-NN) | [deshpandeishita/csrnet-crowd-counting](https://huggingface.co/deshpandeishita/csrnet-crowd-counting/resolve/main/weights.pth) | `shanghaitech_part_a.pth` |

## 2. Checkpoint Architecture Verification

The model weights map 1:1 to the CSRNet architecture:
- **Frontend (10 Conv layers from VGG16)**:
  - `frontend.0` (Conv2d 3 -> 64)
  - `frontend.2` (Conv2d 64 -> 64)
  - `frontend.5` (Conv2d 64 -> 128)
  - `frontend.7` (Conv2d 128 -> 128)
  - `frontend.10` (Conv2d 128 -> 256)
  - `frontend.12` (Conv2d 256 -> 256)
  - `frontend.14` (Conv2d 256 -> 256)
  - `frontend.17` (Conv2d 256 -> 512)
  - `frontend.19` (Conv2d 512 -> 512)
  - `frontend.21` (Conv2d 512 -> 512)
- **Backend (6 Dilated Conv layers, dilation=2)**:
  - `backend.0` (Conv2d 512 -> 512, dilation=2)
  - `backend.2` (Conv2d 512 -> 512, dilation=2)
  - `backend.4` (Conv2d 512 -> 512, dilation=2)
  - `backend.6` (Conv2d 512 -> 256, dilation=2)
  - `backend.8` (Conv2d 256 -> 128, dilation=2)
  - `backend.10` (Conv2d 128 -> 64, dilation=2)
- **Output Layer**:
  - `output_layer` (Conv2d 64 -> 1, kernel_size=1)
- **Total Parameters**: 16,263,361 float32 weights (~65 MB).
- **GPU VRAM Requirement**: ~65 MB model memory footprint + ~100 MB activation footprint at 1080p, well within the 4 GB VRAM limit of the NVIDIA RTX 3050.

## 3. Recommended Placement

Place the downloaded file as:
```
backend/ai/weights/shanghaitech_part_b.pth
```
or keep the original name (`part_B_model.pth.tar` or `weights.pth`).
The predictor will automatically discover any of these default file names in this directory.
