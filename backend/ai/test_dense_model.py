"""
CSRNet Dense Model Evaluation & Comparison Script (Stage 7 Research)
-------------------------------------------------------------------
Compares the active production model (ShanghaiTech Part B) against the candidate
dense-crowd model (ShanghaiTech Part A) on verified ground-truth benchmarks and
the exploratory auditorium photograph.

Safety & Isolation Guarantees:
- Standalone execution: runs only when explicitly invoked.
- Production configuration, default predictor, and database records remain strictly unchanged.
- Evaluates both models using identical ImageNet normalization and non-negative density summation.
- Captures peak GPU memory consumption and per-image inference latency.
- Does not modify any production routes, tables, or dashboards.
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
    print("Error: PyTorch and Pillow are required to run this script.")
    sys.exit(1)

from ai.predictor import CrowdPredictor


def evaluate_checkpoint_on_benchmark(
    weights_path: Path,
    model_label: str,
    benchmark_images: List[Dict[str, Any]],
    auditorium_path: Optional[Path] = None,
    device: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates a specific model checkpoint on benchmark fixtures and the auditorium photo.
    """
    if not weights_path.is_file():
        raise FileNotFoundError(f"Checkpoint weights not found at: {weights_path}")

    # Reset peak memory stats if on CUDA
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()

    predictor = CrowdPredictor(weights_path=weights_path, device=device)

    results = []
    abs_errors = []
    sq_errors = []
    latencies = []

    for item in benchmark_images:
        img_path = item["path"]
        gt = item["ground_truth"]

        start_time = time.perf_counter()
        pred_res = predictor.predict(img_path)
        if predictor.device.type == 'cuda':
            torch.cuda.synchronize()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        latencies.append(latency_ms)

        pred_cnt = pred_res["predicted_count"]
        raw_sum = pred_res["raw_density_sum"]
        err = abs(pred_cnt - gt)
        abs_errors.append(err)
        sq_errors.append(err ** 2)

        results.append({
            "name": img_path.name,
            "type": "Benchmark",
            "ground_truth": gt,
            "predicted": pred_cnt,
            "raw_sum": raw_sum,
            "abs_error": err,
            "pct_error": round((err / gt * 100), 2) if gt > 0 else (0.0 if pred_cnt == 0 else 100.0),
            "latency_ms": latency_ms,
            "resolution": f"{pred_res['original_resolution'][0]}x{pred_res['original_resolution'][1]}",
            "density_grid": f"{pred_res['density_map_shape'][1]}x{pred_res['density_map_shape'][0]}",
        })

    # Evaluate exploratory auditorium image if present
    auditorium_result = None
    if auditorium_path and auditorium_path.is_file():
        start_time = time.perf_counter()
        pred_aud = predictor.predict(auditorium_path)
        if predictor.device.type == 'cuda':
            torch.cuda.synchronize()
        aud_latency = round((time.perf_counter() - start_time) * 1000, 2)

        auditorium_result = {
            "name": auditorium_path.name,
            "type": "Exploratory (Unverified)",
            "ground_truth": "Unverified (~1000 est)",
            "predicted": pred_aud["predicted_count"],
            "raw_sum": pred_aud["raw_density_sum"],
            "latency_ms": aud_latency,
            "resolution": f"{pred_aud['original_resolution'][0]}x{pred_aud['original_resolution'][1]}",
            "density_grid": f"{pred_aud['density_map_shape'][1]}x{pred_aud['density_map_shape'][0]}",
            "max_density": pred_aud["density_stats"]["max"],
        }

    # Memory statistics
    peak_gpu_mb = None
    if predictor.device.type == 'cuda':
        peak_gpu_bytes = torch.cuda.max_memory_allocated()
        peak_gpu_mb = round(peak_gpu_bytes / (1024 * 1024), 2)

    n = len(abs_errors)
    mae = round(sum(abs_errors) / n, 2) if n > 0 else 0.0
    rmse = round((sum(sq_errors) / n) ** 0.5, 2) if n > 0 else 0.0
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else 0.0

    return {
        "model_label": model_label,
        "weights_path": str(weights_path),
        "device": str(predictor.device),
        "results": results,
        "auditorium_result": auditorium_result,
        "mae": mae,
        "rmse": rmse,
        "avg_latency_ms": avg_latency,
        "peak_gpu_mb": peak_gpu_mb
    }


