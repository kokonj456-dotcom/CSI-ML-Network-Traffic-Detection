import torch
import torch.nn as nn


class Autoencoder(nn.Module):
    """Neural network สำหรับเรียนรู้รูปแบบข้อมูลปกติ (Normal / Benign) เพื่อตรวจจับ Anomaly

    สถาปัตยกรรม Symmetric Bottleneck รองรับทั้ง:
    - Quad-Domain Harmonized (19 core features): 19 -> 14 -> 8 -> 4 -> 8 -> 14 -> 19
    - ขนาดมิติอื่นๆ ตามที่กำหนดผ่าน input_dim / hidden_dims
    """

    def __init__(self, input_dim=19, hidden_dims=None):
        super().__init__()
        self.input_dim = input_dim

        if hidden_dims is None:
            if input_dim <= 25:
                hidden_dims = (14, 8, 4)
            else:
                hidden_dims = (64, 32, 16, 8)

        self.hidden_dims = tuple(hidden_dims)

        # Encoder: บีบอัดข้อมูลลงสู่ Latent Bottleneck
        enc_layers = []
        prev_dim = input_dim
        for h_dim in self.hidden_dims:
            enc_layers.append(nn.Linear(prev_dim, h_dim))
            enc_layers.append(nn.ReLU())
            prev_dim = h_dim
        self.encoder = nn.Sequential(*enc_layers)

        # Decoder: ขยายกลับจาก Bottleneck สู่มิติดั้งเดิม
        dec_layers = []
        reversed_dims = list(reversed(self.hidden_dims[:-1])) + [input_dim]
        for i, h_dim in enumerate(reversed_dims):
            dec_layers.append(nn.Linear(prev_dim, h_dim))
            if i < len(reversed_dims) - 1:
                dec_layers.append(nn.ReLU())
            prev_dim = h_dim
        self.decoder = nn.Sequential(*dec_layers)

    def forward(self, x):
        encoded = self.encoder(x)
        reconstructed = self.decoder(encoded)
        return reconstructed
