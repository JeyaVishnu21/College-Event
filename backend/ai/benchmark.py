"""
CSRNet Standardized Benchmark & Model Validation Suite (Stage 7)
---------------------------------------------------------------
Evaluates and validates crowd counting models (ShanghaiTech Part B and Part A)
against ground-truth annotated benchmark datasets under identical preprocessing.

Key Capabilities:
- Warm-up pass before timing to capture accurate, post-initialization inference latency.
- Mathematically sound MAPE (computed strictly on images where Ground Truth > 0).
- Peak CUDA GPU memory tracking.
- Per-image breakdown with absolute and percentage errors.
- Graceful error handling for missing annotations, corrupt files, or GPU OOM.
- Safe, non-destructive execution: zero database or API side effects.

Usage:
  python backend/ai/benchmark.py [--fixtures-dir <dir>] [--device <cuda|cpu>]
"""

import sys
import os
import time
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import torch
    from PIL import Image
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("Error: PyTorch and Pillow are required to run this benchmark.")
    sys.exit(1)

from ai.predictor import CrowdPredictor


def load_ground_truth_map(fixtures_dir: Path) -> Tuple[Dict[str, int], List[Dict[str, str]]]:
    """
    Loads verified ground-truth counts from metadata JSON or accompanying .mat annotations.
    Returns (gt_map, skipped_reasons).
    """
    gt_map: Dict[str, int] = {}
    skipped: List[Dict[str, str]] = []

    json_path = fixtures_dir / 'ground_truth.json'
    if json_path.is_file():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k, v in data.items():
                    if not k.startswith('_') and isinstance(v, (int, float)):
                        gt_map[k] = int(round(v))
        except Exception as e:
            skipped.append({"file": "ground_truth.json", "reason": f"Failed to parse JSON: {e}"})

    # Discover candidate image files
    image_exts = {'.jpg', '.jpeg', '.png'}
    candidate_images = sorted([
        f for f in fixtures_dir.iterdir()
        if f.is_file() and f.suffix.lower() in image_exts
    ])

    for img_f in candidate_images:
        if img_f.name in gt_map:
            continue

        # Check for accompanying .mat annotation
        mat_candidates = [
            fixtures_dir / f"{img_f.stem}_ann.mat",
            fixtures_dir / f"GT_{img_f.name}.mat",
            fixtures_dir / f"GT_{img_f.stem}.mat",
            fixtures_dir / f"{img_f.stem}.mat",
        ]
        found_mat = False
        for mat_p in mat_candidates:
            if mat_p.is_file():
                try:
                    import scipy.io
                    mat_data = scipy.io.loadmat(str(mat_p))
                    if 'annPoints' in mat_data:
                        gt_map[img_f.name] = int(len(mat_data['annPoints']))
                        found_mat = True
                        break
                    elif 'image_info' in mat_data:
                        cnt = mat_data['image_info'][0, 0][0, 0][1][0, 0]
                        gt_map[img_f.name] = int(round(float(cnt)))
                        found_mat = True
                        break
                except Exception as ex:
                    skipped.append({"file": mat_p.name, "reason": f"MAT file read error: {ex}"})

        if not found_mat and img_f.name not in gt_map:
            skipped.append({"file": img_f.name, "reason": "No ground-truth annotation found"})

    return gt_map, skipped


