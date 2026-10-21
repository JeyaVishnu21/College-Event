"""
UCF-CC-50 5-Fold Crowd Counting Cross-Validation & Evaluation Suite (Stage 7)
----------------------------------------------------------------------------
Evaluates pretrained CSRNet models (ShanghaiTech Part B and Part A) across the
50 extreme-congestion images and annotations of the UCF-CC-50 dataset.

Scientific Note:
These models were pretrained on the ShanghaiTech dataset and were NOT retrained on
UCF-CC-50 training folds. This experiment executes 5-fold cross-validation of
evaluation samples (zero-shot transfer evaluation), not full training cross-validation.
50 images provide limited statistical evidence of cross-domain generalization.

Usage:
  python backend/ai/evaluate_ucf_cc_50.py [--dataset-dir <dir>] [--output-dir <dir>] [--device <cuda|cpu>]
"""

import sys
import os
import time
import json
import csv
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import torch
    import scipy.io
    from PIL import Image
    DEPS_AVAILABLE = True
except ImportError as e:
    DEPS_AVAILABLE = False
    print(f"Error: Missing required dependency: {e}")
    sys.exit(1)

from ai.predictor import CrowdPredictor

# Standard 5-fold split definition for UCF-CC-50 (10 images per fold)
UCF_5_FOLDS = {
    "Fold 1": list(range(1, 11)),
    "Fold 2": list(range(11, 21)),
    "Fold 3": list(range(21, 31)),
    "Fold 4": list(range(31, 41)),
    "Fold 5": list(range(41, 51)),
}


def load_ucf_sample(dataset_dir: Path, img_id: int) -> Tuple[Optional[Path], Optional[int], Optional[str]]:
    """
    Finds image and extracts ground truth from UCF-CC-50 .mat annotation.
    Returns (image_path, gt_count, skip_reason).
    """
    img_candidates = [
        dataset_dir / f"{img_id}.jpg",
        dataset_dir / f"{img_id}.jpeg",
        dataset_dir / f"{img_id}.png",
    ]
    mat_candidates = [
        dataset_dir / f"{img_id}_ann.mat",
        dataset_dir / f"{img_id}.mat",
    ]

    img_path = next((p for p in img_candidates if p.is_file()), None)
    mat_path = next((p for p in mat_candidates if p.is_file()), None)

    if not img_path and not mat_path:
        return None, None, f"Image {img_id}.jpg and annotation {img_id}_ann.mat not found"
    if not img_path:
        return None, None, f"Image file {img_id}.jpg not found (annotation exists)"
    if not mat_path:
        return None, None, f"Annotation file {img_id}_ann.mat not found for {img_path.name}"

    try:
        data = scipy.io.loadmat(str(mat_path))
        if 'annPoints' in data:
            gt_count = int(len(data['annPoints']))
            return img_path, gt_count, None
        else:
            return None, None, f"Key 'annPoints' missing in {mat_path.name}"
    except Exception as e:
        return None, None, f"Failed to parse {mat_path.name}: {e}"


