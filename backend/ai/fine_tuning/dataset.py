"""
Dataset Management & Validation for CSRNet Fine-Tuning
------------------------------------------------------
Provides PyTorch Dataset implementation, image/annotation matching,
data leakage prevention via event grouping, and memory-conscious resizing.
"""

import os
import re
import json
import csv
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from PIL import Image

import torch
from torch.utils.data import Dataset
from torchvision import transforms

from .density_map import load_points_from_file, generate_density_map


class DatasetValidator:
    """
    Validates crowd dataset integrity, annotation alignment, and partitions data
    into train, validation, and test splits without data leakage.
    """

    SUPPORTED_IMAGE_EXTS = {'.jpg', '.jpeg', '.png'}
    SUPPORTED_ANNOTATION_EXTS = {'.mat', '.json', '.csv', '.txt'}

    GENERIC_PHOTO_PREFIXES = {
        'img', 'image', 'pic', 'picture', 'photo', 'frame',
        'dsc', 'dscn', 'cimg', 'file', 'shot', 'gt', 'gt_img'
    }

    @classmethod
    def find_annotation_for_image(cls, img_path: Path, annotations_dir: Optional[Path] = None) -> Optional[Path]:
        """Finds matching annotation file for a given image using numeric identifiers and candidate patterns."""
        search_dirs = [img_path.parent]
        if annotations_dir:
            a_dir = Path(annotations_dir).resolve()
            if a_dir.is_dir():
                search_dirs.append(a_dir)
        else:
            # Check standard sibling directories of images/ (e.g. ground_truth with underscore)
            parent = img_path.parent.parent
            for sib_name in ["ground_truth", "ground-truth", "groundtruth", "annotations", "labels"]:
                sib = parent / sib_name
                if sib.is_dir():
                    search_dirs.append(sib)

        stem = img_path.stem

        # Extract numeric identifier if present (e.g. 'IMG_1' -> '1')
        num_match = re.search(r'(\d+)', stem)
        num_str = num_match.group(1) if num_match else ""
        num_int = str(int(num_str)) if num_str else ""

        # Candidates to try
        candidates = [
            f"{stem}.json",
            f"{stem}_ann.mat",
            f"GT_{stem}.mat",
            f"GT_{img_path.name}.mat",
            f"{stem}.mat",
            f"{stem}.csv",
            f"{stem}.txt",
        ]
        if num_str:
            candidates.extend([
                f"GT_IMG_{num_str}.mat",
                f"GT_IMG_{num_int}.mat",
                f"GT_{num_str}.mat",
                f"GT_{num_int}.mat",
                f"IMG_{num_str}.mat",
                f"IMG_{num_int}.mat",
                f"{num_str}_ann.mat",
                f"{num_int}_ann.mat",
                f"{num_str}.mat",
                f"{num_int}.mat",
                f"GT_IMG_{num_str}.json",
                f"GT_IMG_{num_int}.json",
                f"GT_{num_str}.json",
                f"{num_str}.json",
            ])

        for s_dir in search_dirs:
            if not s_dir.is_dir():
                continue
            # 1. Exact match check
            for cand in candidates:
                p = s_dir / cand
                if p.is_file():
                    return p

            # 2. Case-insensitive check in s_dir
            cand_lower = {c.lower(): c for c in candidates}
            try:
                for f in s_dir.iterdir():
                    if f.is_file():
                        f_lower = f.name.lower()
                        if f_lower in cand_lower:
                            return f
                        # Numeric match: e.g. 'GT_IMG_1.mat' for image 'IMG_1.jpg'
                        if num_int:
                            pattern = rf'^(?:gt_)?(?:img_)?0*{num_int}\.(?:mat|json|csv|txt)$'
                            if re.match(pattern, f_lower):
                                return f
            except Exception:
                pass

        return None

    @classmethod
    def infer_event_group(cls, stem: str) -> str:
        """
        Infers an event group string for leakage prevention.
        - Genuine event identifiers ('event_101', 'ev_5', 'fest_annual') group related burst shots.
        - Semantic event/venue names ('TechFest_Auditorium_01') group shots by event prefix.
        - Generic camera/dataset prefixes ('IMG_1', 'DSC_001', numeric '1') are NEVER treated
          as a shared event group; each image receives its own group to prevent false clustering.
        """
        clean_stem = stem.strip()
        lower_stem = clean_stem.lower()

        # 1. Explicit event/fest patterns: 'event_101_...', 'ev_12_...', 'fest_annual_...'
        event_match = re.match(r'^(event_\d+|ev_\d+|fest_\d+|fest_[a-z0-9]+)', lower_stem)
        if event_match:
            return event_match.group(1)

        # 2. Purely numeric names: '1', '400', '001'
        if lower_stem.isdigit():
            return lower_stem

        # 3. Check prefix before trailing digits or underscore+digits
        prefix_match = re.match(r'^([a-zA-Z0-9_\-]+?)(?:_?\d+)+$', clean_stem)
        if prefix_match:
            prefix = prefix_match.group(1).lower().rstrip('_')
            if prefix in cls.GENERIC_PHOTO_PREFIXES or prefix == '':
                # Generic naming (e.g. IMG_1, DSC_100) -> treat as independent image
                return lower_stem
            else:
                # Semantic event/venue prefix (e.g. TechFest_Auditorium, Convocation)
                return prefix

        return lower_stem

    @classmethod
    def scan_dataset(
        cls,
        images_dir: Union[str, Path],
        annotations_dir: Optional[Union[str, Path]] = None,
        master_json: Optional[Union[str, Path]] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans and verifies all image-annotation pairs in a directory.
        Returns a list of verified item dictionaries:
          [{"image_path": Path, "annotation_path": Path or points, "event_group": str, "headcount": int}, ...]
        """
        img_dir = Path(images_dir).resolve()
        if not img_dir.is_dir():
            raise FileNotFoundError(f"Images directory not found: {img_dir}")

        ann_dir = Path(annotations_dir).resolve() if annotations_dir else None

        master_map = {}
        if master_json:
            m_path = Path(master_json).resolve()
            if m_path.is_file():
                if m_path.suffix.lower() == '.csv':
                    with open(m_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            img_key = row.get("image_filename") or row.get("image") or row.get("filename")
                            if img_key:
                                raw_hc = row.get("headcount") if "headcount" in row else row.get("count")
                                if raw_hc is not None and str(raw_hc).strip() != "":
                                    try:
                                        hc = float(str(raw_hc).strip())
                                        master_map[img_key.strip()] = {
                                            "headcount": hc,
                                            "event_type": row.get("event_type", "college_event").strip(),
                                            "crowd_density": (row.get("crowd_density") or row.get("density_category") or "").strip()
                                        }
                                    except ValueError:
                                        pass
                else:
                    with open(m_path, 'r', encoding='utf-8') as f:
                        master_map = json.load(f)

        # Collect images (natural sorting for deterministic order across platforms)
        def natural_sort_key(p):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', p.name)]

        image_files = sorted([
            f for f in img_dir.iterdir()
            if f.is_file() and f.suffix.lower() in cls.SUPPORTED_IMAGE_EXTS
        ], key=natural_sort_key)

        if not image_files:
            raise ValueError(f"No valid image files (.jpg, .jpeg, .png) found in {img_dir}")

        verified_items = []
        corrupted_count = 0
        missing_ann_count = 0

        for img_p in image_files:
            # 1. Verify image can be opened
            try:
                with Image.open(str(img_p)) as pil_img:
                    w, h = pil_img.size
                    pil_img.verify()
            except Exception:
                corrupted_count += 1
                continue

            # 2. Extract points & verified headcount (Strict zero-guessing guarantee)
            pts = None
            ann_p = None
            headcount = None
            event_type = "college_event"
            density_category = ""

            if img_p.name in master_map:
                val = master_map[img_p.name]
                if isinstance(val, dict):
                    raw_hc = val.get("headcount") if "headcount" in val else val.get("count")
                    if raw_hc is not None and str(raw_hc).strip() != "":
                        try:
                            headcount = float(raw_hc)
                        except (ValueError, TypeError):
                            headcount = None
                    if "points" in val and isinstance(val["points"], list):
                        pts = np.asarray(val["points"], dtype=np.float32)
                    else:
                        pts = np.empty((0, 2), dtype=np.float32)
                    event_type = val.get("event_type", "college_event")
                    density_category = val.get("crowd_density") or val.get("density_category") or ""
                elif isinstance(val, list):
                    pts = np.asarray(val, dtype=np.float32)
                    headcount = float(len(pts))
                elif isinstance(val, (int, float)):
                    pts = np.empty((0, 2), dtype=np.float32)
                    headcount = float(val)
            else:
                ann_p = cls.find_annotation_for_image(img_p, ann_dir)
                if ann_p:
                    try:
                        pts = load_points_from_file(ann_p)
                        if pts is not None:
                            headcount = float(len(pts))
                    except Exception:
                        pts = None
                        headcount = None

            # Enforce Task 4: Do not guess counts; skip images without verified ground truth
            if headcount is None or (pts is None and headcount is None):
                missing_ann_count += 1
                continue

            # 3. Infer event group to prevent data leakage across bursts/angles
            event_group = cls.infer_event_group(img_p.stem)

            verified_items.append({
                "image_path": img_p,
                "annotation_path": ann_p,
                "points": pts,
                "headcount": headcount,
                "event_type": event_type,
                "density_category": density_category,
                "resolution": [w, h],
                "event_group": event_group,
            })

        return verified_items

    @classmethod
    def partition_splits(
        cls,
        items: List[Dict[str, Any]],
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        seed: int = 42
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Partitions dataset items into train, validation, and test splits.
        - Respects zero-valued ratios strictly (a ratio of 0 produces 0 samples).
        - For ShanghaiTech / independent images: provides deterministic reproducible splits.
        - For event datasets: groups items by event_group to eliminate data leakage.
        """
        if not items:
            return {"train": [], "val": [], "test": []}

        total_r = train_ratio + val_ratio + test_ratio
        if total_r <= 0:
            return {"train": [], "val": [], "test": []}

        tr_norm = max(0.0, train_ratio / total_r)
        val_norm = max(0.0, val_ratio / total_r)
        test_norm = max(0.0, test_ratio / total_r)

        total_samples = len(items)

        # Exact target count calculations respecting zero-valued ratios
        target_train = int(round(total_samples * tr_norm)) if train_ratio > 0 else 0
        target_val = int(round(total_samples * val_norm)) if val_ratio > 0 else 0
        target_test = total_samples - target_train - target_val if test_ratio > 0 else 0

        # Adjust for rounding when test_ratio is 0
        if test_ratio <= 0:
            target_test = 0
            if train_ratio > 0:
                target_train = total_samples - target_val
            elif val_ratio > 0:
                target_val = total_samples
        elif train_ratio <= 0 and val_ratio <= 0:
            target_test = total_samples

        # Group items by event_group
        grouped = {}
        for it in items:
            grp = it.get("event_group", it["image_path"].stem.lower())
            grouped.setdefault(grp, []).append(it)

        # Deterministic natural sort key
        def natural_sort_key(s):
            return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

        groups = sorted(list(grouped.keys()), key=natural_sort_key)
        rng = random.Random(seed)
        rng.shuffle(groups)

        train_items = []
        val_items = []
        test_items = []

        cur_train = 0
        cur_val = 0
        cur_test = 0

        for grp in groups:
            group_items = grouped[grp]
            n_grp = len(group_items)

            # Assign to train if train is requested and not full
            if target_train > 0 and cur_train < target_train:
                train_items.extend(group_items)
                cur_train += n_grp
            # Else assign to val if val is requested and not full
            elif target_val > 0 and cur_val < target_val:
                val_items.extend(group_items)
                cur_val += n_grp
            # Else assign to test if test is requested and not full
            elif target_test > 0 and cur_test < target_test:
                test_items.extend(group_items)
                cur_test += n_grp
            else:
                # Overflow handling: assign to whichever requested split has room, strictly respecting 0-ratios
                if target_test > 0 and cur_test < target_test:
                    test_items.extend(group_items)
                    cur_test += n_grp
                elif target_val > 0 and cur_val < target_val:
                    val_items.extend(group_items)
                    cur_val += n_grp
                elif target_train > 0:
                    train_items.extend(group_items)
                    cur_train += n_grp
                elif target_val > 0:
                    val_items.extend(group_items)
                    cur_val += n_grp
                elif target_test > 0:
                    test_items.extend(group_items)
                    cur_test += n_grp

        # STRICT SAFEGUARD: Never allow samples in a split with zero ratio
        if train_ratio <= 0.0 or target_train == 0:
            train_items = []
        if val_ratio <= 0.0 or target_val == 0:
            val_items = []
        if test_ratio <= 0.0 or target_test == 0:
            test_items = []

        return {
            "train": train_items,
            "val": val_items,
            "test": test_items
        }


class CrowdDataset(Dataset):
    """
    PyTorch Dataset for CSRNet crowd estimation.
    Designed for memory-conscious GPU training (4 GB VRAM cap).
    """

    def __init__(
        self,
        items: List[Dict[str, Any]],
        max_size: int = 1024,
        is_training: bool = False,
        density_method: str = "fixed",
        fixed_sigma: float = 15.0,
        flip_prob: float = 0.5
    ):
        self.items = items
        self.max_size = max_size
        self.is_training = is_training
        self.density_method = density_method
        self.fixed_sigma = fixed_sigma
        self.flip_prob = flip_prob

        # ImageNet normalization matching CSRNet pretrained VGG-16
        self.normalize = transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225]
        )

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        item = self.items[idx]
        img_path = item["image_path"]
        raw_pts = item["points"]

        # Load RGB image
        pil_img = Image.open(str(img_path)).convert('RGB')
        orig_w, orig_h = pil_img.size

        # 1. Resize to fit max_size (4 GB GPU VRAM safety constraint)
        scale = 1.0
        if max(orig_w, orig_h) > self.max_size:
            scale = self.max_size / float(max(orig_w, orig_h))

        new_w = int(round(orig_w * scale))
        new_h = int(round(orig_h * scale))

        # CSRNet requires dimensions divisible by 8 (3 maxpools)
        new_w = max(8, (new_w // 8) * 8)
        new_h = max(8, (new_h // 8) * 8)

        # Effective scale along each axis
        scale_x = new_w / float(orig_w)
        scale_y = new_h / float(orig_h)

        if new_w != orig_w or new_h != orig_h:
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        # Scale point coordinates accordingly
        pts = raw_pts.copy() if len(raw_pts) > 0 else np.empty((0, 2), dtype=np.float32)
        if len(pts) > 0:
            pts[:, 0] = pts[:, 0] * scale_x
            pts[:, 1] = pts[:, 1] * scale_y

        # 2. Data Augmentation: Random Horizontal Flip during training
        flipped = False
        if self.is_training and random.random() < self.flip_prob:
            pil_img = pil_img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if len(pts) > 0:
                pts[:, 0] = (new_w - 1) - pts[:, 0]
            flipped = True

        # 3. Generate ground-truth continuous density map at (new_h // 8, new_w // 8)
        density_map = generate_density_map(
            shape=(new_h, new_w),
            points=pts,
            method=self.density_method,
            fixed_sigma=self.fixed_sigma,
            downsample_factor=8
        )

        # 4. Convert Image to Tensor & Normalize
        # ToTensor converts PIL (H, W, C) in [0, 255] to torch.FloatTensor (C, H, W) in [0.0, 1.0]
        img_tensor = transforms.functional.to_tensor(pil_img)
        img_tensor = self.normalize(img_tensor)

        density_tensor = torch.from_numpy(density_map).unsqueeze(0).float()  # (1, H//8, W//8)

        return {
            "image": img_tensor,
            "density_map": density_tensor,
            "count": float(len(pts)),
            "image_name": img_path.name,
            "original_resolution": [orig_w, orig_h],
            "resized_resolution": [new_w, new_h],
            "flipped": flipped
        }
