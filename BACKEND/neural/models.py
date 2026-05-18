import torch
import torch.nn as nn

class IntentClassifierNet(nn.Module):
    """
    Feed-forward neural network for intent classification.
    Assumes input is a pre-computed text embedding (e.g., from an external model or TF-IDF).
    """
    def __init__(self, input_dim: int, hidden_dim: int, num_classes: int):
        super(IntentClassifierNet, self).__init__()
        self.network = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.BatchNorm1d(hidden_dim // 2),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim // 2, num_classes)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass for intent classification.
        Args:
            x: Input tensor of shape (batch_size, input_dim)
        Returns:
            Logits of shape (batch_size, num_classes)
        """
        return self.network(x)


class AnomalyDetectorNet(nn.Module):
    """
    Autoencoder for detecting anomalous patterns in system or network data.
    """
    def __init__(self, input_dim: int, latent_dim: int):
        super(AnomalyDetectorNet, self).__init__()
        
        # Encoder
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Linear(64, latent_dim),
            nn.ReLU()
        )
        
        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 64),
            nn.ReLU(),
            nn.Linear(64, input_dim),
            nn.Sigmoid()  # Assuming normalized input features [0, 1]
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass for anomaly detection (autoencoder).
        Args:
            x: Input tensor of shape (batch_size, input_dim)
        Returns:
            Reconstructed tensor of shape (batch_size, input_dim)
        """
        latent = self.encoder(x)
        reconstructed = self.decoder(latent)
        return reconstructed
