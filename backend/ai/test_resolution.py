"""
CSRNet Image-Resolution Experiment (Stage 7 Research)
----------------------------------------------------
Investigates the impact of image resolution and in-memory spatial scaling on
crowd-count predictions for the existing ShanghaiTech Part B production model.

Safety Guarantees:
- Standalone execution: runs only when explicitly invoked.
- Production configuration, weights, and database records remain strictly unchanged.
- Reuses exact model weights, ImageNet preprocessing, and density calculation logic.
- Safely catches and isolates GPU out-of-memory errors per scale factor.
"""

import sys
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import torch
    from PIL import Image
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Error: PyTorch and Pillow are required to run this experiment.")
    sys.exit(1)

from ai.predictor import CrowdPredictor


def run_resolution_experiment(
    image_path: Path,
    weights_path: Path,
    scales: Optional[List[float]] = None,
    device: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Executes CSRNet inference across multiple in-memory scaling factors.
    Catches GPU out-of-memory exceptions safely.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Auditorium test image not found at: {image_path}")

    if not weights_path.is_file():
        raise FileNotFoundError(f"Production weights checkpoint not found at: {weights_path}")

    if scales is None:
        scales = [0.75, 1.0, 1.25, 1.5, 2.0]

    print(f"Loading production Part B model from: {weights_path.name}")
    predictor = CrowdPredictor(weights_path=weights_path, device=device)
    print(f"Inference device: {predictor.device}")

    # Load original image
    original_img = Image.open(image_path).convert('RGB')
    orig_w, orig_h = original_img.size
    print(f"Target image: {image_path.name} (Native Resolution: {orig_w}x{orig_h})")

    # High quality resampling filter
    resample_filter = getattr(Image.Resampling, 'LANCZOS', getattr(Image, 'LANCZOS', Image.BICUBIC))

    results = []

    for scale in scales:
        if scale == 1.0:
            current_img = original_img
            target_w, target_h = orig_w, orig_h
        else:
            target_w = max(1, int(round(orig_w * scale)))
            target_h = max(1, int(round(orig_h * scale)))
            current_img = original_img.resize((target_w, target_h), resample=resample_filter)

        try:
            # Preprocess using production pipeline (ToTensor + ImageNet Normalize)
            input_tensor = predictor.transform(current_img).unsqueeze(0).to(predictor.device)

            # Gradient-free forward pass
            start_time = time.perf_counter()
            with torch.inference_mode():
                density_map = predictor.model(input_tensor)
                if predictor.device.type == 'cuda':
                    torch.cuda.synchronize()
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

            # Density integration
            density_tensor = density_map.squeeze(0).squeeze(0)
            dm_h, dm_w = density_tensor.shape
            non_negative_density = torch.clamp(density_tensor, min=0.0)
            raw_sum = float(non_negative_density.sum().item())
            count = max(0, int(round(raw_sum)))

            results.append({
                "scale": scale,
                "input_w": target_w,
                "input_h": target_h,
                "dm_w": dm_w,
                "dm_h": dm_h,
                "predicted_count": count,
                "raw_sum": raw_sum,
                "latency_ms": latency_ms,
                "status": "SUCCESS"
            })

            # Clean temporary tensors
            del input_tensor, density_map, density_tensor, non_negative_density
            if predictor.device.type == 'cuda':
                torch.cuda.empty_cache()

        except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
            err_msg = str(e)
            if "out of memory" in err_msg.lower():
                if predictor.device.type == 'cuda':
                    torch.cuda.empty_cache()
                results.append({
                    "scale": scale,
                    "input_w": target_w,
                    "input_h": target_h,
                    "dm_w": 0,
                    "dm_h": 0,
                    "predicted_count": None,
                    "raw_sum": None,
                    "latency_ms": None,
                    "status": "FAILED (CUDA OOM)"
                })
            else:
                raise e

    return results


def print_results_table(results: List[Dict[str, Any]]) -> None:
    """Formats and prints experiment results table."""
    header = (
        f"{'Scale':<7} | "
        f"{'Input Res (WxH)':<17} | "
        f"{'Density Grid':<14} | "
        f"{'Pred Count':<11} | "
        f"{'Raw Sum':<10} | "
        f"{'Latency':<11} | "
        f"{'Status':<16}"
    )
    separator = "-" * len(header)
    print("\n" + "=" * len(header))
    print(" CSRNet Image-Resolution & Scaling Experiment Results (Part B)")
    print("=" * len(header))
    print(header)
    print(separator)

    for r in results:
        scale_str = f"{r['scale']:<7.2f}"
        res_str = f"{r['input_w']}x{r['input_h']}"
        grid_str = f"{r['dm_w']}x{r['dm_h']}" if r['dm_w'] else "N/A"
        cnt_str = f"{r['predicted_count']}" if r['predicted_count'] is not None else "N/A"
        raw_str = f"{r['raw_sum']:<10.2f}" if r['raw_sum'] is not None else "N/A"
        lat_str = f"{r['latency_ms']} ms" if r['latency_ms'] is not None else "N/A"
        status_str = r['status']

        print(
            f"{scale_str} | "
            f"{res_str:<17} | "
            f"{grid_str:<14} | "
            f"{cnt_str:<11} | "
            f"{raw_str:<10} | "
            f"{lat_str:<11} | "
            f"{status_str:<16}"
        )

    print(separator)
    print("\nScientific Notes & Limitations:")
    print("1. Interpolation Limit: Upsampling (e.g. 1.25x - 2.0x) uses Lanczos interpolation,")
    print("   which smooths pixel values but CANNOT synthesize genuine high-frequency facial")
    print("   or head features that were not captured by the camera sensor.")
    print("2. Receptive Field Physics: CSRNet uses a fixed receptive field (~284x284 px).")
    print("   Rescaling alters the apparent pixel dimensions of heads relative to the dilated")
    print("   convolution kernels, changing model activation without providing new visual detail.")
    print("3. Higher Count != Higher Accuracy: A higher headcount at increased scale does not mean")
    print("   improved accuracy; it reflects kernel sensitivity to enlarged, blurry features.")
    print("=" * len(header) + "\n")


if __name__ == '__main__':
    target_image = BACKEND_DIR / 'uploads' / 'event_images' / 'event_9034_20261019_121905_29b4df5f.jpg'
    production_weights = BACKEND_DIR / 'ai' / 'weights' / 'shanghaitech_part_b.pth'

    if not target_image.is_file():
        print(f"Error: Target image file not found at: {target_image}")
        sys.exit(1)

    if not production_weights.is_file():
        print(f"Error: Checkpoint weights file not found at: {production_weights}")
        sys.exit(1)

    res = run_resolution_experiment(
        image_path=target_image,
        weights_path=production_weights,
        scales=[0.75, 1.0, 1.25, 1.5, 2.0]
    )
    print_results_table(res)
