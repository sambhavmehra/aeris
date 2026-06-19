import torch
import torch.nn as nn


class IntentClassifierNet(nn.Module):
    """
    Deep feed-forward neural network for intent classification.
    
    Architecture:
      - 3 hidden layers with GELU activation and LayerNorm
      - Residual (skip) connection from projected input to final hidden layer
      - Dropout 0.4 for strong regularization
      - Designed for TF-IDF input vectors
    """
    def __init__(self, input_dim: int, hidden_dim: int, num_classes: int):
        super(IntentClassifierNet, self).__init__()

        # Project input to hidden_dim for residual connection
        self.input_proj = nn.Linear(input_dim, hidden_dim)

        # Layer 1
        self.layer1 = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Dropout(0.4),
        )

        # Layer 2
        self.layer2 = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.LayerNorm(hidden_dim // 2),
            nn.GELU(),
            nn.Dropout(0.4),
        )

        # Layer 3
        self.layer3 = nn.Sequential(
            nn.Linear(hidden_dim // 2, hidden_dim // 4),
            nn.LayerNorm(hidden_dim // 4),
            nn.GELU(),
            nn.Dropout(0.3),
        )

        # Residual projection: hidden_dim → hidden_dim // 4
        self.residual_proj = nn.Linear(hidden_dim, hidden_dim // 4)

        # Output head
        self.classifier = nn.Linear(hidden_dim // 4, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass with residual skip connection.
        Args:
            x: Input tensor of shape (batch_size, input_dim)
        Returns:
            Logits of shape (batch_size, num_classes)
        """
        # Project input to hidden space
        identity = self.input_proj(x)

        # Pass through hidden layers
        h = self.layer1(identity)
        h = self.layer2(h)
        h = self.layer3(h)

        # Add residual connection (projected to match dimensions)
        h = h + self.residual_proj(identity)

        # Classify
        return self.classifier(h)


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
