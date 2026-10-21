"""
Density Map Generation & Point Annotation Parser
------------------------------------------------
Generates continuous 2D ground-truth density maps from head-center point coordinates
compatible with CSRNet's training objective and 1/8 downsampling factor.

Guarantees:
  sum(density_map) == len(points)
"""

import os
import json
import csv
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.spatial import KDTree

try:
    import scipy.io
    SCIPY_IO_AVAILABLE = True
except ImportError:
    SCIPY_IO_AVAILABLE = False


def load_points_from_file(annotation_path: Union[str, Path]) -> np.ndarray:
    """
    Parses head-center point annotations from .mat, .json, or .csv files.
    Returns: np.ndarray of shape (N, 2) where each row is [x, y] in pixel coordinates.
    """
    path = Path(annotation_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Annotation file not found: {path}")

    suffix = path.suffix.lower()

    # 1. MATLAB .mat format
    if suffix == '.mat':
        if not SCIPY_IO_AVAILABLE:
            raise RuntimeError("scipy is required to load .mat annotations.")
        data = scipy.io.loadmat(str(path))

        # Format A: annPoints (UCF-QNRF, UCF-CC-50, etc.)
        if 'annPoints' in data:
            pts = np.asarray(data['annPoints'], dtype=np.float32)
            if pts.ndim == 2 and pts.shape[1] == 2:
                return pts
            if pts.size == 0:
                return np.empty((0, 2), dtype=np.float32)

        # Format B: image_info (ShanghaiTech Part A & Part B)
        if 'image_info' in data:
            info = data['image_info']
            try:
                # ShanghaiTech format: image_info[0,0][0,0][0] holds point array
                points_arr = info[0, 0][0, 0][0]
                pts = np.asarray(points_arr, dtype=np.float32)
                if pts.ndim == 2 and pts.shape[1] == 2:
                    return pts
            except Exception:
                pass

        # Format C: any 2D variable in .mat
        for k, v in data.items():
            if not k.startswith('__') and isinstance(v, np.ndarray):
                if v.ndim == 2 and v.shape[1] == 2:
                    return v.astype(np.float32)

        return np.empty((0, 2), dtype=np.float32)

    # 2. JSON format
    elif suffix == '.json':
        with open(path, 'r', encoding='utf-8') as f:
            content = json.load(f)

        # Standard formats:
        # a) [[x1, y1], [x2, y2], ...]
        if isinstance(content, list):
            if len(content) == 0:
                return np.empty((0, 2), dtype=np.float32)
            pts = np.asarray(content, dtype=np.float32)
            if pts.ndim == 2 and pts.shape[1] == 2:
                return pts

        # b) {"points": [[x1, y1], ...]}
        elif isinstance(content, dict):
            if 'points' in content:
                pts = np.asarray(content['points'], dtype=np.float32)
                if pts.size == 0:
                    return np.empty((0, 2), dtype=np.float32)
                if pts.ndim == 2 and pts.shape[1] == 2:
                    return pts
            if 'annotations' in content:
                # [{"x": 100, "y": 200}, ...]
                pts = [[item.get('x', 0), item.get('y', 0)] for item in content['annotations']]
                return np.asarray(pts, dtype=np.float32) if pts else np.empty((0, 2), dtype=np.float32)

        return np.empty((0, 2), dtype=np.float32)

    # 3. CSV format
    elif suffix in ('.csv', '.txt'):
        points = []
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row or row[0].startswith('#') or row[0].strip().isalpha():
                    continue
                try:
                    # Expect x, y in first two columns
                    x, y = float(row[0].strip()), float(row[1].strip())
                    points.append([x, y])
                except (ValueError, IndexError):
                    continue
        return np.asarray(points, dtype=np.float32) if points else np.empty((0, 2), dtype=np.float32)

    else:
        raise ValueError(f"Unsupported annotation format '{suffix}'. Supported: .mat, .json, .csv, .txt")


def generate_density_map(
    shape: Tuple[int, int],
    points: np.ndarray,
    method: str = "fixed",
    fixed_sigma: float = 15.0,
    k_nn: int = 3,
    beta: float = 0.3,
    downsample_factor: int = 8
) -> np.ndarray:
    """
    Generates a continuous 2D ground-truth density map matching CSRNet's output resolution.

    Args:
      shape: (height, width) of the original image.
      points: (N, 2) numpy array of [x, y] coordinates.
      method: "fixed" (constant Gaussian sigma) or "adaptive" (k-NN distance-based sigma).
      fixed_sigma: Sigma for fixed Gaussian kernel (default: 15.0, standard for Part B / sparse college crowds).
      k_nn: Number of nearest neighbors for adaptive kernel.
      beta: Multiplier for mean k-NN distance.
      downsample_factor: CSRNet output spatial downsampling (default: 8).

    Returns:
      density_map: np.ndarray of shape (H // 8, W // 8), float32,
                   where np.sum(density_map) matches the headcount len(points) within numerical precision.
    """
    h, w = int(shape[0]), int(shape[1])
    target_h = h // downsample_factor
    target_w = w // downsample_factor

    if target_h <= 0 or target_w <= 0:
        raise ValueError(f"Image dimensions {shape} too small for downsample factor {downsample_factor}")

    # Empty scene: return all zeros
    if points is None or len(points) == 0:
        return np.zeros((target_h, target_w), dtype=np.float32)

    # Filter points within image boundaries
    valid_mask = (points[:, 0] >= 0) & (points[:, 0] < w) & (points[:, 1] >= 0) & (points[:, 1] < h)
    valid_points = points[valid_mask]
    n_points = len(valid_points)

    if n_points == 0:
        return np.zeros((target_h, target_w), dtype=np.float32)

    # Generate density map at target resolution (H // 8, W // 8) directly by scaling coordinates
    # This avoids generating a massive (H, W) array and downsampling, saving significant memory.
    density_map = np.zeros((target_h, target_w), dtype=np.float32)

    # Scale points to target resolution
    scaled_x = valid_points[:, 0] / downsample_factor
    scaled_y = valid_points[:, 1] / downsample_factor

    if method == "adaptive" and n_points >= k_nn + 1:
        tree = KDTree(valid_points)
        distances, _ = tree.query(valid_points, k=k_nn + 1)
        # Average distance to k nearest neighbors (excluding point itself at index 0)
        mean_distances = np.mean(distances[:, 1:], axis=1)
        sigmas = np.clip(mean_distances * beta / downsample_factor, 1.0, 15.0)
    else:
        # Fixed sigma scaled down to output resolution
        scaled_sigma = max(1.0, fixed_sigma / downsample_factor)
        sigmas = np.full(n_points, scaled_sigma, dtype=np.float32)

    # Accumulate Gaussian kernels
    for i in range(n_points):
        px, py = int(round(scaled_x[i])), int(round(scaled_y[i]))
        px = np.clip(px, 0, target_w - 1)
        py = np.clip(py, 0, target_h - 1)

        sig = float(sigmas[i])
        radius = int(max(3, round(3.0 * sig)))

        x_min = max(0, px - radius)
        x_max = min(target_w, px + radius + 1)
        y_min = max(0, py - radius)
        y_max = min(target_h, py + radius + 1)

        # 2D Gaussian patch
        gy, gx = np.ogrid[y_min - py : y_max - py, x_min - px : x_max - px]
        patch = np.exp(-(gx * gx + gy * gy) / (2.0 * sig * sig))

        patch_sum = patch.sum()
        if patch_sum > 0:
            patch /= patch_sum  # Each person contributes exactly 1.0 to the integral
            density_map[y_min:y_max, x_min:x_max] += patch

    # Guarantee strict count preservation (normalize sum to exact valid headcount)
    current_sum = float(density_map.sum())
    if current_sum > 0:
        density_map = density_map * (float(n_points) / current_sum)

    return density_map.astype(np.float32)
