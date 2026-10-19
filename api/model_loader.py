import torch
import torch.nn as nn
from pathlib import Path
import joblib

class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()

        self.conv = nn.Sequential(
            nn.Conv2d(
                in_channels,
                out_channels,
                kernel_size=3,
                padding=1
            ),
            nn.ReLU(inplace=True),

            nn.Conv2d(
                out_channels,
                out_channels,
                kernel_size=3,
                padding=1
            ),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        return self.conv(x)


class UNet(nn.Module):
    def __init__(self):
        super().__init__()

        # Encoder
        self.enc1 = DoubleConv(3, 64)
        self.enc2 = DoubleConv(64, 128)
        self.enc3 = DoubleConv(128, 256)

        self.pool = nn.MaxPool2d(2)

        # Bottleneck
        self.bottleneck = DoubleConv(256, 512)

        # Decoder
        self.up3 = nn.ConvTranspose2d(
            512, 256,
            kernel_size=2,
            stride=2
        )
        self.dec3 = DoubleConv(512, 256)

        self.up2 = nn.ConvTranspose2d(
            256, 128,
            kernel_size=2,
            stride=2
        )
        self.dec2 = DoubleConv(256, 128)

        self.up1 = nn.ConvTranspose2d(
            128, 64,
            kernel_size=2,
            stride=2
        )
        self.dec1 = DoubleConv(128, 64)

        # Final segmentation layer
        self.final = nn.Conv2d(
            64, 1,
            kernel_size=1
        )

    def forward(self, x):

        # Encoder
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))

        # Bottleneck
        b = self.bottleneck(self.pool(e3))

        # Decoder
        d3 = self.up3(b)
        d3 = torch.cat([d3, e3], dim=1)
        d3 = self.dec3(d3)

        d2 = self.up2(d3)
        d2 = torch.cat([d2, e2], dim=1)
        d2 = self.dec2(d2)

        d1 = self.up1(d2)
        d1 = torch.cat([d1, e1], dim=1)
        d1 = self.dec1(d1)

        return self.final(d1)


# Device
device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)


# Create model
model = UNet().to(device)


# Model path
MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "best_unet.pth"
)


# Load trained weights
model.load_state_dict(
    torch.load(
        MODEL_PATH,
        map_location=device
    )
)


# Evaluation mode
model.eval()

# ============================================================
# Rice Yield CNN
# ============================================================

class RiceYieldCNN(nn.Module):

    def __init__(self):
        super().__init__()

        self.features = nn.Sequential(

            # Block 1
            nn.Conv2d(
                in_channels=5,
                out_channels=32,
                kernel_size=3,
                padding=1
            ),
            nn.ReLU(),
            nn.MaxPool2d(2),

            # Block 2
            nn.Conv2d(
                in_channels=32,
                out_channels=64,
                kernel_size=3,
                padding=1
            ),
            nn.ReLU(),
            nn.MaxPool2d(2),

            # Block 3
            nn.Conv2d(
                in_channels=64,
                out_channels=128,
                kernel_size=3,
                padding=1
            ),
            nn.ReLU(),
            nn.MaxPool2d(2)
        )

        self.regressor = nn.Sequential(

            nn.Flatten(),

            nn.Linear(
                128 * 8 * 8,
                128
            ),
            nn.ReLU(),

            nn.Dropout(0.3),

            nn.Linear(
                128,
                1
            )
        )

    def forward(self, x):

        x = self.features(x)
        x = self.regressor(x)

        return x.squeeze(1)
    
# ============================================================
# Rice Yield CNN Model Loading
# ============================================================

yield_model = RiceYieldCNN().to(device)

YIELD_MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "best_rice_yield_model.pth"
)

yield_model.load_state_dict(
    torch.load(
        YIELD_MODEL_PATH,
        map_location=device
    )
)

yield_model.eval()

#here ml model for rice yield prediction is loaded using joblib.
ML_MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "final_rice_yield_model.pkl"
)

agricultural_model = joblib.load(
    ML_MODEL_PATH
)