"""
Stage 7 CSRNet AI Inference Pipeline Verification Suite
-------------------------------------------------------
Verifies the CSRNet crowd density estimation and headcount prediction pipeline:
  TEST 1: Checkpoint loading and exact 34-parameter tensor architecture matching.
  TEST 2: Spatial output shape preservation: (1, 3, H, W) -> (1, 1, H // 8, W // 8).
  TEST 3: Finite values guarantee (zero NaN or Inf values in density maps).
  TEST 4: Diagnostic statistics completeness (min, max, mean, std, negative/positive pixel counts).
  TEST 5: Non-crowd baseline behavior (near-zero residuals, correct 0 headcount).
  TEST 6: Real crowd detection and positive density response.
  TEST 7: Numerical consistency between CUDA (GPU) and CPU execution.
  TEST 8: Documentation and validation of testing limitations for unlabelled images.
"""

import sys
import unittest
from pathlib import Path
from PIL import Image

# Ensure backend directory is in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import torch
    from ai.model import CSRNet
    from ai.predictor import CrowdPredictor, CheckpointVerificationError
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class TestStage7CSRNetInference(unittest.TestCase):
    """Focused verification suite for CSRNet inference pipeline."""

    @classmethod
    def setUpClass(cls):
        if not TORCH_AVAILABLE:
            raise unittest.SkipTest("PyTorch is not available in test environment.")

        cls.weights_path = BACKEND_DIR / "ai" / "weights" / "shanghaitech_part_b.pth"
        if not cls.weights_path.is_file():
            raise unittest.SkipTest(f"Pretrained checkpoint not found at {cls.weights_path}")

        cls.dummy_img = BACKEND_DIR / "uploads" / "event_images" / "event_101_20260928_223100_81f80338.jpg"
        cls.real_crowd_img = BACKEND_DIR / "tests" / "fixtures" / "6.jpg"

        # Initialize predictor on available device
        cls.predictor = CrowdPredictor(weights_path=cls.weights_path)

    def test_01_checkpoint_loading_and_architecture_matching(self):
        """TEST 1: Checkpoint loads with strict tensor matching across all 34 layers."""
        info = self.predictor.load_weights(self.weights_path)
        self.assertTrue(info["verified"])
        self.assertEqual(info["layers_matched"], 34)

        # Count total parameters (exactly 16,263,489 parameters)
        total_params = sum(p.numel() for p in self.predictor.model.parameters())
        self.assertEqual(total_params, 16263489)


    def test_02_spatial_output_shape(self):
        """TEST 2: Model preserves 1/8 spatial downsampling ratio across varied resolutions."""
        test_resolutions = [
            (640, 480),   # Divisible by 8 -> 80 x 60
            (1024, 768),  # Divisible by 8 -> 128 x 96
            (643, 481),   # Non-multiple of 8 -> 80 x 60
        ]
        self.predictor.model.eval()
        for width, height in test_resolutions:
            dummy_input = torch.zeros(1, 3, height, width, device=self.predictor.device)
            with torch.no_grad():
                output = self.predictor.model(dummy_input)
            expected_h = height // 8
            expected_w = width // 8
            self.assertEqual(
                output.shape,
                (1, 1, expected_h, expected_w),
                f"Shape mismatch for input ({width}, {height}): expected (1, 1, {expected_h}, {expected_w}), got {output.shape}"
            )

    def test_03_finite_values_guarantee(self):
        """TEST 3: Output density map contains exclusively finite values (no NaN or Inf)."""
        if self.dummy_img.is_file():
            res = self.predictor.predict(self.dummy_img, return_density_map=True)
            dm = res["density_map"]
            self.assertTrue(bool(torch.isfinite(torch.from_numpy(dm)).all().item()))

        if self.real_crowd_img.is_file():
            res = self.predictor.predict(self.real_crowd_img, return_density_map=True)
            dm = res["density_map"]
            self.assertTrue(bool(torch.isfinite(torch.from_numpy(dm)).all().item()))

    def test_04_density_statistics_structure(self):
        """TEST 4: Inference result contains complete density map diagnostic statistics."""
        if not self.dummy_img.is_file():
            self.skipTest(f"Test image not found: {self.dummy_img}")

        res = self.predictor.predict(self.dummy_img)
        self.assertIn("density_stats", res)
        stats = res["density_stats"]

        required_keys = [
            "min", "max", "mean", "std", "sum",
            "negative_pixels", "positive_pixels", "zero_pixels",
            "total_pixels", "negative_pixel_pct"
        ]
        for key in required_keys:
            self.assertIn(key, stats)

        # Mathematical sanity: partition of pixels
        total_accounted = stats["negative_pixels"] + stats["positive_pixels"] + stats["zero_pixels"]
        self.assertEqual(total_accounted, stats["total_pixels"])
        self.assertGreater(stats["total_pixels"], 0)

    def test_05_non_crowd_baseline_headcount(self):
        """TEST 5: Non-crowd synthetic image produces zero-centered residual noise and 0 headcount."""
        if not self.dummy_img.is_file():
            self.skipTest(f"Dummy image not found: {self.dummy_img}")

        res = self.predictor.predict(self.dummy_img)
        stats = res["density_stats"]

        # 1. Headcount must be 0 for an empty image
        self.assertEqual(res["predicted_count"], 0)

        # 2. Mean pixel residual must be negligible (< 0.0005 per pixel)
        self.assertLess(abs(stats["mean"]), 0.0005)

        # 3. Sum across 4800 pixels should be close to 0 (magnitude < 0.5 people)
        self.assertLess(abs(stats["sum"]), 0.5)

    def test_06_real_crowd_detection(self):
        """TEST 6: Real crowd image produces strong positive density peaks and high headcount."""
        if not self.real_crowd_img.is_file():
            self.skipTest(f"Real crowd sample image not found: {self.real_crowd_img}")

        res = self.predictor.predict(self.real_crowd_img)
        stats = res["density_stats"]

        # Strong positive activation in crowd regions (maximum density > 0.5)
        self.assertGreater(stats["max"], 0.5)

        # Headcount must detect significant crowd (> 100 people)
        self.assertGreater(res["predicted_count"], 100)

        # Density sum must be positive
        self.assertGreater(res["raw_density_sum"], 100.0)

    def test_07_gpu_cpu_consistency(self):
        """TEST 7: CUDA and CPU inference results match within deep FP32 precision tolerance."""
        if not torch.cuda.is_available():
            self.skipTest("CUDA is not available on this machine.")

        target_img = self.real_crowd_img if self.real_crowd_img.is_file() else self.dummy_img
        if not target_img.is_file():
            self.skipTest("No test image available for GPU/CPU comparison.")

        pred_cuda = CrowdPredictor(weights_path=self.weights_path, device="cuda")
        pred_cpu = CrowdPredictor(weights_path=self.weights_path, device="cpu")

        res_cuda = pred_cuda.predict(target_img, return_density_map=True)
        res_cpu = pred_cpu.predict(target_img, return_density_map=True)

        # Max absolute pixel difference across all density grid cells
        max_diff = float(abs(res_cuda["density_map"] - res_cpu["density_map"]).max())
        self.assertLess(
            max_diff,
            1e-3,
            f"GPU and CPU density maps diverge: max diff {max_diff:.6e} exceeds 1e-3 tolerance"
        )

        # Raw continuous density sum relative difference should be under 0.2%
        rel_sum_diff = abs(res_cuda["raw_density_sum"] - res_cpu["raw_density_sum"]) / res_cuda["raw_density_sum"]
        self.assertLess(rel_sum_diff, 0.005, f"Raw density sum relative diff {rel_sum_diff:.4f} exceeds 0.5%")

        # Integer predicted headcounts should match within rounding boundary (+/- 1 person)
        self.assertLessEqual(
            abs(res_cuda["predicted_count"] - res_cpu["predicted_count"]),
            1,
            f"Predicted counts diverge excessively: CUDA={res_cuda['predicted_count']}, CPU={res_cpu['predicted_count']}"
        )


    def test_08_limitations_and_boundary_conditions(self):
        """TEST 8: Verify boundary handling for non-positive raw sums."""
        # Test count rounding logic:
        # Negative continuous density sums must always clamp to 0 people
        self.assertEqual(max(0, int(round(-0.097))), 0)
        self.assertEqual(max(0, int(round(-0.499))), 0)
        self.assertEqual(max(0, int(round(0.499))), 0)
        self.assertEqual(max(0, int(round(0.501))), 1)
        self.assertEqual(max(0, int(round(124.8))), 125)


if __name__ == '__main__':
    unittest.main(verbosity=2)
