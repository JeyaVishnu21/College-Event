"""
CSRNet Fine-Tuning Pipeline Package
-----------------------------------
Provides an isolated, memory-conscious fine-tuning and evaluation workflow
for adapting CSRNet on college-event crowd photographs.
"""

from .density_map import generate_density_map, load_points_from_file
from .dataset import CrowdDataset, DatasetValidator
from .trainer import CSRNetFineTuner
from .evaluator import CrowdEvaluator

__all__ = [
    'generate_density_map',
    'load_points_from_file',
    'CrowdDataset',
    'DatasetValidator',
    'CSRNetFineTuner',
    'CrowdEvaluator',
]
