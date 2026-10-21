"""
CSRNet Fine-Tuning Manager (4 GB GPU Optimized)
-----------------------------------------------
Executes training loops, gradient accumulation, validation checkpoints,
and logging for NVIDIA RTX 3050 Laptop GPU (4 GB VRAM) safety.
"""

import os
import sys
import json
import time
import math
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
import numpy as np

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from ..model import CSRNet
from .dataset import CrowdDataset, DatasetValidator


class CSRNetFineTuner:
    """
    Fine-tuning controller for CSRNet on college crowd datasets.
    Isolates all experimental artifacts into dedicated directories.
    """

    def __init__(
        self,
        base_weights_path: Union[str, Path],
        experiment_dir: Union[str, Path],
        device: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        self.base_weights_path = Path(base_weights_path).resolve()
        if not self.base_weights_path.is_file():
            raise FileNotFoundError(f"Base pretrained weights not found: {self.base_weights_path}")

        self.experiment_dir = Path(experiment_dir).resolve()
        self.experiment_dir.mkdir(parents=True, exist_ok=True)

        # Device selection: priority to CUDA
        if device:
            self.device = torch.device(device)
        else:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        # Default configuration tuned for 4 GB VRAM RTX 3050 Laptop GPU
        self.config = {
            "optimizer": "sgd",
            "learning_rate": 1e-6,
            "momentum": 0.95,
            "weight_decay": 1e-4,
            "freeze_frontend_epochs": 5,
            "early_stopping_patience": 5,
            "batch_size": 1,
            "accumulate_grad_batches": 4,  # Simulates effective batch size 4 without VRAM spike
            "epochs": 20,
            "max_image_size": 1024,
            "density_method": "fixed",
            "fixed_sigma": 15.0,
            "random_seed": 42,
            "grad_clip_norm": 1.0,
            "lr_decay_step": 10,
            "lr_decay_gamma": 0.5,
            "use_amp": False,
        }
        if config:
            self.config.update(config)

        # Set random seeds for reproducibility
        self._set_seed(self.config["random_seed"])

        # Setup logger
        self.logger = self._init_logger()

        # Initialize model
        self.model = CSRNet(load_weights=True)
        self._load_baseline_weights()
        self.model.to(self.device)

        # Loss function: Standard density map MSE loss
        self.criterion = nn.MSELoss(reduction='sum')

        # Organize parameter groups for differential/freezable frontend vs dilated backend
        frontend_params = list(self.model.frontend.parameters())
        backend_params = list(self.model.backend.parameters()) + list(self.model.output_layer.parameters())

        param_groups = [
            {"params": backend_params, "lr": self.config["learning_rate"], "name": "backend"},
            {"params": frontend_params, "lr": self.config["learning_rate"], "name": "frontend"}
        ]

        opt_name = str(self.config.get("optimizer", "sgd")).lower()
        if opt_name == "adam":
            self.optimizer = torch.optim.Adam(
                param_groups,
                lr=self.config["learning_rate"],
                weight_decay=self.config["weight_decay"]
            )
        else:
            self.optimizer = torch.optim.SGD(
                param_groups,
                lr=self.config["learning_rate"],
                momentum=self.config.get("momentum", 0.95),
                weight_decay=self.config["weight_decay"]
            )

        self.scheduler = torch.optim.lr_scheduler.StepLR(
            self.optimizer,
            step_size=self.config["lr_decay_step"],
            gamma=self.config["lr_decay_gamma"]
        )

        # Save config snapshot
        with open(self.experiment_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)

    def _set_seed(self, seed: int):
        torch.manual_seed(seed)
        np.random.seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    def _init_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"CSRNetFineTuner_{self.experiment_dir.name}")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            fh = logging.FileHandler(self.experiment_dir / "training.log", encoding="utf-8")
            formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
            # Also log to stdout
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(formatter)
            logger.addHandler(sh)
        return logger

    def close(self):
        """Flushes and closes all logger handlers to release file locks (important on Windows)."""
        if hasattr(self, 'logger') and self.logger:
            for handler in list(self.logger.handlers):
                handler.close()
                self.logger.removeHandler(handler)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _load_baseline_weights(self):
        """Loads and maps pretrained checkpoint weights to model cleanly."""
        try:
            ckpt = torch.load(str(self.base_weights_path), map_location=self.device, weights_only=False)
        except TypeError:
            ckpt = torch.load(str(self.base_weights_path), map_location=self.device)

        if isinstance(ckpt, dict):
            raw_dict = ckpt.get('state_dict', ckpt.get('model_state_dict', ckpt.get('model', ckpt)))
        else:
            raw_dict = ckpt.state_dict()

        clean_dict = {}
        for k, v in raw_dict.items():
            k_clean = k[7:] if k.startswith('module.') else k
            if k_clean.startswith('output.'):
                k_clean = 'output_layer.' + k_clean[7:]
            clean_dict[k_clean] = v

        self.model.load_state_dict(clean_dict, strict=True)
        self.logger.info(f"Loaded pretrained baseline weights from {self.base_weights_path.name}")

    def freeze_frontend(self):
        """Freezes the first 10 convolutional layers of the VGG-16 frontend."""
        for param in self.model.frontend.parameters():
            param.requires_grad = False
        self.logger.info("Frozen the first 10 VGG-16 frontend layers (requires_grad=False).")

    def unfreeze_frontend(self):
        """Unfreezes the first 10 convolutional layers of the VGG-16 frontend for end-to-end training."""
        for param in self.model.frontend.parameters():
            param.requires_grad = True
        self.logger.info("Unfrozen the first 10 VGG-16 frontend layers (requires_grad=True).")

    def is_frontend_frozen(self) -> bool:
        """Returns True if any frontend parameter is frozen (requires_grad=False)."""
        return any(not p.requires_grad for p in self.model.frontend.parameters())

    def train_epoch(self, train_loader: DataLoader, epoch: int) -> float:
        """Trains for one epoch with gradient accumulation and VRAM safety."""
        self.model.train()
        total_loss = 0.0
        n_batches = len(train_loader)
        accum_steps = max(1, self.config["accumulate_grad_batches"])

        self.optimizer.zero_grad()

        for i, batch in enumerate(train_loader):
            images = batch["image"].to(self.device)
            targets = batch["density_map"].to(self.device)

            # Forward pass
            outputs = self.model(images)

            # Compute sum MSE loss scaled by batch accumulation factor
            loss = self.criterion(outputs, targets) / accum_steps
            loss.backward()

            total_loss += loss.item() * accum_steps

            # Step optimizer every accum_steps or on the final batch
            if (i + 1) % accum_steps == 0 or (i + 1) == n_batches:
                if self.config["grad_clip_norm"] > 0:
                    active_params = [p for p in self.model.parameters() if p.requires_grad and p.grad is not None]
                    if active_params:
                        torch.nn.utils.clip_grad_norm_(active_params, self.config["grad_clip_norm"])
                self.optimizer.step()
                self.optimizer.zero_grad()

            # Empty VRAM cache periodically for 4 GB GPU safety
            if self.device.type == 'cuda' and (i + 1) % 10 == 0:
                torch.cuda.empty_cache()

        avg_loss = total_loss / max(1, n_batches)
        return avg_loss

    def evaluate(self, dataloader: DataLoader) -> Dict[str, float]:
        """Evaluates model against a dataset split without computing gradients."""
        self.model.eval()
        total_mae = 0.0
        total_mse = 0.0
        n_samples = 0

        with torch.no_grad():
            for batch in dataloader:
                images = batch["image"].to(self.device)
                ground_truth_count = batch["count"].item()

                output = self.model(images)
                pred_count = max(0.0, float(output.sum().item()))

                err = abs(pred_count - ground_truth_count)
                sq_err = (pred_count - ground_truth_count) ** 2

                total_mae += err
                total_mse += sq_err
                n_samples += 1

        if n_samples == 0:
            return {"mae": 0.0, "rmse": 0.0, "samples": 0}

        mae = total_mae / n_samples
        rmse = math.sqrt(total_mse / n_samples)

        return {
            "mae": round(mae, 3),
            "rmse": round(rmse, 3),
            "samples": n_samples
        }

    def fit(
        self,
        train_items: List[Dict[str, Any]],
        val_items: List[Dict[str, Any]],
        test_items: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Executes complete fine-tuning pipeline.
        Enforces validation that training data exists before starting.
        """
        if not train_items:
            raise ValueError("Training dataset contains 0 items. Cannot begin fine-tuning without annotated data.")
        if not val_items:
            raise ValueError("Validation dataset contains 0 items. Validation data is required for model selection.")

        # Safeguard: Verify strictly zero data leakage between train and val
        train_img_set = {it["image_path"].name for it in train_items}
        val_img_set = {it["image_path"].name for it in val_items}
        overlap = train_img_set & val_img_set
        if overlap:
            raise ValueError(f"Data leakage detected! {len(overlap)} images overlap between train and validation: {list(overlap)[:5]}")

        self.logger.info(f"Beginning fine-tuning: {len(train_items)} train, {len(val_items)} val, {len(test_items or [])} test samples.")
        self.logger.info(f"Target Device: {self.device}")

        # Construct PyTorch DataLoaders
        train_dataset = CrowdDataset(
            items=train_items,
            max_size=self.config["max_image_size"],
            is_training=True,
            density_method=self.config["density_method"],
            fixed_sigma=self.config["fixed_sigma"]
        )
        val_dataset = CrowdDataset(
            items=val_items,
            max_size=self.config["max_image_size"],
            is_training=False,
            density_method=self.config["density_method"],
            fixed_sigma=self.config["fixed_sigma"]
        )

        train_loader = DataLoader(train_dataset, batch_size=self.config["batch_size"], shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=1, shuffle=False)

        # Baseline evaluation before fine-tuning
        baseline_val_metrics = self.evaluate(val_loader)
        self.logger.info(f"[Baseline] Pre-trained Part B Val MAE: {baseline_val_metrics['mae']:.2f}, RMSE: {baseline_val_metrics['rmse']:.2f}")

        # Save baseline model permanently as baseline_model.pth (never overwritten)
        torch.save({
            "epoch": 0,
            "model_state_dict": self.model.state_dict(),
            "val_metrics": baseline_val_metrics,
            "config": self.config
        }, self.experiment_dir / "baseline_model.pth")

        # Also initialize best_model.pth to baseline reference
        torch.save({
            "epoch": 0,
            "model_state_dict": self.model.state_dict(),
            "val_metrics": baseline_val_metrics,
            "config": self.config
        }, self.experiment_dir / "best_model.pth")

        best_val_mae = baseline_val_metrics["mae"]
        best_epoch = 0
        best_finetuned_val_mae = float("inf")
        best_finetuned_epoch = None
        history: List[Dict[str, Any]] = []

        # Configure freezing of VGG-16 frontend layers
        freeze_epochs = max(0, int(self.config.get("freeze_frontend_epochs", 0)))
        if freeze_epochs > 0:
            self.freeze_frontend()

        # Configure early stopping
        patience = max(0, int(self.config.get("early_stopping_patience", 0)))
        epochs_without_improvement = 0
        early_stopped = False

        total_epochs = self.config["epochs"]
        start_time = time.perf_counter()

        for epoch in range(1, total_epochs + 1):
            # Unfreeze frontend when freeze duration is reached
            if freeze_epochs > 0 and epoch == freeze_epochs + 1:
                self.unfreeze_frontend()

            ep_start = time.perf_counter()
            train_loss = self.train_epoch(train_loader, epoch)
            val_metrics = self.evaluate(val_loader)
            self.scheduler.step()

            ep_duration = time.perf_counter() - ep_start
            cur_lr = self.optimizer.param_groups[0]['lr']

            log_entry = {
                "epoch": epoch,
                "train_loss": round(train_loss, 4),
                "val_mae": val_metrics["mae"],
                "val_rmse": val_metrics["rmse"],
                "lr": cur_lr,
                "frontend_frozen": self.is_frontend_frozen(),
                "duration_seconds": round(ep_duration, 1)
            }
            history.append(log_entry)

            self.logger.info(
                f"Epoch {epoch:02d}/{total_epochs:02d} | "
                f"Loss: {train_loss:.4f} | "
                f"Val MAE: {val_metrics['mae']:.2f} | "
                f"Val RMSE: {val_metrics['rmse']:.2f} | "
                f"LR: {cur_lr:.2e} | "
                f"Frontend: {'Frozen' if self.is_frontend_frozen() else 'Active'} | "
                f"Time: {ep_duration:.1f}s"
            )

            # Save latest checkpoint
            torch.save({
                "epoch": epoch,
                "model_state_dict": self.model.state_dict(),
                "optimizer_state_dict": self.optimizer.state_dict(),
                "val_metrics": val_metrics,
                "config": self.config
            }, self.experiment_dir / "latest_model.pth")

            # Check if this epoch beats best fine-tuned validation MAE (epoch >= 1)
            improved = False
            if val_metrics["mae"] < best_finetuned_val_mae:
                best_finetuned_val_mae = val_metrics["mae"]
                best_finetuned_epoch = epoch
                improved = True
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": self.model.state_dict(),
                    "val_metrics": val_metrics,
                    "config": self.config
                }, self.experiment_dir / "best_finetuned_model.pth")
                self.logger.info(f"  >>> Best fine-tuned checkpoint saved (Epoch {epoch}, Val MAE: {best_finetuned_val_mae:.2f})")

            # Check if this epoch beats overall best validation MAE (including baseline)
            if val_metrics["mae"] < best_val_mae:
                best_val_mae = val_metrics["mae"]
                best_epoch = epoch
                torch.save({
                    "epoch": epoch,
                    "model_state_dict": self.model.state_dict(),
                    "val_metrics": val_metrics,
                    "config": self.config
                }, self.experiment_dir / "best_model.pth")
                self.logger.info(f"  >>> New overall best checkpoint saved (Val MAE: {best_val_mae:.2f})")

            # Early stopping check
            if patience > 0:
                if improved:
                    epochs_without_improvement = 0
                else:
                    epochs_without_improvement += 1
                    self.logger.info(f"  >>> Early stopping counter: {epochs_without_improvement}/{patience} epochs without improvement")
                    if epochs_without_improvement >= patience:
                        self.logger.info(
                            f"  >>> Early stopping triggered: Validation MAE did not improve for {patience} consecutive epochs. "
                            f"Stopping training early at epoch {epoch}."
                        )
                        early_stopped = True
                        break

        total_time = round(time.perf_counter() - start_time, 2)

        # Save training history
        with open(self.experiment_dir / "train_history.json", "w", encoding="utf-8") as f:
            json.dump({
                "baseline_val_metrics": baseline_val_metrics,
                "best_val_mae": best_val_mae,
                "best_epoch": best_epoch,
                "best_finetuned_val_mae": best_finetuned_val_mae if best_finetuned_epoch is not None else None,
                "best_finetuned_epoch": best_finetuned_epoch,
                "early_stopped": early_stopped,
                "stopped_epoch": history[-1]["epoch"] if history else 0,
                "total_training_time_seconds": total_time,
                "epochs": history
            }, f, indent=2)

        self.logger.info(
            f"Fine-tuning completed in {total_time}s. "
            f"Best Epoch: {best_epoch} (Val MAE: {best_val_mae:.2f}), "
            f"Best Fine-Tuned Epoch: {best_finetuned_epoch} (Val MAE: {best_finetuned_val_mae:.2f})"
        )

        return {
            "best_epoch": best_epoch,
            "best_val_mae": best_val_mae,
            "best_finetuned_epoch": best_finetuned_epoch,
            "best_finetuned_val_mae": best_finetuned_val_mae if best_finetuned_epoch is not None else None,
            "baseline_val_mae": baseline_val_metrics["mae"],
            "early_stopped": early_stopped,
            "experiment_dir": str(self.experiment_dir),
            "history": history
        }
