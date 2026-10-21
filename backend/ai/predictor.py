"""
CrowdPredictor Inference Pipeline (Stage 7)
-------------------------------------------
Manages model loading, automatic hardware acceleration selection (CUDA / CPU),
image preprocessing with ImageNet normalization, gradient-free evaluation, and
density-map numerical integration.
"""

import os
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Union

try:
    import torch
    from torchvision import transforms
    from PIL import Image
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from .model import CSRNet


class CheckpointVerificationError(Exception):
    """Raised when checkpoint weights do not match expected architecture."""
    pass


class CrowdPredictor:
    """
    Inference manager for CSRNet crowd headcount estimation.
    """

    def __init__(
        self,
        weights_path: Optional[Union[str, Path]] = None,
        device: Optional[str] = None
    ):
        if not TORCH_AVAILABLE:
            raise RuntimeError(
                "PyTorch / torchvision / Pillow are not installed. "
                "Inference cannot be executed until package installation completes."
            )

        self._inference_lock = threading.Lock()

        # 1. Device Selection (RTX 3050 CUDA priority, CPU fallback)
        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # 2. Initialize Architecture
        self.model = CSRNet(load_weights=True)
        self.weights_path: Optional[Path] = None

        # 3. Load Checkpoint if provided
        if weights_path:
            self.load_weights(weights_path)

        # 4. Enforce Evaluation Mode
        self.model.to(self.device)
        self.model.eval()

        # 5. Image Transformation Pipeline (ImageNet mean & std used by pretrained VGG16)
        self.transform = transforms.Compose([

            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

    def load_weights(self, weights_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Loads and strictly verifies checkpoint parameter names, shapes, and architecture.
        Supports raw state_dict, checkpoint dictionaries, and DataParallel 'module.' prefixes.
        """
        path = Path(weights_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Checkpoint file not found at: {path}")

        # Load weights to target device or CPU (supporting PyTorch 2.6+ default change)
        try:
            checkpoint = torch.load(str(path), map_location=self.device, weights_only=False)
        except TypeError:
            checkpoint = torch.load(str(path), map_location=self.device)

        # Extract state dictionary
        if isinstance(checkpoint, dict):
            if 'state_dict' in checkpoint:
                raw_dict = checkpoint['state_dict']
            elif 'model_state_dict' in checkpoint:
                raw_dict = checkpoint['model_state_dict']
            elif 'model' in checkpoint:
                raw_dict = checkpoint['model']
            else:
                raw_dict = checkpoint
        else:
            raw_dict = checkpoint.state_dict()

        # Strip DataParallel 'module.' prefix if present and map alternate layer names
        clean_dict = {}
        for k, v in raw_dict.items():
            clean_key = k[7:] if k.startswith('module.') else k
            # Some checkpoints name the output conv layer 'output.' instead of 'output_layer.'
            if clean_key.startswith('output.'):
                clean_key = 'output_layer.' + clean_key[7:]
            clean_dict[clean_key] = v

        # Verify parameter compatibility against model definition
        model_keys = set(self.model.state_dict().keys())
        ckpt_keys = set(clean_dict.keys())

        missing = model_keys - ckpt_keys
        unexpected = ckpt_keys - model_keys

        if missing:
            raise CheckpointVerificationError(
                f"Checkpoint is missing {len(missing)} required layers: {sorted(list(missing))[:5]}..."
            )
        if unexpected:
            raise CheckpointVerificationError(
                f"Checkpoint contains {len(unexpected)} unexpected layers: {sorted(list(unexpected))[:5]}..."
            )

        # Verify tensor shapes
        for name, param in self.model.state_dict().items():
            ckpt_shape = clean_dict[name].shape
            if param.shape != ckpt_shape:
                raise CheckpointVerificationError(
                    f"Shape mismatch for '{name}': Model expects {tuple(param.shape)}, "
                    f"but checkpoint has {tuple(ckpt_shape)}"
                )

        # Load verified state_dict
        self.model.load_state_dict(clean_dict, strict=True)
        self.weights_path = path

        return {
            "verified": True,
            "weights_path": str(path),
            "layers_matched": len(clean_dict),
            "device": str(self.device)
        }

    def predict(
        self,
        image_path: Union[str, Path],
        return_density_map: bool = False
    ) -> Dict[str, Any]:
        """
        Performs inference on a single image and computes crowd headcount.
        - Disables gradient calculations (torch.no_grad).
        - Verifies that all output density values are finite numbers (no NaN or Inf).
        - Computes diagnostic statistics for the continuous 2D density map.
        - Sums over the continuous 2D density map to determine headcount.
        - Returns structured prediction dictionary.
        """
        img_path = Path(image_path).resolve()
        if not img_path.is_file():
            raise FileNotFoundError(f"Image not found at: {img_path}")

        start_time = time.perf_counter()

        # 1. Image Preprocessing
        pil_img = Image.open(str(img_path)).convert('RGB')
        orig_width, orig_height = pil_img.size

        # Transform and add batch dimension (1, 3, H, W)
        tensor = self.transform(pil_img).unsqueeze(0).to(self.device)

        # 2. Evaluation / Inference with disabled gradients & thread-safe lock
        with self._inference_lock:
            self.model.eval()
            with torch.no_grad():
                output = self.model(tensor)
            # Transfer tensor to CPU inside lock before releasing
            density_map = output.squeeze(0).squeeze(0).detach().cpu()

        inference_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 3. Density Map Integration & Diagnostics
        # Output shape: (1, 1, H // 8, W // 8)
        # Verify finite values
        if not torch.isfinite(density_map).all():
            raise ValueError(
                f"Density map contains non-finite values (NaN or Inf) during inference on {img_path.name}"
            )

        total_pixels = int(density_map.numel())
        min_val = float(density_map.min().item())
        max_val = float(density_map.max().item())
        mean_val = float(density_map.mean().item())
        std_val = float(density_map.std().item())
        neg_count = int((density_map < 0).sum().item())
        pos_count = int((density_map > 0).sum().item())
        zero_count = int((density_map == 0).sum().item())
        raw_count = float(density_map.sum().item())

        # Headcount calculation:
        # In continuous density estimation, raw_count is the spatial integral of the density map.
        # Empty background images produce tiny zero-centered residuals (e.g. mean ~ -0.00002)
        # summing to small negative numbers (e.g. -0.097), representing 0 people.
        # Physical crowd counts cannot be negative.
        headcount = max(0, int(round(raw_count)))

        density_stats = {
            "min": round(min_val, 6),
            "max": round(max_val, 6),
            "mean": round(mean_val, 8),
            "std": round(std_val, 6),
            "sum": round(raw_count, 4),
            "negative_pixels": neg_count,
            "positive_pixels": pos_count,
            "zero_pixels": zero_count,
            "total_pixels": total_pixels,
            "negative_pixel_pct": round((neg_count / total_pixels) * 100, 2) if total_pixels > 0 else 0.0,
        }

        result = {
            "predicted_count": headcount,
            "raw_density_sum": round(raw_count, 3),
            "density_stats": density_stats,
            "original_resolution": [orig_width, orig_height],
            "model_input_shape": list(tensor.shape),
            "density_map_shape": list(density_map.shape),
            "device": str(self.device),
            "inference_time_ms": inference_time_ms,
            "model_name": "CSRNet",
            "weights_file": self.weights_path.name if self.weights_path else "unloaded"
        }

        if return_density_map:
            result["density_map"] = density_map.numpy()

        return result

    @staticmethod
    def format_diagnostics_log(result: Dict[str, Any], identifier: str = "") -> str:
        """
        Formats comprehensive inference diagnostics for secure server-side logging.
        Does not expose raw file system paths.
        """
        orig_res = result.get("original_resolution", [0, 0])
        input_shape = result.get("model_input_shape", [])
        dm_shape = result.get("density_map_shape", [])
        stats = result.get("density_stats", {})
        raw_sum = result.get("raw_density_sum", 0.0)
        count = result.get("predicted_count", 0)
        device = result.get("device", "unknown")
        latency = result.get("inference_time_ms", 0)
        min_v = stats.get("min", 0.0)
        max_v = stats.get("max", 0.0)

        id_str = f"[{identifier}] " if identifier else ""
        return (
            f"CSRNet Inference Diagnostics {id_str}| "
            f"Orig Resolution: {orig_res[0]}x{orig_res[1]} (WxH) | "
            f"Model Input: {input_shape} | "
            f"Density Map Grid: {dm_shape} | "
            f"Raw Density Sum: {raw_sum:.3f} | "
            f"Min Density: {min_v:.6f} | "
            f"Max Density: {max_v:.6f} | "
            f"Predicted Count: {count} | "
            f"Latency: {latency}ms ({device})"
        )



# Global singleton instance holder for Flask application integration
_DEFAULT_PREDICTOR: Optional[CrowdPredictor] = None
_PREDICTOR_LOCK = threading.Lock()


def get_default_predictor(
    weights_path: Optional[Union[str, Path]] = None,
    device: Optional[str] = None
) -> CrowdPredictor:
    """Returns or lazily initializes the default singleton CrowdPredictor instance with thread safety."""
    global _DEFAULT_PREDICTOR
    if _DEFAULT_PREDICTOR is None:
        with _PREDICTOR_LOCK:
            if _DEFAULT_PREDICTOR is None:
                if weights_path is None:
                    # Check default weights location
                    default_weights = Path(__file__).resolve().parent / 'weights' / 'shanghaitech_part_b.pth'
                    if default_weights.is_file():
                        weights_path = default_weights
                _DEFAULT_PREDICTOR = CrowdPredictor(weights_path=weights_path, device=device)
    return _DEFAULT_PREDICTOR

