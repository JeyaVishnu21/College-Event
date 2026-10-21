"""
CSRNet Model Architecture (Stage 7)
-----------------------------------
Reference:
"CSRNet: Dilated Convolutional Neural Networks for Understanding the Highly Congested Scenes"
Yuhong Li, Xiaofan Zhang, Deming Chen (CVPR 2018)
Paper: https://arxiv.org/abs/1802.10062
Official Repository: https://github.com/leeyeehoo/CSRNet-pytorch

Network Structure:
- Frontend: First 10 convolutional layers of VGG-16 with 3 MaxPool2d downsamplings.
  Extracts hierarchical low-to-mid level visual features with 1/8 downsampling factor.
- Backend: 6 dilated convolutional layers (atrous convolutions with dilation rate = 2).
  Enlarges the receptive field to aggregate multi-scale contextual features without
  further loss of spatial resolution.
- Output Layer: 1x1 Convolution mapping 64 feature channels to a single continuous
  density map channel. The spatial sum over the density map yields the total headcount.
"""

from typing import List, Union
import torch
import torch.nn as nn


def make_layers(
    cfg: List[Union[int, str]],
    in_channels: int = 3,
    batch_norm: bool = False,
    dilation: bool = False
) -> nn.Sequential:
    """
    Constructs a sequential series of Conv2d (+ optional BatchNorm) + ReLU layers,
    interspersed with MaxPool2d downsampling when 'M' is encountered in `cfg`.
    """
    d_rate = 2 if dilation else 1
    layers: List[nn.Module] = []
    
    for v in cfg:
        if v == 'M':
            layers.append(nn.MaxPool2d(kernel_size=2, stride=2))
        else:
            conv2d = nn.Conv2d(
                in_channels=in_channels,
                out_channels=v,
                kernel_size=3,
                padding=d_rate,
                dilation=d_rate
            )
            if batch_norm:
                layers.extend([conv2d, nn.BatchNorm2d(v), nn.ReLU(inplace=True)])
            else:
                layers.extend([conv2d, nn.ReLU(inplace=True)])
            in_channels = v

    return nn.Sequential(*layers)


class CSRNet(nn.Module):
    """
    CSRNet implementation compatible with ShanghaiTech Part A and Part B checkpoints.
    Total Parameters: ~16.26 Million (~65 MB in float32 format).
    """

    def __init__(self, load_weights: bool = False):
        super(CSRNet, self).__init__()
        self.seen = 0

        # Frontend feature channels: conv1_1 through conv4_3 from VGG-16
        self.frontend_feat: List[Union[int, str]] = [
            64, 64, 'M', 128, 128, 'M', 256, 256, 256, 'M', 512, 512, 512
        ]
        # Backend feature channels: 6 dilated convolutions with dilation=2
        self.backend_feat: List[Union[int, str]] = [512, 512, 512, 256, 128, 64]

        # Construct frontend and dilated backend blocks
        self.frontend = make_layers(self.frontend_feat, in_channels=3, dilation=False)
        self.backend = make_layers(self.backend_feat, in_channels=512, dilation=True)

        # 1x1 Convolution to generate 1-channel continuous density map
        self.output_layer = nn.Conv2d(64, 1, kernel_size=1)

        if not load_weights:
            self._initialize_weights()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass producing spatial density map.
        Input: (B, 3, H, W) normalized RGB image tensor
        Output: (B, 1, H // 8, W // 8) predicted continuous density map
        """
        x = self.frontend(x)
        x = self.backend(x)
        x = self.output_layer(x)
        return x

    def _initialize_weights(self) -> None:
        """Standard Gaussian initialization for weights and zeros for biases."""
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.normal_(m.weight, std=0.01)
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
