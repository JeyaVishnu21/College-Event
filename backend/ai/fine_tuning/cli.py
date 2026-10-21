"""
CSRNet Fine-Tuning CLI Interface
--------------------------------
Commands:
  1. validate-dataset: Scans and validates image/annotation matching, leakage prevention, and splits.
  2. train: Runs memory-conscious fine-tuning on a verified dataset.
  3. evaluate: Compares baseline and fine-tuned checkpoints on held-out test data.
  4. verify-annotations: Directly inspects and counts head annotations across files.
"""

import sys
import json
import argparse
from pathlib import Path

# Add backend directory to path
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai.fine_tuning.dataset import DatasetValidator
from ai.fine_tuning.trainer import CSRNetFineTuner
from ai.fine_tuning.evaluator import CrowdEvaluator


def cmd_validate(args):
    print("=" * 70)
    print(" [1] Dataset Integrity & Leakage-Free Split Validation")
    print("=" * 70)
    items = DatasetValidator.scan_dataset(
        images_dir=args.images_dir,
        annotations_dir=args.annotations_dir,
        master_json=args.master_json
    )
    print(f"Verified image/annotation pairs found: {len(items)}")

    if getattr(args, "pairing_only", False):
        headcounts = [it["headcount"] for it in items]
        min_hc = min(headcounts) if headcounts else 0
        max_hc = max(headcounts) if headcounts else 0
        mean_hc = sum(headcounts) / len(headcounts) if headcounts else 0.0

        print(f"Pairing-Only Verification Mode Active:")
        print(f"  - Total verified pairs: {len(items)}")
        print(f"  - Headcount range:      min={min_hc}, max={max_hc}, mean={mean_hc:.1f}")
        print(f"  - Total annotated heads: {sum(headcounts)}")
        print(f"[PASS] PAIRING VERIFICATION SUCCESSFUL: All {len(items)} images paired with readable annotations.")

        if args.save_splits:
            out_p = Path(args.save_splits).resolve()
            out_p.parent.mkdir(parents=True, exist_ok=True)
            manifest = {
                "test": [{"image": it["image_path"].name, "headcount": it["headcount"], "group": it["event_group"]} for it in items],
                "total_samples": len(items)
            }
            with open(out_p, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            print(f"Saved verified dataset manifest to: {out_p}")
        return

    splits = DatasetValidator.partition_splits(
        items,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed
    )

    print(f"Partitioned Splits:")
    print(f"  - Train:      {len(splits['train'])} samples")
    print(f"  - Validation: {len(splits['val'])} samples")
    print(f"  - Test:       {len(splits['test'])} samples")

    # Verify event group separation (no leakage)
    train_groups = {it['event_group'] for it in splits['train']}
    val_groups = {it['event_group'] for it in splits['val']}
    test_groups = {it['event_group'] for it in splits['test']}

    leak_train_val = train_groups & val_groups
    leak_train_test = train_groups & test_groups
    leak_val_test = val_groups & test_groups

    if leak_train_val or leak_train_test or leak_val_test:
        print("[FAIL] DATA LEAKAGE DETECTED across event groups!")
        if leak_train_val:
            print(f"  Overlap between Train and Val ({len(leak_train_val)} groups): {list(leak_train_val)[:5]}")
        if leak_train_test:
            print(f"  Overlap between Train and Test ({len(leak_train_test)} groups): {list(leak_train_test)[:5]}")
        if leak_val_test:
            print(f"  Overlap between Val and Test ({len(leak_val_test)} groups): {list(leak_val_test)[:5]}")
        sys.exit(1)
    else:
        print("[PASS] ZERO DATA LEAKAGE: Event groups are strictly disjoint across all splits.")

    if args.save_splits:
        out_p = Path(args.save_splits).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            k: [{"image": it["image_path"].name, "headcount": it["headcount"], "group": it["event_group"]} for it in v]
            for k, v in splits.items()
        }
        with open(out_p, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2)
        print(f"Saved split metadata to: {out_p}")


