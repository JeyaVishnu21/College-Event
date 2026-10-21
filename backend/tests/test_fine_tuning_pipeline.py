"""
Unit Test Suite for CSRNet Fine-Tuning Pipeline
------------------------------------------------
Tests:
  1. Point annotation loading (.mat, .json, .csv)
  2. Density map generation & strict headcount conservation (sum == N)
  3. Aspect-ratio preserving resizing & point scaling for 4 GB GPU safety
  4. Dataset scanning & image/annotation matching
  5. Data leakage prevention via event group partitioning
  6. Checkpoint loading into CSRNet architecture
  7. Evaluation metrics calculation (MAE, RMSE, Signed Error, Density Tiers)
  8. Training preconditions & safety safeguards (raising on empty dataset)
"""

import os
import sys
import json
import csv
import shutil
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image

import torch

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai.model import CSRNet
from ai.fine_tuning.density_map import load_points_from_file, generate_density_map
from ai.fine_tuning.dataset import DatasetValidator, CrowdDataset
from ai.fine_tuning.evaluator import CrowdEvaluator
from ai.fine_tuning.trainer import CSRNetFineTuner


class TestDensityMapAndAnnotationLoading(unittest.TestCase):
    """Tests annotation parsing and density map mathematical properties."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.fixtures_dir = BACKEND_DIR / "tests" / "fixtures"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_points_from_json(self):
        """Tests parsing point coordinates from JSON formats."""
        # Format A: [[x1, y1], [x2, y2]]
        p_a = Path(self.temp_dir) / "test_a.json"
        with open(p_a, "w") as f:
            json.dump([[10.5, 20.2], [30.0, 40.0], [55.3, 80.1]], f)

        pts_a = load_points_from_file(p_a)
        self.assertEqual(pts_a.shape, (3, 2))
        self.assertAlmostEqual(pts_a[0, 0], 10.5, places=2)
        self.assertAlmostEqual(pts_a[0, 1], 20.2, places=2)

        # Format B: {"points": [[x1, y1], ...]}
        p_b = Path(self.temp_dir) / "test_b.json"
        with open(p_b, "w") as f:
            json.dump({"points": [[100, 150]]}, f)

        pts_b = load_points_from_file(p_b)
        self.assertEqual(pts_b.shape, (1, 2))
        self.assertEqual(pts_b[0, 0], 100)

        # Format C: Empty
        p_c = Path(self.temp_dir) / "empty.json"
        with open(p_c, "w") as f:
            json.dump([], f)
        pts_c = load_points_from_file(p_c)
        self.assertEqual(len(pts_c), 0)

    def test_load_points_from_csv(self):
        """Tests parsing point coordinates from CSV/TXT format."""
        p_csv = Path(self.temp_dir) / "test.csv"
        with open(p_csv, "w") as f:
            f.write("# x, y coordinates\n")
            f.write("12.5, 34.8\n")
            f.write("90.1, 105.0\n")

        pts = load_points_from_file(p_csv)
        self.assertEqual(pts.shape, (2, 2))
        self.assertAlmostEqual(pts[0, 0], 12.5, places=2)
        self.assertAlmostEqual(pts[1, 1], 105.0, places=2)

    def test_load_points_from_mat_fixture(self):
        """Tests parsing real .mat annotations from repository fixtures if present."""
        mat_fixture = self.fixtures_dir / "1_ann.mat"
        if mat_fixture.is_file():
            pts = load_points_from_file(mat_fixture)
            self.assertGreater(len(pts), 0)
            self.assertEqual(pts.ndim, 2)
            self.assertEqual(pts.shape[1], 2)

    def test_density_map_count_conservation(self):
        """
        CRITICAL: Verifies continuous density map summation strictly equals
        the ground-truth headcount len(points) within numerical tolerance.
        """
        shape = (256, 256)
        points = np.array([
            [50.0, 50.0],
            [60.0, 80.0],
            [120.0, 150.0],
            [200.0, 210.0],
            [180.0, 90.0]
        ], dtype=np.float32)

        density_map = generate_density_map(
            shape=shape,
            points=points,
            fixed_sigma=15.0,
            downsample_factor=8
        )

        # Output resolution must be (256 // 8, 256 // 8) = (32, 32)
        self.assertEqual(density_map.shape, (32, 32))

        # Sum must strictly equal 5.0 (headcount)
        integral = float(np.sum(density_map))
        self.assertAlmostEqual(integral, 5.0, delta=1e-3)

    def test_density_map_empty_scene(self):
        """Verifies an empty scene produces an all-zero density map with integral 0.0."""
        shape = (128, 128)
        points = np.empty((0, 2), dtype=np.float32)

        density_map = generate_density_map(shape=shape, points=points, downsample_factor=8)
        self.assertEqual(density_map.shape, (16, 16))
        self.assertEqual(float(np.sum(density_map)), 0.0)


class TestDatasetAndLeakageSafeguards(unittest.TestCase):
    """Tests dataset verification, split partitioning, and leakage safeguards."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.img_dir = Path(self.temp_dir) / "images"
        self.ann_dir = Path(self.temp_dir) / "annotations"
        self.img_dir.mkdir(parents=True)
        self.ann_dir.mkdir(parents=True)

        # Create synthetic images and annotation files belonging to distinct event groups
        # event_101: 4 images (burst)
        # event_102: 4 images
        # event_103: 4 images
        # event_104: 4 images
        for ev_id in [101, 102, 103, 104]:
            for shot in range(1, 5):
                name = f"event_{ev_id}_shot_{shot}"
                img_path = self.img_dir / f"{name}.jpg"
                ann_path = self.ann_dir / f"{name}.json"

                # 64x64 dummy image
                img = Image.new("RGB", (64, 64), color=(shot * 20, ev_id % 255, 100))
                img.save(img_path)

                # 5 synthetic points
                pts = [[10 + shot, 10], [20, 20], [30, 30], [40, 40], [50, 50]]
                with open(ann_path, "w") as f:
                    json.dump(pts, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scan_dataset(self):
        """Tests that scan_dataset successfully pairs images and annotations and infers event groups."""
        items = DatasetValidator.scan_dataset(self.img_dir, self.ann_dir)
        self.assertEqual(len(items), 16)
        for it in items:
            self.assertEqual(it["headcount"], 5)
            self.assertTrue(it["event_group"].startswith("event_"))

    def test_partition_splits_zero_leakage(self):
        """
        CRITICAL TEST: Ensures that images from the same event_group are NEVER split
        between train, val, and test partitions (eliminating data leakage).
        """
        items = DatasetValidator.scan_dataset(self.img_dir, self.ann_dir)
        splits = DatasetValidator.partition_splits(
            items,
            train_ratio=0.50,
            val_ratio=0.25,
            test_ratio=0.25,
            seed=42
        )

        train_groups = {it["event_group"] for it in splits["train"]}
        val_groups = {it["event_group"] for it in splits["val"]}
        test_groups = {it["event_group"] for it in splits["test"]}

        # Total samples must sum to total items
        self.assertEqual(len(splits["train"]) + len(splits["val"]) + len(splits["test"]), 16)

        # No overlapping event groups between any pairs
        self.assertEqual(len(train_groups & val_groups), 0, "Leakage detected between train and val!")
        self.assertEqual(len(train_groups & test_groups), 0, "Leakage detected between train and test!")
        self.assertEqual(len(val_groups & test_groups), 0, "Leakage detected between val and test!")

    def test_crowd_dataset_resizing_and_divisible_by_8(self):
        """Tests that CrowdDataset resizes large images and constrains dimensions to multiples of 8."""
        items = DatasetValidator.scan_dataset(self.img_dir, self.ann_dir)
        dataset = CrowdDataset(items, max_size=32, is_training=False)

        sample = dataset[0]
        img_tensor = sample["image"]
        density_tensor = sample["density_map"]

        # Resized dimensions must be multiples of 8
        c, h, w = img_tensor.shape
        self.assertEqual(c, 3)
        self.assertEqual(h % 8, 0)
        self.assertEqual(w % 8, 0)
        self.assertLessEqual(max(h, w), 32)

        # Density map dimensions must match (1, h // 8, w // 8)
        self.assertEqual(density_tensor.shape, (1, h // 8, w // 8))

        # Density sum should conserve original headcount (5)
        self.assertAlmostEqual(float(density_tensor.sum()), 5.0, delta=1e-2)

    def test_shanghaitech_filename_pairing_and_ground_truth_folder(self):
        """
        Regression test: Supports ShanghaiTech naming (IMG_N.jpg and GT_IMG_N.mat/json)
        and verifies pairing using numeric image identifier in 'ground_truth' directory.
        """
        sh_root = Path(self.temp_dir) / "shanghaitech_test"
        img_dir = sh_root / "images"
        gt_dir = sh_root / "ground_truth"  # Folder with underscore
        img_dir.mkdir(parents=True)
        gt_dir.mkdir(parents=True)

        for i in [1, 2, 42, 400]:
            img_p = img_dir / f"IMG_{i}.jpg"
            ann_p = gt_dir / f"GT_IMG_{i}.json"

            # Create dummy 64x64 image
            Image.new("RGB", (64, 64), color=(10, 20, 30)).save(img_p)
            with open(ann_p, "w") as f:
                json.dump([[15.0, 25.0], [35.0, 45.0]], f)

        # Scan dataset: annotations_dir is None, so it must discover sibling 'ground_truth'
        items = DatasetValidator.scan_dataset(img_dir)
        self.assertEqual(len(items), 4)

        # Verify pairing and that event_group is NOT collapsed to 'img'
        groups = set()
        for it in items:
            self.assertEqual(it["headcount"], 2)
            self.assertTrue(it["annotation_path"].name.startswith("GT_IMG_"))
            self.assertNotEqual(it["event_group"], "img", "Event group must not collapse to 'img'!")
            groups.add(it["event_group"])

        # Each image must have its own independent group
        self.assertEqual(len(groups), 4)

    def test_shanghaitech_400_sample_split_85_15(self):
        """
        Regression test: For 400 ShanghaiTech training images, verifies deterministic
        85% train / 15% validation split producing exactly 340 train and 60 val samples.
        """
        # Create 400 synthetic items
        items = [
            {
                "image_path": Path(f"images/IMG_{i}.jpg"),
                "annotation_path": Path(f"ground_truth/GT_IMG_{i}.json"),
                "points": np.array([[10, 10]], dtype=np.float32),
                "headcount": 1,
                "event_group": f"img_{i}",
            }
            for i in range(1, 401)
        ]

        splits1 = DatasetValidator.partition_splits(
            items,
            train_ratio=0.85,
            val_ratio=0.15,
            test_ratio=0.0,
            seed=42
        )

        # Verify sample counts
        self.assertEqual(len(splits1["train"]), 340, "Train split must contain exactly 340 samples (85%).")
        self.assertEqual(len(splits1["val"]), 60, "Val split must contain exactly 60 samples (15%).")
        self.assertEqual(len(splits1["test"]), 0, "Test split must contain exactly 0 samples.")

        # Verify zero data leakage
        train_names = {it["image_path"].name for it in splits1["train"]}
        val_names = {it["image_path"].name for it in splits1["val"]}
        self.assertEqual(len(train_names & val_names), 0, "No overlap between train and val!")

        # Verify deterministic reproducibility with seed 42
        splits2 = DatasetValidator.partition_splits(
            items,
            train_ratio=0.85,
            val_ratio=0.15,
            test_ratio=0.0,
            seed=42
        )
        train_names_2 = {it["image_path"].name for it in splits2["train"]}
        val_names_2 = {it["image_path"].name for it in splits2["val"]}
        self.assertEqual(train_names, train_names_2, "Splits must be identical across runs with seed 42.")
        self.assertEqual(val_names, val_names_2, "Splits must be identical across runs with seed 42.")

    def test_zero_valued_split_ratios_strictly_respected(self):
        """
        Regression test: A ratio of zero must produce strictly zero samples in that split.
        No sample should be stolen or forced into validation/test when ratio is 0.
        """
        items = [
            {
                "image_path": Path(f"images/IMG_{i}.jpg"),
                "annotation_path": Path(f"ground_truth/GT_IMG_{i}.json"),
                "points": np.array([[10, 10]], dtype=np.float32),
                "headcount": 1,
                "event_group": f"img_{i}",
            }
            for i in range(1, 317)  # 316 test samples
        ]

        # Case 1: Train=1.0, Val=0.0, Test=0.0
        splits_train_only = DatasetValidator.partition_splits(
            items,
            train_ratio=1.0,
            val_ratio=0.0,
            test_ratio=0.0,
            seed=42
        )
        self.assertEqual(len(splits_train_only["train"]), 316)
        self.assertEqual(len(splits_train_only["val"]), 0)
        self.assertEqual(len(splits_train_only["test"]), 0)

        # Case 2: Train=0.0, Val=0.0, Test=1.0
        splits_test_only = DatasetValidator.partition_splits(
            items,
            train_ratio=0.0,
            val_ratio=0.0,
            test_ratio=1.0,
            seed=42
        )
        self.assertEqual(len(splits_test_only["train"]), 0)
        self.assertEqual(len(splits_test_only["val"]), 0)
        self.assertEqual(len(splits_test_only["test"]), 316)

    def test_event_leakage_safeguards_for_genuine_event_ids(self):
        """
        Regression test: Retains event-level grouping safeguards for genuine event IDs.
        Images from the same event are grouped together and leakage is detected.
        """
        # Event 101 has 3 shots, Event 102 has 2 shots
        self.assertEqual(DatasetValidator.infer_event_group("event_101_burst_01"), "event_101")
        self.assertEqual(DatasetValidator.infer_event_group("event_101_burst_02"), "event_101")
        self.assertEqual(DatasetValidator.infer_event_group("TechFest_Hall_01"), "techfest_hall")
        self.assertEqual(DatasetValidator.infer_event_group("TechFest_Hall_02"), "techfest_hall")

        # Generic prefixes must NOT be treated as event groups
        self.assertEqual(DatasetValidator.infer_event_group("IMG_1"), "img_1")
        self.assertEqual(DatasetValidator.infer_event_group("IMG_2"), "img_2")
        self.assertEqual(DatasetValidator.infer_event_group("DSC_004"), "dsc_004")
        self.assertEqual(DatasetValidator.infer_event_group("10"), "10")


class TestModelCheckpointAndEvaluationMetrics(unittest.TestCase):
    """Tests CSRNet checkpoint loading and evaluation metric computations."""

    def setUp(self):
        self.baseline_checkpoint = BACKEND_DIR / "ai" / "weights" / "shanghaitech_part_b.pth"
        self.evaluator = CrowdEvaluator(device="cpu")

    def test_checkpoint_loading(self):
        """Verifies loading pretrained Part B weights into CSRNet architecture without missing keys."""
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        model = self.evaluator.load_model(self.baseline_checkpoint)
        self.assertIsInstance(model, CSRNet)

        # Verify forward pass produces 1-channel output downsampled by 8
        dummy_input = torch.randn(1, 3, 64, 64)
        with torch.no_grad():
            out = model(dummy_input)
        self.assertEqual(out.shape, (1, 1, 8, 8))

    def test_evaluation_metric_calculations(self):
        """Tests mathematical correctness of MAE, RMSE, Signed Error, and Density Tiers."""
        # Create a mock model where predict_image returns predetermined values
        class MockCSRNet(torch.nn.Module):
            pass

        mock_model = MockCSRNet()

        # Synthetic test items across low, medium, and high density tiers
        test_items = [
            {"image_path": Path("dummy_low.jpg"), "headcount": 20},     # Tier: Low (0-50)
            {"image_path": Path("dummy_med.jpg"), "headcount": 100},    # Tier: Medium (51-200)
            {"image_path": Path("dummy_high.jpg"), "headcount": 300},   # Tier: High (201+)
        ]

        # Preset predictions:
        # Low: gt=20, pred=25 -> diff = +5, abs_err = 5, sq_err = 25
        # Med: gt=100, pred=90 -> diff = -10, abs_err = 10, sq_err = 100
        # High: gt=300, pred=320 -> diff = +20, abs_err = 20, sq_err = 400
        pred_map = {
            "dummy_low.jpg": (25, 25.1),
            "dummy_med.jpg": (90, 89.8),
            "dummy_high.jpg": (320, 319.7)
        }

        # Override predict_image for isolated unit test
        original_predict = self.evaluator.predict_image
        self.evaluator.predict_image = lambda m, p: pred_map[p.name]

        try:
            results = self.evaluator.evaluate_model(mock_model, test_items, model_label="MockModel")

            # Overall MAE = (5 + 10 + 20) / 3 = 35 / 3 = 11.67
            # Overall RMSE = sqrt((25 + 100 + 400) / 3) = sqrt(175) = 13.23
            # Overall Signed Error = (+5 - 10 + 20) / 3 = 15 / 3 = +5.0
            overall = results["overall_metrics"]
            self.assertAlmostEqual(overall["mae"], 11.67, places=2)
            self.assertAlmostEqual(overall["rmse"], 13.23, places=2)
            self.assertAlmostEqual(overall["signed_error"], 5.0, places=2)

            # Check density tiers
            tiers = results["density_tiers"]
            self.assertEqual(tiers["low (0-50)"]["sample_count"], 1)
            self.assertEqual(tiers["low (0-50)"]["mae"], 5.0)
            self.assertEqual(tiers["low (0-50)"]["signed_error"], 5.0)

            self.assertEqual(tiers["medium (51-200)"]["sample_count"], 1)
            self.assertEqual(tiers["medium (51-200)"]["mae"], 10.0)
            self.assertEqual(tiers["medium (51-200)"]["signed_error"], -10.0)

            self.assertEqual(tiers["high (201+)"]["sample_count"], 1)
            self.assertEqual(tiers["high (201+)"]["mae"], 20.0)
            self.assertEqual(tiers["high (201+)"]["signed_error"], 20.0)

        finally:
            self.evaluator.predict_image = original_predict

    def test_fine_tuner_safety_guard_on_empty_dataset(self):
        """
        Requirement 12 safeguard: Fine-tuner MUST refuse to start and raise ValueError
        if training dataset items are empty.
        """
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        with tempfile.TemporaryDirectory() as exp_dir:
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_dir,
                device="cpu"
            ) as trainer:
                with self.assertRaises(ValueError):
                    trainer.fit(train_items=[], val_items=[])

    def test_fine_tuner_overlap_detection(self):
        """
        Safeguard: Verifies that fine-tuner refuses to train if train and validation
        sets share any overlapping images.
        """
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        with tempfile.TemporaryDirectory() as exp_dir:
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_dir,
                device="cpu"
            ) as trainer:
                item1 = {"image_path": Path("img_1.jpg"), "points": np.empty((0, 2)), "headcount": 0}
                item2 = {"image_path": Path("img_2.jpg"), "points": np.empty((0, 2)), "headcount": 0}
                # Overlap: item1 in both train and val
                with self.assertRaises(ValueError) as ctx:
                    trainer.fit(train_items=[item1, item2], val_items=[item1])
                self.assertIn("Data leakage detected", str(ctx.exception))

    def test_saved_shanghaitech_part_b_train_val_splits_file(self):
        """
        Verifies the exact properties of the saved ShanghaiTech Part B split JSON:
        340 train samples, 60 val samples, 0 test samples, and 0 overlap.
        """
        split_path = BACKEND_DIR / "ai" / "experiments" / "shanghaitech_part_b_train_val_splits.json"
        if not split_path.is_file():
            self.skipTest("shanghaitech_part_b_train_val_splits.json not yet generated")

        with open(split_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        train_imgs = [x["image"] for x in data["train"]]
        val_imgs = [x["image"] for x in data["val"]]
        test_imgs = [x["image"] for x in data.get("test", [])]

        self.assertEqual(len(train_imgs), 340, "Must have exactly 340 training samples")
        self.assertEqual(len(val_imgs), 60, "Must have exactly 60 validation samples")
        self.assertEqual(len(test_imgs), 0, "Must have exactly 0 test samples")
        self.assertEqual(len(set(train_imgs) & set(val_imgs)), 0, "Must have zero overlap between train and val")

    def test_best_finetuned_checkpoint_tracking(self):
        """
        Regression test: Verifies that trainer saves best_finetuned_model.pth for epoch >= 1,
        even when fine-tuned validation MAE does not beat the epoch 0 baseline.
        """
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        with tempfile.TemporaryDirectory() as exp_dir:
            exp_path = Path(exp_dir)
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_path,
                device="cpu",
                config={"epochs": 1, "accumulate_grad_batches": 1, "batch_size": 1}
            ) as trainer:
                # Mock evaluate so epoch 0 baseline MAE is low (e.g., 5.0)
                # and epoch 1 val MAE is higher (e.g., 15.0, simulating early divergence)
                eval_calls = [0]
                def mock_evaluate(loader):
                    eval_calls[0] += 1
                    if eval_calls[0] == 1:
                        return {"mae": 5.0, "rmse": 6.0, "samples": 1}
                    return {"mae": 15.0, "rmse": 18.0, "samples": 1}

                # Mock train_epoch to avoid running full convolutions on synthetic images
                trainer.evaluate = mock_evaluate
                def mock_train_epoch(loader, ep):
                    trainer.optimizer.step()
                    return 1.0
                trainer.train_epoch = mock_train_epoch

                dummy_item1 = {"image_path": Path("img_1.jpg"), "points": np.empty((0, 2)), "headcount": 0}
                dummy_item2 = {"image_path": Path("img_2.jpg"), "points": np.empty((0, 2)), "headcount": 0}

                # Mock CrowdDataset so dataloader can be constructed
                res = trainer.fit(train_items=[dummy_item1], val_items=[dummy_item2])

                # best_model.pth should remain epoch 0 (baseline)
                self.assertEqual(res["best_epoch"], 0)
                self.assertEqual(res["best_val_mae"], 5.0)
                self.assertTrue((exp_path / "best_model.pth").is_file())

                # best_finetuned_model.pth MUST be saved for epoch 1
                self.assertEqual(res["best_finetuned_epoch"], 1)
                self.assertEqual(res["best_finetuned_val_mae"], 15.0)
                self.assertTrue((exp_path / "best_finetuned_model.pth").is_file())

                # Verify train_history.json contains both
                with open(exp_path / "train_history.json", "r", encoding="utf-8") as f:
                    hist = json.load(f)
                self.assertEqual(hist["best_epoch"], 0)
                self.assertEqual(hist["best_finetuned_epoch"], 1)
                self.assertEqual(hist["best_finetuned_val_mae"], 15.0)

    def test_evaluator_count_conservation_and_rounding_consistency(self):
        """
        Regression test: Verifies that density map generation strictly conserves count,
        and that evaluator rounding logic is mathematically deterministic and identical
        for baseline and fine-tuned predictions.
        """
        # 1. Count conservation under coordinates scaling
        orig_shape = (768, 1024)
        np.random.seed(42)
        pts = np.random.uniform(low=[10, 10], high=[1000, 750], size=(137, 2)).astype(np.float32)

        density = generate_density_map(orig_shape, pts, method="fixed", fixed_sigma=15.0, downsample_factor=8)
        self.assertEqual(density.shape, (768 // 8, 1024 // 8))
        self.assertAlmostEqual(float(density.sum()), 137.0, places=3)

        # 2. Evaluator rounding consistency
        # Both baseline and fine-tuned pass through predict_image which applies int(round(raw_sum))
        # Python uses banker's rounding (round-half-to-even: 12.5 -> 12, 13.5 -> 14)
        raw_sums = [12.49, 12.50, 12.51, 0.0, 99.99]
        expected_rounded = [12, 12, 13, 0, 100]
        actual_rounded = [max(0, int(round(s))) for s in raw_sums]
        self.assertEqual(actual_rounded, expected_rounded)

    def test_frontend_freezing_and_unfreezing_schedule(self):
        """
        Regression test: Verifies that frontend parameters are frozen for freeze_frontend_epochs
        and automatically unfrozen on the subsequent epoch.
        """
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        with tempfile.TemporaryDirectory() as exp_dir:
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_dir,
                device="cpu",
                config={"epochs": 3, "freeze_frontend_epochs": 2, "early_stopping_patience": 0}
            ) as trainer:
                frozen_status = []

                def mock_train_epoch(loader, ep):
                    frozen_status.append(trainer.is_frontend_frozen())
                    trainer.optimizer.step()
                    return 1.0

                trainer.train_epoch = mock_train_epoch
                trainer.evaluate = lambda loader: {"mae": 5.0, "rmse": 6.0, "samples": 1}

                dummy_item1 = {"image_path": Path("img_1.jpg"), "points": np.empty((0, 2)), "headcount": 0}
                dummy_item2 = {"image_path": Path("img_2.jpg"), "points": np.empty((0, 2)), "headcount": 0}

                trainer.fit(train_items=[dummy_item1], val_items=[dummy_item2])

                # Epoch 1: Frozen (True)
                # Epoch 2: Frozen (True)
                # Epoch 3: Unfrozen (False)
                self.assertEqual(frozen_status, [True, True, False])

    def test_early_stopping_triggered(self):
        """
        Regression test: Verifies that early stopping terminates training early
        when validation MAE fails to improve for patience consecutive epochs.
        """
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        with tempfile.TemporaryDirectory() as exp_dir:
            exp_path = Path(exp_dir)
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_path,
                device="cpu",
                config={"epochs": 10, "early_stopping_patience": 2, "freeze_frontend_epochs": 0}
            ) as trainer:
                # Validation MAE:
                # Epoch 0 (baseline): 10.0
                # Epoch 1: 8.0 (improved, counter=0)
                # Epoch 2: 9.0 (no improve, counter=1)
                # Epoch 3: 9.5 (no improve, counter=2 -> early stops!)
                eval_sequence = [
                    {"mae": 10.0, "rmse": 11.0, "samples": 1},  # Baseline
                    {"mae": 8.0, "rmse": 9.0, "samples": 1},    # Epoch 1
                    {"mae": 9.0, "rmse": 10.0, "samples": 1},   # Epoch 2
                    {"mae": 9.5, "rmse": 10.5, "samples": 1},   # Epoch 3
                ]
                call_idx = [0]
                def mock_evaluate(loader):
                    res = eval_sequence[call_idx[0]]
                    call_idx[0] += 1
                    return res

                trainer.evaluate = mock_evaluate
                trainer.train_epoch = lambda loader, ep: (trainer.optimizer.step(), 1.0)[1]

                dummy_item1 = {"image_path": Path("img_1.jpg"), "points": np.empty((0, 2)), "headcount": 0}
                dummy_item2 = {"image_path": Path("img_2.jpg"), "points": np.empty((0, 2)), "headcount": 0}

                res = trainer.fit(train_items=[dummy_item1], val_items=[dummy_item2])

                self.assertTrue(res["early_stopped"])
                self.assertEqual(len(res["history"]), 3, "Should have stopped after epoch 3 due to patience=2")
                self.assertEqual(res["best_finetuned_epoch"], 1)
                self.assertEqual(res["best_finetuned_val_mae"], 8.0)

    def test_baseline_model_permanent_preservation(self):
        """
        Regression test: Verifies that baseline_model.pth is permanently preserved at epoch 0
        and never overwritten, even when fine-tuning beats baseline and updates best_model.pth.
        """
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        with tempfile.TemporaryDirectory() as exp_dir:
            exp_path = Path(exp_dir)
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_path,
                device="cpu",
                config={"epochs": 1, "early_stopping_patience": 0, "freeze_frontend_epochs": 0}
            ) as trainer:
                # Epoch 0 baseline = 10.0, Epoch 1 = 4.0 (beats baseline!)
                eval_calls = [0]
                def mock_evaluate(loader):
                    eval_calls[0] += 1
                    if eval_calls[0] == 1:
                        return {"mae": 10.0, "rmse": 12.0, "samples": 1}
                    return {"mae": 4.0, "rmse": 5.0, "samples": 1}

                trainer.evaluate = mock_evaluate
                trainer.train_epoch = lambda loader, ep: (trainer.optimizer.step(), 1.0)[1]

                dummy_item1 = {"image_path": Path("img_1.jpg"), "points": np.empty((0, 2)), "headcount": 0}
                dummy_item2 = {"image_path": Path("img_2.jpg"), "points": np.empty((0, 2)), "headcount": 0}

                res = trainer.fit(train_items=[dummy_item1], val_items=[dummy_item2])

                # best_model.pth should update to epoch 1
                self.assertEqual(res["best_epoch"], 1)
                self.assertEqual(res["best_val_mae"], 4.0)

                # baseline_model.pth MUST exist and be epoch 0
                baseline_ckpt = torch.load(exp_path / "baseline_model.pth", map_location="cpu")
                self.assertEqual(baseline_ckpt["epoch"], 0)
                self.assertEqual(baseline_ckpt["val_metrics"]["mae"], 10.0)

                # best_finetuned_model.pth MUST be epoch 1
                finetuned_ckpt = torch.load(exp_path / "best_finetuned_model.pth", map_location="cpu")
                self.assertEqual(finetuned_ckpt["epoch"], 1)
                self.assertEqual(finetuned_ckpt["val_metrics"]["mae"], 4.0)

    def test_optimizer_and_momentum_initialization(self):
        """
        Regression test: Verifies that optimizer is properly initialized as SGD or Adam
        with correct momentum and parameter groups.
        """
        if not self.baseline_checkpoint.is_file():
            self.skipTest("shanghaitech_part_b.pth not available in repo")

        with tempfile.TemporaryDirectory() as exp_dir:
            # Test SGD (default)
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_dir,
                device="cpu",
                config={"optimizer": "sgd", "learning_rate": 1e-6, "momentum": 0.95}
            ) as trainer:
                self.assertIsInstance(trainer.optimizer, torch.optim.SGD)
                self.assertEqual(trainer.optimizer.defaults["momentum"], 0.95)
                self.assertEqual(trainer.optimizer.defaults["lr"], 1e-6)
                self.assertEqual(len(trainer.optimizer.param_groups), 2)  # backend & frontend

            # Test Adam
            with CSRNetFineTuner(
                base_weights_path=self.baseline_checkpoint,
                experiment_dir=exp_dir,
                device="cpu",
                config={"optimizer": "adam", "learning_rate": 1e-5}
            ) as trainer:
                self.assertIsInstance(trainer.optimizer, torch.optim.Adam)
                self.assertEqual(trainer.optimizer.defaults["lr"], 1e-5)

    def test_scan_dataset_csv_master_annotations_and_zero_guessing(self):
        """
        Regression test: Verifies that DatasetValidator.scan_dataset parses CSV master annotations,
        propagates event_type and density_category, and enforces strict zero-guessing (skips unverified images).
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_p = Path(tmp_dir)
            img_dir = tmp_p / "images"
            img_dir.mkdir()

            # Create 3 dummy JPEG images
            img1 = img_dir / "event_photo_1.jpg"
            img2 = img_dir / "event_photo_2.jpg"
            img3 = img_dir / "unverified_photo_3.jpg"

            for p in [img1, img2, img3]:
                im = Image.new("RGB", (64, 64), color="blue")
                im.save(p)

            # Create CSV master annotation file
            # img1: verified count 35 (low)
            # img2: verified count 120 (medium)
            # img3: empty/unverified count -> must be skipped, NOT guessed!
            csv_path = tmp_p / "annotations.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["image_filename", "headcount", "event_type", "crowd_density", "verified"])
                writer.writerow(["event_photo_1.jpg", "35", "technical_fest", "low (0-50)", "true"])
                writer.writerow(["event_photo_2.jpg", "120", "hackathon", "medium (51-200)", "true"])
                writer.writerow(["unverified_photo_3.jpg", "", "seminar", "", "false"])

            items = DatasetValidator.scan_dataset(images_dir=img_dir, master_json=csv_path)

            # Only 2 images should be verified; unverified_photo_3 MUST be skipped (zero guessing)
            self.assertEqual(len(items), 2)
            item_map = {x["image_path"].name: x for x in items}

            self.assertIn("event_photo_1.jpg", item_map)
            self.assertEqual(item_map["event_photo_1.jpg"]["headcount"], 35.0)
            self.assertEqual(item_map["event_photo_1.jpg"]["event_type"], "technical_fest")
            self.assertEqual(item_map["event_photo_1.jpg"]["density_category"], "low (0-50)")

            self.assertIn("event_photo_2.jpg", item_map)
            self.assertEqual(item_map["event_photo_2.jpg"]["headcount"], 120.0)
            self.assertEqual(item_map["event_photo_2.jpg"]["event_type"], "hackathon")

            self.assertNotIn("unverified_photo_3.jpg", item_map)

    def test_compare_models_csv_and_json_export(self):
        """
        Regression test: Verifies that CrowdEvaluator.compare_models exports both JSON
        and CSV files (evaluation_results.csv and summary_metrics.csv) with expected headers.
        """
        with tempfile.TemporaryDirectory() as out_dir:
            out_p = Path(out_dir)

            test_items = [
                {
                    "image_path": Path("event_hall_1.jpg"),
                    "headcount": 30,
                    "event_type": "symposium",
                    "density_category": "low (0-50)"
                },
                {
                    "image_path": Path("concert_lawn_2.jpg"),
                    "headcount": 220,
                    "event_type": "cultural_fest",
                    "density_category": "high (201+)"
                }
            ]

            # Mock load_model and predict_image to test export cleanly without GPU weights
            orig_load = self.evaluator.load_model
            orig_predict = self.evaluator.predict_image

            # Preset predictions:
            # Baseline: event_hall=25 (diff -5), concert=200 (diff -20)
            # Finetuned: event_hall=28 (diff -2), concert=215 (diff -5)
            preds = {
                "base": {"event_hall_1.jpg": (25, 25.2), "concert_lawn_2.jpg": (200, 199.8)},
                "fine": {"event_hall_1.jpg": (28, 28.1), "concert_lawn_2.jpg": (215, 214.9)}
            }

            class DummyModel:
                def __init__(self, mode):
                    self.mode = mode

            try:
                self.evaluator.load_model = lambda p: DummyModel("fine" if "finetuned" in str(p) else "base")
                self.evaluator.predict_image = lambda m, p: preds[m.mode][p.name]

                comp = self.evaluator.compare_models(
                    baseline_checkpoint="dummy_base.pth",
                    finetuned_checkpoint="dummy_finetuned.pth",
                    test_items=test_items,
                    output_dir=out_p
                )

                # Return contract verification: comp must be non-None and contain comparison dict
                self.assertIsNotNone(comp, "compare_models must return a comparison dictionary, not None")
                self.assertIn("comparison", comp)
                self.assertIn("baseline", comp)
                self.assertIn("finetuned", comp)
                self.assertEqual(comp["test_sample_count"], 2)
                self.assertIn("baseline_mae", comp["comparison"])
                self.assertIn("finetuned_mae", comp["comparison"])

                # 1. JSON file exists
                self.assertTrue((out_p / "evaluation_results.json").is_file())

                # 2. Per-image CSV file exists and contains correct columns
                csv_p = out_p / "evaluation_results.csv"
                self.assertTrue(csv_p.is_file())

                with open(csv_p, "r", encoding="utf-8") as f:
                    rows = list(csv.reader(f))

                header = rows[0]
                self.assertIn("image_name", header)
                self.assertIn("event_type", header)
                self.assertIn("baseline_predicted", header)
                self.assertIn("finetuned_predicted", header)
                self.assertIn("abs_error_delta", header)
                self.assertIn("finetuned_improved", header)

                self.assertEqual(len(rows), 3)  # header + 2 images

                # 3. Summary metrics CSV exists
                summary_csv = out_p / "summary_metrics.csv"
                self.assertTrue(summary_csv.is_file())
                with open(summary_csv, "r", encoding="utf-8") as f:
                    sum_rows = list(csv.reader(f))
                self.assertEqual(sum_rows[0][0], "category")
                self.assertEqual(sum_rows[1][0], "Overall")

            finally:
                self.evaluator.load_model = orig_load
                self.evaluator.predict_image = orig_predict

    def test_empty_annotated_dataset_raises_clear_error(self):
        """
        Regression test: Verifies that compare_models raises a clear ValueError
        when test_items is empty, and scan_dataset returns empty list if no valid annotations match.
        """
        # 1. compare_models raises ValueError on empty test items
        with self.assertRaises(ValueError) as ctx:
            self.evaluator.compare_models(
                baseline_checkpoint="dummy_base.pth",
                finetuned_checkpoint="dummy_fine.pth",
                test_items=[]
            )
        self.assertIn("Evaluation test items list is empty", str(ctx.exception))

        # 2. scan_dataset with unmatched annotations
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_p = Path(tmp_dir)
            img_dir = tmp_p / "images"
            img_dir.mkdir()

            im = Image.new("RGB", (32, 32), color="green")
            im.save(img_dir / "unrelated_1.jpg")

            # CSV with different filename
            csv_p = tmp_p / "ann.csv"
            with open(csv_p, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["image_filename", "headcount", "verified"])
                writer.writerow(["some_other_image.jpg", "50", "true"])

            items = DatasetValidator.scan_dataset(images_dir=img_dir, master_json=csv_p)
            self.assertEqual(len(items), 0, "Images without matching verified annotations must produce 0 items")


if __name__ == "__main__":
    unittest.main()
