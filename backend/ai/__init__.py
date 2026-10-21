"""
AI Crowd Counting Module (Stage 7)
----------------------------------
Provides deep learning based crowd density estimation and headcount prediction
using the CSRNet (Dilated Convolutional Neural Networks for Understanding
the Highly Congested Scenes - CVPR 2018) architecture.
"""

from .model import CSRNet, make_layers
from .predictor import CrowdPredictor, get_default_predictor

__all__ = [
    'CSRNet',
    'make_layers',
    'CrowdPredictor',
    'get_default_predictor'
]