def cmd_train(args):
    print("=" * 70)
    print(" [2] Memory-Conscious CSRNet Fine-Tuning Execution")
    print("=" * 70)
    items = DatasetValidator.scan_dataset(
        images_dir=args.images_dir,
        annotations_dir=args.annotations_dir,
        master_json=args.master_json
    )
    print(f"Verified dataset images found: {len(items)}")

    if getattr(args, "splits_file", None):
        splits_path = Path(args.splits_file).resolve()
        if not splits_path.is_file():
            raise FileNotFoundError(f"Splits file not found: {splits_path}")
        with open(splits_path, 'r', encoding='utf-8') as f:
            split_data = json.load(f)

        items_by_name = {it["image_path"].name: it for it in items}

        def _extract_names(entry_list):
            return [e["image"] if isinstance(e, dict) else e for e in entry_list]

        train_names = _extract_names(split_data.get("train", []))
        val_names = _extract_names(split_data.get("val", []))
        test_names = _extract_names(split_data.get("test", []))

        # Check for missing files
        missing_train = set(train_names) - set(items_by_name.keys())
        missing_val = set(val_names) - set(items_by_name.keys())
        if missing_train:
            raise FileNotFoundError(f"{len(missing_train)} train images from split file not found in images directory: {list(missing_train)[:5]}")
        if missing_val:
            raise FileNotFoundError(f"{len(missing_val)} validation images from split file not found in images directory: {list(missing_val)[:5]}")

        train_items = [items_by_name[n] for n in train_names if n in items_by_name]
        val_items = [items_by_name[n] for n in val_names if n in items_by_name]
        test_items = [items_by_name[n] for n in test_names if n in items_by_name]

        splits = {
            "train": train_items,
            "val": val_items,
            "test": test_items
        }
        print(f"Loaded exact splits from file: {splits_path.name}")
        print(f"  - Train:      {len(splits['train'])} samples")
        print(f"  - Validation: {len(splits['val'])} samples")
        print(f"  - Test:       {len(splits['test'])} samples")
    else:
        splits = DatasetValidator.partition_splits(
            items,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio,
            seed=args.seed
        )
        print(f"Partitioned splits on-the-fly:")
        print(f"  - Train:      {len(splits['train'])} samples")
        print(f"  - Validation: {len(splits['val'])} samples")
        print(f"  - Test:       {len(splits['test'])} samples")

    if not splits["train"]:
        print("[ERROR] Training dataset contains 0 items. Aborting training.")
        sys.exit(1)

    custom_cfg = {
        "optimizer": getattr(args, "optimizer", "sgd"),
        "learning_rate": args.lr,
        "momentum": getattr(args, "momentum", 0.95),
        "freeze_frontend_epochs": getattr(args, "freeze_frontend_epochs", 5),
        "early_stopping_patience": getattr(args, "patience", 5),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "accumulate_grad_batches": args.accum_steps,
        "max_image_size": args.max_size,
        "random_seed": args.seed,
    }

    tuner = CSRNetFineTuner(
        base_weights_path=args.base_weights,
        experiment_dir=args.experiment_dir,
        device=args.device,
        config=custom_cfg
    )

    try:
        results = tuner.fit(
            train_items=splits["train"],
            val_items=splits["val"],
            test_items=splits["test"]
        )
    finally:
        tuner.close()

    print(f"\n[DONE] Fine-tuning finished. Best Checkpoint saved in: {args.experiment_dir}")


def cmd_evaluate(args):
    print("=" * 70)
    print(" [3] Comparative Baseline vs Fine-Tuned Evaluation")
    print("=" * 70)
    items = DatasetValidator.scan_dataset(
        images_dir=args.test_images_dir,
        annotations_dir=args.test_annotations_dir,
        master_json=args.master_json
    )

    if not items:
        print(f"[ERROR] No valid annotated images found in '{args.test_images_dir}'.")
        print("Please check that image filenames match between the images directory and annotation file, and that verified counts are provided.")
        sys.exit(1)

    evaluator = CrowdEvaluator(device=args.device)
    comp = evaluator.compare_models(
        baseline_checkpoint=args.baseline_weights,
        finetuned_checkpoint=args.finetuned_weights,
        test_items=items,
        output_dir=args.output_dir
    )

    b = comp["comparison"]
    print(f"Test Samples: {comp['test_sample_count']}")
    print("-" * 50)
    print(f"Pretrained Baseline MAE:   {b['baseline_mae']:.2f} (Bias: {b['baseline_signed_error']:+.2f})")
    print(f"Fine-Tuned Checkpoint MAE: {b['finetuned_mae']:.2f} (Bias: {b['finetuned_signed_error']:+.2f}, Delta: {b['mae_delta']:+.2f})")
    print(f"Pretrained Baseline RMSE:  {b['baseline_rmse']:.2f}")
    print(f"Fine-Tuned Checkpoint RMSE:{b['finetuned_rmse']:.2f} (Delta: {b['rmse_delta']:+.2f})")
    print("-" * 50)
    if args.output_dir:
        out_path = Path(args.output_dir).resolve()
        print(f"Saved evaluation artifacts to: {out_path}")
        print(f"  - Full JSON report: {out_path / 'evaluation_results.json'}")
        print(f"  - Per-image CSV:    {out_path / 'evaluation_results.csv'}")
        print(f"  - Summary CSV:      {out_path / 'summary_metrics.csv'}")


