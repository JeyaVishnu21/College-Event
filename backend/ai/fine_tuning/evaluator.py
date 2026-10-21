"""
CSRNet Comparative Evaluation & Benchmarking Suite
--------------------------------------------------
Evaluates baseline (ShanghaiTech Part B) vs fine-tuned models on identical
held-out images across MAE, RMSE, signed error, and density-stratified tiers.
"""

import os
import sys
import json
import csv
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from PIL import Image

import torch
from torchvision import transforms

from ..model import CSRNet
from .density_map import load_points_from_file


class CrowdEvaluator:
    """
    Evaluator comparing multiple CSRNet checkpoints on verified ground truth.
    Strictly forbids test-set model selection, hardcoded multipliers, or manual adjustments.
    """

    def __init__(self, device: Optional[str] = None):
        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

    def load_model(self, checkpoint_path: Union[str, Path]) -> CSRNet:
        """Loads a model with verified parameters."""
        path = Path(checkpoint_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Checkpoint not found: {path}")

        try:
            ckpt = torch.load(str(path), map_location=self.device, weights_only=False)
        except TypeError:
            ckpt = torch.load(str(path), map_location=self.device)

        if isinstance(ckpt, dict):
            raw_dict = ckpt.get('model_state_dict', ckpt.get('state_dict', ckpt.get('model', ckpt)))
        else:
            raw_dict = ckpt.state_dict()

        clean_dict = {}
        for k, v in raw_dict.items():
            k_clean = k[7:] if k.startswith('module.') else k
            if k_clean.startswith('output.'):
                k_clean = 'output_layer.' + k_clean[7:]
            clean_dict[k_clean] = v

        model = CSRNet(load_weights=True)
        model.load_state_dict(clean_dict, strict=True)
        model.to(self.device)
        model.eval()
        return model

    def predict_image(self, model: CSRNet, image_path: Path) -> Tuple[int, float]:
        """
        Runs inference on single image.
        Returns (integer_headcount, raw_continuous_density_sum).
        """
        with Image.open(str(image_path)) as img:
            pil_img = img.convert('RGB')
            w, h = pil_img.size

            # Ensure dimensions are divisible by 8 for CSRNet
            new_w = max(8, (w // 8) * 8)
            new_h = max(8, (h // 8) * 8)
            if new_w != w or new_h != h:
                pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)

            tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            output = model(tensor)
            raw_sum = float(output.sum().item())
            headcount = max(0, int(round(raw_sum)))

        return headcount, round(raw_sum, 3)

    def evaluate_model(
        self,
        model: CSRNet,
        test_items: List[Dict[str, Any]],
        model_label: str = "Model"
    ) -> Dict[str, Any]:
        """
        Evaluates a single model across test images.
        Computes MAE, RMSE, Signed Error, and Density Tier breakdowns.
        """
        if not test_items:
            raise ValueError("Evaluation test items list is empty.")

        errors = []
        squared_errors = []
        signed_errors = []
        per_image_results = []

        # Density Tiers: Low (0-50), Medium (51-200), High (201+)
        tier_data = {
            "low (0-50)": {"errors": [], "sq_errors": [], "signed": [], "count": 0},
            "medium (51-200)": {"errors": [], "sq_errors": [], "signed": [], "count": 0},
            "high (201+)": {"errors": [], "sq_errors": [], "signed": [], "count": 0},
        }

        for it in test_items:
            img_path = Path(it["image_path"])
            gt_count = int(round(it["headcount"]))
            event_type = it.get("event_type", "college_event")
            density_category = it.get("density_category") or ""

            pred_count, raw_sum = self.predict_image(model, img_path)

            diff = pred_count - gt_count
            abs_err = abs(diff)
            sq_err = diff ** 2

            errors.append(abs_err)
            squared_errors.append(sq_err)
            signed_errors.append(diff)

            # Assign to tier
            if gt_count <= 50:
                t_key = "low (0-50)"
            elif gt_count <= 200:
                t_key = "medium (51-200)"
            else:
                t_key = "high (201+)"

            if not density_category:
                density_category = t_key

            tier_data[t_key]["errors"].append(abs_err)
            tier_data[t_key]["sq_errors"].append(sq_err)
            tier_data[t_key]["signed"].append(diff)
            tier_data[t_key]["count"] += 1

            per_image_results.append({
                "image": img_path.name,
                "event_type": event_type,
                "density_category": density_category,
                "ground_truth": gt_count,
                "predicted": pred_count,
                "raw_density_sum": raw_sum,
                "signed_error": diff,
                "absolute_error": abs_err,
                "tier": t_key
            })

        n = len(errors)
        overall_mae = float(np.mean(errors))
        overall_rmse = float(np.sqrt(np.mean(squared_errors)))
        overall_signed = float(np.mean(signed_errors))

        tier_summary = {}
        for k, v in tier_data.items():
            cnt = v["count"]
            tier_summary[k] = {
                "sample_count": cnt,
                "mae": round(float(np.mean(v["errors"])), 2) if cnt > 0 else None,
                "rmse": round(float(np.sqrt(np.mean(v["sq_errors"]))), 2) if cnt > 0 else None,
                "signed_error": round(float(np.mean(v["signed"])), 2) if cnt > 0 else None,
            }

        return {
            "model_label": model_label,
            "sample_count": n,
            "overall_metrics": {
                "mae": round(overall_mae, 2),
                "rmse": round(overall_rmse, 2),
                "signed_error": round(overall_signed, 2),
            },
            "density_tiers": tier_summary,
            "per_image_results": per_image_results
        }

    def compare_models(
        self,
        baseline_checkpoint: Union[str, Path],
        finetuned_checkpoint: Union[str, Path],
        test_items: List[Dict[str, Any]],
        output_dir: Optional[Union[str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Evaluates and performs side-by-side comparison on identical test samples.
        Exports results in both JSON and CSV formats (per-image and summary).
        """
        if not test_items:
            raise ValueError("Evaluation test items list is empty.")

        baseline_model = self.load_model(baseline_checkpoint)
        finetuned_model = self.load_model(finetuned_checkpoint)

        baseline_results = self.evaluate_model(baseline_model, test_items, model_label="Pretrained Part B (Baseline)")
        finetuned_results = self.evaluate_model(finetuned_model, test_items, model_label="Fine-Tuned Checkpoint")

        # Compute relative improvements
        b_mae = baseline_results["overall_metrics"]["mae"]
        f_mae = finetuned_results["overall_metrics"]["mae"]
        mae_delta = round(f_mae - b_mae, 2)
        mae_pct_improvement = round(((b_mae - f_mae) / b_mae) * 100, 2) if b_mae > 0 else 0.0

        b_rmse = baseline_results["overall_metrics"]["rmse"]
        f_rmse = finetuned_results["overall_metrics"]["rmse"]
        rmse_delta = round(f_rmse - b_rmse, 2)

        comparison = {
            "test_sample_count": len(test_items),
            "baseline": baseline_results,
            "finetuned": finetuned_results,
            "comparison": {
                "baseline_mae": b_mae,
                "finetuned_mae": f_mae,
                "mae_delta": mae_delta,
                "mae_improvement_pct": mae_pct_improvement,
                "baseline_rmse": b_rmse,
                "finetuned_rmse": f_rmse,
                "rmse_delta": rmse_delta,
                "baseline_signed_error": baseline_results["overall_metrics"]["signed_error"],
                "finetuned_signed_error": finetuned_results["overall_metrics"]["signed_error"],
            }
        }

        if output_dir:
            out_p = Path(output_dir).resolve()
            out_p.mkdir(parents=True, exist_ok=True)

            # 1. Save detailed comparison JSON
            with open(out_p / "evaluation_results.json", "w", encoding="utf-8") as f:
                json.dump(comparison, f, indent=2)

            # 2. Save per-image predictions CSV
            csv_path = out_p / "evaluation_results.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "image_name",
                    "event_type",
                    "density_category",
                    "ground_truth",
                    "baseline_predicted",
                    "baseline_signed_error",
                    "baseline_abs_error",
                    "finetuned_predicted",
                    "finetuned_signed_error",
                    "finetuned_abs_error",
                    "abs_error_delta",
                    "finetuned_improved"
                ])
                base_imgs = {x["image"]: x for x in baseline_results["per_image_results"]}
                for f_item in finetuned_results["per_image_results"]:
                    img_name = f_item["image"]
                    b_item = base_imgs.get(img_name, {})
                    b_pred = b_item.get("predicted", "")
                    b_err = b_item.get("signed_error", "")
                    b_abs = b_item.get("absolute_error", "")
                    f_pred = f_item["predicted"]
                    f_err = f_item["signed_error"]
                    f_abs = f_item["absolute_error"]
                    delta = round(f_abs - b_abs, 2) if (b_abs != "" and f_abs != "") else ""
                    improved = (f_abs < b_abs) if (b_abs != "" and f_abs != "") else False
                    writer.writerow([
                        img_name,
                        f_item.get("event_type", "college_event"),
                        f_item.get("density_category", f_item.get("tier", "")),
                        f_item["ground_truth"],
                        b_pred,
                        b_err,
                        b_abs,
                        f_pred,
                        f_err,
                        f_abs,
                        delta,
                        improved
                    ])

            # 3. Save summary metrics CSV
            summary_path = out_p / "summary_metrics.csv"
            with open(summary_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "category",
                    "sample_count",
                    "baseline_mae",
                    "finetuned_mae",
                    "mae_delta",
                    "baseline_rmse",
                    "finetuned_rmse",
                    "rmse_delta",
                    "baseline_bias",
                    "finetuned_bias"
                ])
                # Overall row
                c = comparison["comparison"]
                writer.writerow([
                    "Overall",
                    len(test_items),
                    c["baseline_mae"],
                    c["finetuned_mae"],
                    c["mae_delta"],
                    c["baseline_rmse"],
                    c["finetuned_rmse"],
                    c["rmse_delta"],
                    c["baseline_signed_error"],
                    c["finetuned_signed_error"]
                ])
                # Density tiers rows
                for t_name, b_tier in baseline_results["density_tiers"].items():
                    f_tier = finetuned_results["density_tiers"].get(t_name, {})
                    b_mae_val = b_tier["mae"]
                    f_mae_val = f_tier.get("mae")
                    m_d = round(f_mae_val - b_mae_val, 2) if (b_mae_val is not None and f_mae_val is not None) else ""
                    b_rmse_val = b_tier["rmse"]
                    f_rmse_val = f_tier.get("rmse")
                    r_d = round(f_rmse_val - b_rmse_val, 2) if (b_rmse_val is not None and f_rmse_val is not None) else ""
                    writer.writerow([
                        t_name,
                        b_tier["sample_count"],
                        b_mae_val,
                        f_mae_val,
                        m_d,
                        b_rmse_val,
                        f_rmse_val,
                        r_d,
                        b_tier["signed_error"],
                        f_tier.get("signed_error")
                    ])

        return comparison

    @staticmethod
    def verify_annotation_counts(annotation_dir: Union[str, Path]) -> Dict[str, int]:
        """Utility to verify exact point counts across annotation files directly."""
        ann_p = Path(annotation_dir).resolve()
        if not ann_p.is_dir():
            raise FileNotFoundError(f"Annotation directory not found: {ann_p}")

        results = {}
        for f in sorted(ann_p.iterdir()):
            if f.is_file() and f.suffix.lower() in {'.mat', '.json', '.csv', '.txt'}:
                try:
                    pts = load_points_from_file(f)
                    results[f.name] = len(pts)
                except Exception as e:
                    results[f.name] = -1
        return results