def evaluate_model_benchmark(
    weights_path: Path,
    model_name: str,
    fixtures_dir: Path,
    device: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates a single model checkpoint against valid ground-truth annotated fixtures.
    Executes a warm-up pass before measuring latency.
    """
    if not weights_path.is_file():
        raise FileNotFoundError(f"Weights file not found: {weights_path}")

    predictor = CrowdPredictor(weights_path=weights_path, device=device)
    gt_map, skipped = load_ground_truth_map(fixtures_dir)

    # Filter valid images
    valid_images = []
    for fname, gt_count in gt_map.items():
        img_p = fixtures_dir / fname
        if img_p.is_file():
            valid_images.append((img_p, gt_count))
        else:
            skipped.append({"file": fname, "reason": "Image file referenced in GT does not exist"})

    if not valid_images:
        return {
            "model_name": model_name,
            "weights_path": str(weights_path),
            "valid_count": 0,
            "skipped": skipped,
            "error": "No valid annotated images available for evaluation"
        }

    # Warm-up pass to ensure CUDA kernels / VGG weights are initialized in memory
    try:
        first_img, _ = valid_images[0]
        _ = predictor.predict(first_img)
        if predictor.device.type == 'cuda':
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
    except Exception as e:
        pass

    results = []
    abs_errors = []
    sq_errors = []
    pct_errors = []  # Strictly where GT > 0
    latencies = []

    for img_p, gt in valid_images:
        try:
            start_t = time.perf_counter()
            pred = predictor.predict(img_p)
            if predictor.device.type == 'cuda':
                torch.cuda.synchronize()
            lat_ms = round((time.perf_counter() - start_t) * 1000, 2)
            latencies.append(lat_ms)

            cnt = pred["predicted_count"]
            err = abs(cnt - gt)
            abs_errors.append(err)
            sq_errors.append(err ** 2)

            # Mathematically meaningful percentage error (GT > 0 only)
            pct_err = None
            if gt > 0:
                pct_err = round((err / gt) * 100.0, 2)
                pct_errors.append(pct_err)

            results.append({
                "image": img_p.name,
                "ground_truth": gt,
                "predicted": cnt,
                "raw_sum": pred["raw_density_sum"],
                "abs_error": err,
                "pct_error": pct_err,
                "latency_ms": lat_ms,
                "resolution": f"{pred['original_resolution'][0]}x{pred['original_resolution'][1]}",
                "density_grid": f"{pred['density_map_shape'][1]}x{pred['density_map_shape'][0]}",
                "status": "VALID"
            })
        except Exception as e:
            skipped.append({"file": img_p.name, "reason": f"Inference failed: {e}"})

    n = len(abs_errors)
    mae = round(sum(abs_errors) / n, 2) if n > 0 else 0.0
    rmse = round((sum(sq_errors) / n) ** 0.5, 2) if n > 0 else 0.0
    mape = round(sum(pct_errors) / len(pct_errors), 2) if pct_errors else None
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    peak_gpu_mb = None
    if predictor.device.type == 'cuda':
        peak_gpu_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2)

    return {
        "model_name": model_name,
        "weights_path": str(weights_path),
        "device": str(predictor.device),
        "valid_count": n,
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "avg_latency_ms": avg_latency,
        "peak_gpu_mb": peak_gpu_mb,
        "results": results,
        "skipped": skipped
    }


def run_comparative_benchmark(
    fixtures_dir: Optional[Path] = None,
    device: Optional[str] = None
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Runs the standardized comparative benchmark for Part B and Part A.
    """
    if fixtures_dir is None:
        fixtures_dir = BACKEND_DIR / 'tests' / 'fixtures'

    weights_b = BACKEND_DIR / 'ai' / 'weights' / 'shanghaitech_part_b.pth'
    weights_a = BACKEND_DIR / 'ai' / 'weights' / 'shanghaitech_part_a.pth'

    print("Executing benchmark for ShanghaiTech Part B (Production Baseline)...")
    res_b = evaluate_model_benchmark(
        weights_path=weights_b,
        model_name="ShanghaiTech Part B (Production Default)",
        fixtures_dir=fixtures_dir,
        device=device
    )

    print("Executing benchmark for ShanghaiTech Part A (Dense Candidate)...")
    res_a = evaluate_model_benchmark(
        weights_path=weights_a,
        model_name="ShanghaiTech Part A (Dense Candidate)",
        fixtures_dir=fixtures_dir,
        device=device
    )

    return res_b, res_a


def print_benchmark_report(res_b: Dict[str, Any], res_a: Dict[str, Any]) -> None:
    """Prints the structured comparative benchmark report."""
    print("\n" + "=" * 94)
    print(" STANDARDIZED CSRNET CROWD-COUNTING BENCHMARK REPORT")
    print("=" * 94)
    print(f"Device: {res_b['device']}")
    print(f"Baseline Checkpoint : {Path(res_b['weights_path']).name}")
    print(f"Candidate Checkpoint: {Path(res_a['weights_path']).name}")
    print(f"Evaluated Fixtures  : {res_b['valid_count']} images with verified ground-truth annotations")
    if res_b['valid_count'] <= 5:
        print(" [NOTE: Small benchmark split (<10 samples). Results are preliminary.]")
    print("-" * 94)

    # 1. Per-Image Breakdown Table
    header = (
        f"{'Image':<20} | "
        f"{'Resolution':<11} | "
        f"{'GT':<5} | "
        f"{'Part B Pred (Err)':<19} | "
        f"{'Part A Pred (Err)':<19} | "
        f"{'Delta':<10}"
    )
    print(header)
    print("-" * 94)

    # Map results by image filename
    a_by_img = {r['image']: r for r in res_a['results']}

    for rb in res_b['results']:
        img_name = rb['image']
        ra = a_by_img.get(img_name)
        gt = rb['ground_truth']
        res_str = rb['resolution']

        b_pct = f" ({rb['pct_error']}%)" if rb['pct_error'] is not None else ""
        b_str = f"{rb['predicted']} (err {rb['abs_error']}{b_pct})"

        if ra:
            a_pct = f" ({ra['pct_error']}%)" if ra['pct_error'] is not None else ""
            a_str = f"{ra['predicted']} (err {ra['abs_error']}{a_pct})"
            delta_val = ra['abs_error'] - rb['abs_error']
            delta_str = f"{delta_val:+d}"
        else:
            a_str = "N/A"
            delta_str = "N/A"

        print(f"{img_name:<20} | {res_str:<11} | {gt:<5} | {b_str:<19} | {a_str:<19} | {delta_str:<10}")

    print("-" * 94)

    # 2. Summary Aggregate Metrics
    print(f"{'Metric':<34} | {'Part B (Production)':<26} | {'Part A (Dense Candidate)':<26}")
    print("-" * 94)
    print(f"{'Valid Evaluated Images':<34} | {res_b['valid_count']:<26} | {res_a['valid_count']:<26}")
    print(f"{'Mean Absolute Error (MAE)':<34} | {res_b['mae']:<26.2f} | {res_a['mae']:<26.2f}")
    print(f"{'Root Mean Squared Error (RMSE)':<34} | {res_b['rmse']:<26.2f} | {res_a['rmse']:<26.2f}")

    b_mape = f"{res_b['mape']:.2f}%" if res_b['mape'] is not None else "N/A"
    a_mape = f"{res_a['mape']:.2f}%" if res_a['mape'] is not None else "N/A"
    print(f"{'Mean Abs Percentage Error (MAPE)':<34} | {b_mape:<26} | {a_mape:<26}")

    print(f"{'Average Latency (Post Warm-Up)':<34} | {res_b['avg_latency_ms']:<23.2f} ms | {res_a['avg_latency_ms']:<23.2f} ms")
    if res_b['peak_gpu_mb'] is not None:
        print(f"{'Peak GPU Memory Allocation':<34} | {res_b['peak_gpu_mb']:<23.2f} MB | {res_a['peak_gpu_mb']:<23.2f} MB")

    print("-" * 94)

    # 3. Skipped / Failed Images
    all_skipped = res_b.get('skipped', []) + res_a.get('skipped', [])
    unique_skipped = {s['file']: s['reason'] for s in all_skipped}
    if unique_skipped:
        print("\nSkipped or Non-Evaluated Files:")
        for f, reason in unique_skipped.items():
            print(f"  - {f}: {reason}")
    else:
        print("\nSkipped or Failed Images: None (100% of candidate images successfully processed)")

    print("=" * 94 + "\n")


if __name__ == '__main__':
    res_b, res_a = run_comparative_benchmark()
    print_benchmark_report(res_b, res_a)