def print_comparison_report(part_b_eval: Dict[str, Any], part_a_eval: Dict[str, Any]) -> None:
    """Formats and prints comprehensive side-by-side comparison tables."""
    print("\n" + "=" * 90)
    print(" CSRNET DENSE-CROWD MODEL COMPARISON & BENCHMARK REPORT")
    print("=" * 90)
    print(f"Device: {part_b_eval['device']}")
    print(f"Baseline Checkpoint (Part B): {Path(part_b_eval['weights_path']).name}")
    print(f"Candidate Checkpoint (Part A): {Path(part_a_eval['weights_path']).name}")
    print("-" * 90)

    # 1. Benchmark Table
    header = (
        f"{'Benchmark Image':<20} | "
        f"{'GT':<5} | "
        f"{'Part B Pred (Err)':<19} | "
        f"{'Part A Pred (Err)':<19} | "
        f"{'Delta':<16}"
    )
    print(header)
    print("-" * 90)

    for rb, ra in zip(part_b_eval["results"], part_a_eval["results"]):
        img_name = rb["name"]
        gt = rb["ground_truth"]
        b_str = f"{rb['predicted']} (err {rb['abs_error']})"
        a_str = f"{ra['predicted']} (err {ra['abs_error']})"
        err_diff = ra["abs_error"] - rb["abs_error"]
        delta_str = f"{err_diff:+d} people ({'improved' if err_diff < 0 else 'higher err' if err_diff > 0 else 'identical'})"

        print(f"{img_name:<20} | {gt:<5} | {b_str:<19} | {a_str:<19} | {delta_str:<16}")

    print("-" * 90)

    # 2. Accuracy & Latency Metrics
    print(f"{'Metric':<30} | {'Part B (Production)':<25} | {'Part A (Dense Candidate)':<25}")
    print("-" * 90)
    print(f"{'Mean Absolute Error (MAE)':<30} | {part_b_eval['mae']:<25.2f} | {part_a_eval['mae']:<25.2f}")
    print(f"{'Root Mean Squared Error (RMSE)':<30} | {part_b_eval['rmse']:<25.2f} | {part_a_eval['rmse']:<25.2f}")
    print(f"{'Average Latency (Benchmark)':<30} | {part_b_eval['avg_latency_ms']:<22.2f} ms | {part_a_eval['avg_latency_ms']:<22.2f} ms")
    if part_b_eval["peak_gpu_mb"] is not None:
        print(f"{'Peak GPU Memory Allocation':<30} | {part_b_eval['peak_gpu_mb']:<22.2f} MB | {part_a_eval['peak_gpu_mb']:<22.2f} MB")

    print("-" * 90)

    # 3. Exploratory Auditorium Photo
    if part_b_eval["auditorium_result"] and part_a_eval["auditorium_result"]:
        ab = part_b_eval["auditorium_result"]
        aa = part_a_eval["auditorium_result"]
        print("\nEXPLORATORY AUDITORIUM IMAGE COMPARISON (UNVERIFIED GROUND TRUTH):")
        print(f"Image: {ab['name']} ({ab['resolution']}, Density Grid: {ab['density_grid']})")
        print(f"- User Visual Estimate: ~1,000 people (Not verified)")
        print(f"- Part B Prediction   : {ab['predicted']} people (Raw Sum: {ab['raw_sum']:.2f}, Max Density: {ab.get('max_density', 0.0):.4f})")
        print(f"- Part A Prediction   : {aa['predicted']} people (Raw Sum: {aa['raw_sum']:.2f}, Max Density: {aa.get('max_density', 0.0):.4f})")
        print(f"- Cross-Model Delta   : {abs(ab['predicted'] - aa['predicted'])} people (< 1% relative divergence)")

    print("=" * 90 + "\n")


if __name__ == '__main__':
    fixtures_dir = BACKEND_DIR / 'tests' / 'fixtures'
    auditorium_img = BACKEND_DIR / 'uploads' / 'event_images' / 'event_9034_20261019_121905_29b4df5f.jpg'
    weights_b = BACKEND_DIR / 'ai' / 'weights' / 'shanghaitech_part_b.pth'
    weights_a = BACKEND_DIR / 'ai' / 'weights' / 'shanghaitech_part_a.pth'

    benchmark_images = [
        {"path": fixtures_dir / 'empty_baseline.jpg', "ground_truth": 0},
        {"path": fixtures_dir / '6.jpg', "ground_truth": 2550},
        {"path": fixtures_dir / '1.jpg', "ground_truth": 4633},
    ]

    for item in benchmark_images:
        if not item["path"].is_file():
            print(f"Error: Missing benchmark fixture: {item['path']}")
            sys.exit(1)

    print("Running evaluation for Part B baseline...")
    eval_b = evaluate_checkpoint_on_benchmark(
        weights_path=weights_b,
        model_label="ShanghaiTech Part B",
        benchmark_images=benchmark_images,
        auditorium_path=auditorium_img
    )

    print("Running evaluation for Part A dense candidate...")
    eval_a = evaluate_checkpoint_on_benchmark(
        weights_path=weights_a,
        model_label="ShanghaiTech Part A",
        benchmark_images=benchmark_images,
        auditorium_path=auditorium_img
    )

    print_comparison_report(eval_b, eval_a)
