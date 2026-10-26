import torch.nn as nn


class ConvBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),
        )

    def forward(self, x):
        return self.block(x)


class PaddyDoctorCNN(nn.Module):
    def __init__(self, class_count: int):
        super().__init__()
        self.features = nn.Sequential(
            ConvBlock(3, 24), ConvBlock(24, 48),
            ConvBlock(48, 96), ConvBlock(96, 128),
            nn.AdaptiveAvgPool2d(1), nn.Flatten(),
        )
        self.classifier = nn.Sequential(nn.Dropout(0.25), nn.Linear(128, class_count))

    def forward(self, x):
        return self.classifier(self.features(x))