def run_ucf_evaluation(
    dataset_dir: Path,
    output_dir: Path,
    device: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes the 5-fold evaluation for both Part B and Part A models.
    """
    weights_b = BACKEND_DIR / 'ai' / 'weights' / 'shanghaitech_part_b.pth'
    weights_a = BACKEND_DIR / 'ai' / 'weights' / 'shanghaitech_part_a.pth'

    if not weights_b.is_file():
        raise FileNotFoundError(f"Part B weights not found at: {weights_b}")
    if not weights_a.is_file():
        raise FileNotFoundError(f"Part A weights not found at: {weights_a}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Initializing CSRNet predictors...")
    predictor_b = CrowdPredictor(weights_path=weights_b, device=device)
    predictor_a = CrowdPredictor(weights_path=weights_a, device=device)
    active_device = str(predictor_b.device)
    print(f"Device: {active_device}")

    # Warm-up pass on first available image
    for i in range(1, 51):
        test_img, _, _ = load_ucf_sample(dataset_dir, i)
        if test_img:
            try:
                _ = predictor_b.predict(test_img)
                _ = predictor_a.predict(test_img)
                if predictor_b.device.type == 'cuda':
                    torch.cuda.synchronize()
                    torch.cuda.reset_peak_memory_stats()
            except Exception:
                pass
            break

    image_results = []
    skipped_items = []

    fold_metrics = {"Fold 1": {}, "Fold 2": {}, "Fold 3": {}, "Fold 4": {}, "Fold 5": {}}

    latencies_b = []
    latencies_a = []

    for fold_name, img_ids in UCF_5_FOLDS.items():
        fold_abs_err_b = []
        fold_sq_err_b = []
        fold_abs_err_a = []
        fold_sq_err_a = []
        fold_valid_count = 0

        for img_id in img_ids:
            img_path, gt_count, skip_reason = load_ucf_sample(dataset_dir, img_id)
            if skip_reason:
                skipped_items.append({"id": img_id, "fold": fold_name, "reason": skip_reason})
                continue

            # Inference Part B
            t0 = time.perf_counter()
            pred_b = predictor_b.predict(img_path)
            if predictor_b.device.type == 'cuda':
                torch.cuda.synchronize()
            lat_b = round((time.perf_counter() - t0) * 1000, 2)
            latencies_b.append(lat_b)

            # Inference Part A
            t1 = time.perf_counter()
            pred_a = predictor_a.predict(img_path)
            if predictor_a.device.type == 'cuda':
                torch.cuda.synchronize()
            lat_a = round((time.perf_counter() - t1) * 1000, 2)
            latencies_a.append(lat_a)

            cnt_b = pred_b["predicted_count"]
            cnt_a = pred_a["predicted_count"]

            err_b = abs(cnt_b - gt_count)
            err_a = abs(cnt_a - gt_count)

            fold_abs_err_b.append(err_b)
            fold_sq_err_b.append(err_b ** 2)
            fold_abs_err_a.append(err_a)
            fold_sq_err_a.append(err_a ** 2)
            fold_valid_count += 1

            pct_b = round((err_b / gt_count) * 100.0, 2) if gt_count > 0 else 0.0
            pct_a = round((err_a / gt_count) * 100.0, 2) if gt_count > 0 else 0.0

            image_results.append({
                "id": img_id,
                "fold": fold_name,
                "filename": img_path.name,
                "resolution": f"{pred_b['original_resolution'][0]}x{pred_b['original_resolution'][1]}",
                "ground_truth": gt_count,
                "part_b_pred": cnt_b,
                "part_b_raw": pred_b["raw_density_sum"],
                "part_b_err": err_b,
                "part_b_pct_err": pct_b,
                "part_b_lat_ms": lat_b,
                "part_a_pred": cnt_a,
                "part_a_raw": pred_a["raw_density_sum"],
                "part_a_err": err_a,
                "part_a_pct_err": pct_a,
                "part_a_lat_ms": lat_a,
                "delta_err": err_a - err_b  # negative means Part A is better
            })

        # Calculate fold metrics if any images were evaluated
        if fold_valid_count > 0:
            fold_metrics[fold_name] = {
                "valid_count": fold_valid_count,
                "total_expected": len(img_ids),
                "part_b_mae": round(sum(fold_abs_err_b) / fold_valid_count, 2),
                "part_b_rmse": round((sum(fold_sq_err_b) / fold_valid_count) ** 0.5, 2),
                "part_a_mae": round(sum(fold_abs_err_a) / fold_valid_count, 2),
                "part_a_rmse": round((sum(fold_sq_err_a) / fold_valid_count) ** 0.5, 2),
            }
        else:
            fold_metrics[fold_name] = {
                "valid_count": 0,
                "total_expected": len(img_ids),
                "status": "No images available in dataset directory"
            }

    # Aggregate overall metrics across all valid images
    total_valid = len(image_results)
    if total_valid > 0:
        all_err_b = [r["part_b_err"] for r in image_results]
        all_sq_b = [r["part_b_err"] ** 2 for r in image_results]
        all_err_a = [r["part_a_err"] for r in image_results]
        all_sq_a = [r["part_a_err"] ** 2 for r in image_results]

        overall_metrics = {
            "valid_images": total_valid,
            "total_expected": 50,
            "part_b_mae": round(sum(all_err_b) / total_valid, 2),
            "part_b_rmse": round((sum(all_sq_b) / total_valid) ** 0.5, 2),
            "part_a_mae": round(sum(all_err_a) / total_valid, 2),
            "part_a_rmse": round((sum(all_sq_a) / total_valid) ** 0.5, 2),
            "part_b_avg_lat_ms": round(sum(latencies_b) / len(latencies_b), 2) if latencies_b else 0.0,
            "part_a_avg_lat_ms": round(sum(latencies_a) / len(latencies_a), 2) if latencies_a else 0.0,
        }
    else:
        overall_metrics = {
            "valid_images": 0,
            "total_expected": 50,
            "status": "No valid UCF-CC-50 images found"
        }

    peak_gpu_mb = None
    if predictor_b.device.type == 'cuda':
        peak_gpu_mb = round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2)

    report_payload = {
        "benchmark": "UCF-CC-50 5-Fold Evaluation",
        "device": active_device,
        "peak_gpu_mb": peak_gpu_mb,
        "overall_metrics": overall_metrics,
        "fold_metrics": fold_metrics,
        "image_results": image_results,
        "skipped_items": skipped_items,
        "scientific_notes": [
            "This experiment evaluates pretrained checkpoints on UCF-CC-50 evaluation samples without retraining on training folds.",
            "50 images represent extreme density distributions and provide limited statistical power for general crowd diversity.",
            "Production models and configurations remain unchanged."
        ]
    }

    # Save JSON report
    json_path = output_dir / 'ucf_cc_50_evaluation.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report_payload, f, indent=2)

    # Save CSV report
    csv_path = output_dir / 'ucf_cc_50_evaluation.csv'
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            "Image ID", "Fold", "Filename", "Resolution", "Ground Truth",
            "Part B Pred", "Part B Err", "Part B % Err", "Part B Latency (ms)",
            "Part A Pred", "Part A Err", "Part A % Err", "Part A Latency (ms)",
            "Delta (A-B)"
        ])
        for r in image_results:
            writer.writerow([
                r["id"], r["fold"], r["filename"], r["resolution"], r["ground_truth"],
                r["part_b_pred"], r["part_b_err"], r["part_b_pct_err"], r["part_b_lat_ms"],
                r["part_a_pred"], r["part_a_err"], r["part_a_pct_err"], r["part_a_lat_ms"],
                r["delta_err"]
            ])

    print(f"Saved JSON report to: {json_path}")
    print(f"Saved CSV report to : {csv_path}")

    return report_payload


def print_ucf_report(report: Dict[str, Any]) -> None:
    """Formats and prints summary to stdout."""
    print("\n" + "=" * 94)
    print(" UCF-CC-50 5-FOLD CROWD COUNTING EVALUATION REPORT")
    print("=" * 94)
    print(f"Device: {report['device']}")
    if report['peak_gpu_mb'] is not None:
        print(f"Peak GPU Memory: {report['peak_gpu_mb']} MB")
    print("-" * 94)

    # Per-Image Results
    results = report.get("image_results", [])
    if results:
        header = (
            f"{'ID':<4} | "
            f"{'Fold':<8} | "
            f"{'Resolution':<10} | "
            f"{'GT':<5} | "
            f"{'Part B Pred (Err)':<19} | "
            f"{'Part A Pred (Err)':<19} | "
            f"{'Delta':<10}"
        )
        print(header)
        print("-" * 94)
        for r in results:
            b_str = f"{r['part_b_pred']} (err {r['part_b_err']} [{r['part_b_pct_err']}*])".replace('*', '%')
            a_str = f"{r['part_a_pred']} (err {r['part_a_err']} [{r['part_a_pct_err']}*])".replace('*', '%')
            d_str = f"{r['delta_err']:+d}"
            print(f"{r['id']:<4} | {r['fold']:<8} | {r['resolution']:<10} | {r['ground_truth']:<5} | {b_str:<19} | {a_str:<19} | {d_str:<10}")
        print("-" * 94)

    # Fold Summary
    print("\nPER-FOLD SUMMARY:")
    print(f"{'Fold Name':<10} | {'Evaluated':<12} | {'Part B MAE':<12} | {'Part B RMSE':<12} | {'Part A MAE':<12} | {'Part A RMSE':<12}")
    print("-" * 80)
    for fold, fm in report.get("fold_metrics", {}).items():
        if fm.get("valid_count", 0) > 0:
            print(f"{fold:<10} | {fm['valid_count']}/{fm['total_expected']} images  | {fm['part_b_mae']:<12.2f} | {fm['part_b_rmse']:<12.2f} | {fm['part_a_mae']:<12.2f} | {fm['part_a_rmse']:<12.2f}")
        else:
            print(f"{fold:<10} | 0/{fm['total_expected']} images  | {'N/A (Missing)':<12} | {'N/A':<12} | {'N/A (Missing)':<12} | {'N/A':<12}")

    # Overall Summary
    om = report.get("overall_metrics", {})
    print("-" * 80)
    if om.get("valid_images", 0) > 0:
        print(f"Overall Valid Images : {om['valid_images']} / {om['total_expected']}")
        print(f"Overall Part B MAE   : {om['part_b_mae']:.2f} (RMSE: {om['part_b_rmse']:.2f}, Latency: {om.get('part_b_avg_lat_ms', 0):.2f} ms)")
        print(f"Overall Part A MAE   : {om['part_a_mae']:.2f} (RMSE: {om['part_a_rmse']:.2f}, Latency: {om.get('part_a_avg_lat_ms', 0):.2f} ms)")
    else:
        print(f"Overall Valid Images : 0 / 50 (Dataset files missing)")

    # Skipped Summary
    skipped = report.get("skipped_items", [])
    if skipped:
        print(f"\nSkipped / Missing Dataset Items: {len(skipped)} files (e.g. {skipped[0]['reason']})")
    print("=" * 94 + "\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="UCF-CC-50 5-Fold Cross-Validation Evaluation Suite")
    parser.add_argument("--dataset-dir", type=str, default=str(BACKEND_DIR / 'tests' / 'fixtures'))
    parser.add_argument("--output-dir", type=str, default=str(BACKEND_DIR / 'ai' / 'reports'))
    parser.add_argument("--device", type=str, default=None)
    args = parser.parse_args()

    rep = run_ucf_evaluation(
        dataset_dir=Path(args.dataset_dir),
        output_dir=Path(args.output_dir),
        device=args.device
    )
    print_ucf_report(rep)