def cmd_verify_annotations(args):
    print("=" * 70)
    print(" [4] Verify Direct Annotation Counts")
    print("=" * 70)
    counts = CrowdEvaluator.verify_annotation_counts(args.annotations_dir)
    print(f"Total annotation files scanned: {len(counts)}")
    for name, cnt in list(counts.items())[:20]:
        print(f"  - {name}: {cnt} annotated head centers")
    if len(counts) > 20:
        print(f"  ... and {len(counts) - 20} more.")


def main():
    parser = argparse.ArgumentParser(description="CSRNet Fine-Tuning & Evaluation CLI")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # Subcommand: validate-dataset
    val_p = subparsers.add_parser("validate-dataset", help="Validate image/annotation alignment and splits")
    val_p.add_argument("--images-dir", required=True, help="Directory containing crowd images")
    val_p.add_argument("--annotations-dir", default=None, help="Directory containing point annotations (.mat, .json, .csv)")
    val_p.add_argument("--master-json", default=None, help="Optional single master JSON file mapping image filename to point list")
    val_p.add_argument("--train-ratio", type=float, default=0.70)
    val_p.add_argument("--val-ratio", type=float, default=0.15)
    val_p.add_argument("--test-ratio", type=float, default=0.15)
    val_p.add_argument("--seed", type=int, default=42)
    val_p.add_argument("--save-splits", default=None, help="Path to save split JSON")
    val_p.add_argument("--pairing-only", action="store_true", help="Verify image/annotation pairing only without repartitioning splits (ideal for official test datasets)")
    val_p.set_defaults(func=cmd_validate)

    # Subcommand: train
    train_p = subparsers.add_parser("train", help="Fine-tune CSRNet on crowd dataset")
    train_p.add_argument("--images-dir", required=True)
    train_p.add_argument("--annotations-dir", default=None)
    train_p.add_argument("--master-json", default=None)
    train_p.add_argument("--base-weights", default="backend/ai/weights/shanghaitech_part_b.pth")
    train_p.add_argument("--experiment-dir", default="backend/ai/experiments/exp_01")
    train_p.add_argument("--optimizer", default="sgd", choices=["sgd", "adam"], help="Optimizer (default: sgd)")
    train_p.add_argument("--momentum", type=float, default=0.95, help="SGD momentum (default: 0.95)")
    train_p.add_argument("--lr", type=float, default=1e-6, help="Initial learning rate (default: 1e-6)")
    train_p.add_argument("--freeze-frontend-epochs", type=int, default=5, help="Epochs to freeze VGG-16 frontend (default: 5, 0 to disable)")
    train_p.add_argument("--patience", type=int, default=5, help="Early stopping patience in epochs (default: 5, 0 to disable)")
    train_p.add_argument("--epochs", type=int, default=20)
    train_p.add_argument("--batch-size", type=int, default=1)
    train_p.add_argument("--accum-steps", type=int, default=4)
    train_p.add_argument("--max-size", type=int, default=1024)
    train_p.add_argument("--seed", type=int, default=42)
    train_p.add_argument("--device", default=None)
    train_p.add_argument("--splits-file", default=None, help="Path to pre-computed train/val splits JSON")
    train_p.add_argument("--train-ratio", type=float, default=0.70)
    train_p.add_argument("--val-ratio", type=float, default=0.15)
    train_p.add_argument("--test-ratio", type=float, default=0.15)
    train_p.set_defaults(func=cmd_train)

    # Subcommand: evaluate
    eval_p = subparsers.add_parser("evaluate", help="Compare baseline vs fine-tuned model")
    eval_p.add_argument("--test-images-dir", required=True)
    eval_p.add_argument("--test-annotations-dir", default=None)
    eval_p.add_argument("--master-json", default=None)
    eval_p.add_argument("--baseline-weights", default="backend/ai/weights/shanghaitech_part_b.pth")
    eval_p.add_argument("--finetuned-weights", required=True)
    eval_p.add_argument("--output-dir", default="backend/ai/experiments/eval_report")
    eval_p.add_argument("--device", default=None)
    eval_p.set_defaults(func=cmd_evaluate)

    # Subcommand: verify-annotations
    ver_p = subparsers.add_parser("verify-annotations", help="Count annotated points directly from files")
    ver_p.add_argument("--annotations-dir", required=True)
    ver_p.set_defaults(func=cmd_verify_annotations)

    parsed = parser.parse_args()
    parsed.func(parsed)


if __name__ == "__main__":
    main()
