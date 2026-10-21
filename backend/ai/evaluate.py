"""
CSRNet Crowd Counting Evaluation & Benchmarking Suite (Stage 7)
--------------------------------------------------------------
Provides repeatable evaluation of the CSRNet inference pipeline against
verified ground-truth headcounts.

Computes:
  - MAE  (Mean Absolute Error): sum(|y - y_hat|) / N
  - MSE  (Mean Squared Error):  sum((y - y_hat)^2) / N
  - RMSE (Root Mean Squared Error): sqrt(MSE)
  - MAPE (Mean Absolute Percentage Error): for images with non-zero headcount
  - Diagnostic statistics: density range, resolution, latency

Usage:
  python backend/ai/evaluate.py [--images-dir <dir>] [--ground-truth <json>] [--weights <pth>] [--device <cuda|cpu>]
"""

import os
import sys
import json
import math
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import scipy.io
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


def load_ground_truth_from_mat(mat_path: Path) -> Optional[int]:
    """Attempts to extract verified ground-truth headcount from a .mat annotation file."""
    if not SCIPY_AVAILABLE or not mat_path.is_file():
        return None
    try:
        data = scipy.io.loadmat(str(mat_path))
        # Format 1: annPoints (UCF-QNRF, UCF-CC-50)
        if 'annPoints' in data:
            return int(len(data['annPoints']))
        # Format 2: image_info (ShanghaiTech)
        if 'image_info' in data:
            info = data['image_info']
            count_val = info[0, 0][0, 0][1][0, 0]
            return int(round(float(count_val)))
    except Exception:
        pass
    return None


def evaluate_dataset(
    images_dir: Path,
    ground_truth_map: Optional[Dict[str, int]] = None,
    weights_path: Optional[Path] = None,
    device: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates CSRNet crowd predictor across all images in a directory with ground truth.
    Returns structured results dictionary with metrics and per-image details.
    """
    from ai.predictor import CrowdPredictor, get_default_predictor

    images_dir = Path(images_dir).resolve()
    if not images_dir.is_dir():
        raise FileNotFoundError(f"Images directory not found: {images_dir}")

    if weights_path:
        predictor = CrowdPredictor(weights_path=weights_path, device=device)
    else:
        predictor = get_default_predictor(device=device)

    # Collect images
    image_extensions = {'.jpg', '.jpeg', '.png'}
    candidate_images = sorted([
        f for f in images_dir.iterdir()
        if f.is_file() and f.suffix.lower() in image_extensions
    ])

    if not candidate_images:
        raise ValueError(f"No image files (.jpg, .jpeg, .png) found in: {images_dir}")

    # Build ground truth dictionary
    gt_dict = {}
    if ground_truth_map:
        gt_dict.update(ground_truth_map)

    # Check for accompanying .mat files in images_dir
    for img_p in candidate_images:
        if img_p.name not in gt_dict:
            # Check possible annotation file patterns
            mat_candidates = [
                img_p.parent / f"{img_p.stem}_ann.mat",
                img_p.parent / f"GT_{img_p.name}.mat",
                img_p.parent / f"GT_{img_p.stem}.mat",
                img_p.parent / f"{img_p.stem}.mat",
            ]
            for mat_p in mat_candidates:
                if mat_p.is_file():
                    gt_count = load_ground_truth_from_mat(mat_p)
                    if gt_count is not None:
                        gt_dict[img_p.name] = gt_count
                        break

    results: List[Dict[str, Any]] = []
    abs_errors: List[float] = []
    sq_errors: List[float] = []
    pct_errors: List[float] = []

    for img_p in candidate_images:
        gt = gt_dict.get(img_p.name)
        if gt is None:
            continue

        pred_res = predictor.predict(img_p)
        pred_cnt = pred_res["predicted_count"]
        raw_sum = pred_res["raw_density_sum"]
        err = abs(pred_cnt - gt)
        abs_errors.append(err)
        sq_errors.append(err ** 2)

        if gt > 0:
            pct_err = (err / gt) * 100.0
            pct_errors.append(pct_err)
        else:
            pct_err = 0.0 if pred_cnt == 0 else 100.0

        item_res = {
            "image": img_p.name,
            "ground_truth": gt,
            "predicted": pred_cnt,
            "raw_sum": raw_sum,
            "abs_error": err,
            "pct_error": round(pct_err, 2),
            "resolution": pred_res["original_resolution"],
            "model_input_shape": pred_res.get("model_input_shape", []),
            "density_map_shape": pred_res["density_map_shape"],
            "latency_ms": pred_res["inference_time_ms"],
            "min_density": pred_res["density_stats"]["min"],
            "max_density": pred_res["density_stats"]["max"],
        }
        results.append(item_res)

    if not results:
        raise ValueError(
            f"None of the {len(candidate_images)} images had verified ground-truth counts."
        )

    n = len(results)
    mae = sum(abs_errors) / n
    mse = sum(sq_errors) / n
    rmse = math.sqrt(mse)
    mape = (sum(pct_errors) / len(pct_errors)) if pct_errors else 0.0

    summary = {
        "num_images": n,
        "mae": round(mae, 2),
        "mse": round(mse, 2),
        "rmse": round(rmse, 2),
        "mape": round(mape, 2),
        "device": str(predictor.device),
        "weights_file": predictor.weights_path.name if predictor.weights_path else "default",
        "results": results
    }

    return summary


def print_evaluation_report(summary: Dict[str, Any]) -> None:
    """Prints a clean ASCII report of benchmark evaluation metrics."""
    print("=" * 82)
    print("           CSRNet Crowd Counting Evaluation & Accuracy Report           ")
    print("=" * 82)
    print(f" Model Checkpoint : {summary['weights_file']}")
    print(f" Execution Device : {summary['device']}")
    print(f" Evaluated Images : {summary['num_images']}")
    print("-" * 82)
    print(f"{'Image':<24} {'GT':>6} {'Pred':>6} {'AbsErr':>8} {'% Err':>8} {'Resolution':>12} {'Latency':>10}")
    print("-" * 82)

    for r in summary["results"]:
        res_str = f"{r['resolution'][0]}x{r['resolution'][1]}"
        lat_str = f"{r['latency_ms']:.1f}ms"
        pct_str = f"{r['pct_error']:.1f}%"
        print(
            f"{r['image'][:24]:<24} "
            f"{r['ground_truth']:>6} "
            f"{r['predicted']:>6} "
            f"{r['abs_error']:>8} "
            f"{pct_str:>8} "
            f"{res_str:>12} "
            f"{lat_str:>10}"
        )

    print("-" * 82)
    print(" SUMMARY ACCURACY METRICS")
    print("-" * 82)
    print(f" Mean Absolute Error (MAE)       : {summary['mae']:.2f} people")
    print(f" Root Mean Squared Error (RMSE)  : {summary['rmse']:.2f}")
    print(f" Mean Abs Percentage Error (MAPE): {summary['mape']:.2f}%")
    print("=" * 82)


def main():
    parser = argparse.ArgumentParser(
        description="CSRNet Repeatable Evaluation against Verified Ground Truth"
    )
    parser.add_argument(
        "--images-dir",
        type=str,
        default=str(BACKEND_DIR / "tests" / "fixtures"),
        help="Directory containing test images and/or .mat annotation files"
    )
    parser.add_argument(
        "--ground-truth",
        type=str,
        default=None,
        help="Path to JSON file mapping image filename to verified headcount"
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=None,
        help="Path to model checkpoint (.pth / .pth.tar)"
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["cuda", "cpu"],
        help="Target device (cuda or cpu)"
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Optional path to write full evaluation results as JSON"
    )

    args = parser.parse_args()

    # Load ground truth JSON if specified or default exists
    gt_map = {}
    gt_path = args.ground_truth
    if not gt_path:
        default_gt = BACKEND_DIR / "tests" / "fixtures" / "ground_truth.json"
        if default_gt.is_file():
            gt_path = str(default_gt)

    if gt_path and Path(gt_path).is_file():
        with open(gt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            gt_map = {k: v for k, v in data.items() if not k.startswith("_")}

    weights = Path(args.weights) if args.weights else None
    summary = evaluate_dataset(
        images_dir=Path(args.images_dir),
        ground_truth_map=gt_map,
        weights_path=weights,
        device=args.device
    )

    print_evaluation_report(summary)

    if args.json_out:
        out_p = Path(args.json_out)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\n[OK] Results exported to {out_p}")


if __name__ == "__main__":
    main()
