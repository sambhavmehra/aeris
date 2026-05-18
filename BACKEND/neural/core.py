"""
AERIS Neural Core — Manages local PyTorch models and text preprocessing.
Provides fast, zero-latency intent classification and anomaly detection
without requiring external API calls.
"""

import os
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import logging
import pickle
from typing import Optional, List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer

from neural.models import IntentClassifierNet, AnomalyDetectorNet

logger = logging.getLogger("aeris.neural.core")

# ─────────────────────── Training Data ───────────────────────
# Sample phrases for each intent class used to bootstrap the model on startup.
# The Brain can retrain later with real user data for improved accuracy.

INTENT_LABELS = ["chat", "realtime", "os_engine"]

TRAINING_DATA: List[Tuple[str, str]] = [
    # ── Chat ──
    ("hello", "chat"),
    ("hi there", "chat"),
    ("how are you", "chat"),
    ("tell me a joke", "chat"),
    ("who are you", "chat"),
    ("what is 2+2", "chat"),
    ("what is photosynthesis", "chat"),
    ("good morning", "chat"),
    ("goodbye", "chat"),
    ("define gravity", "chat"),

    # ── Realtime ──
    ("latest ipl score", "realtime"),
    ("aaj ka mausam", "realtime"),
    ("bitcoin price", "realtime"),
    ("who won the election", "realtime"),
    ("react latest version", "realtime"),
    ("today's news", "realtime"),
    ("current stock price of apple", "realtime"),
    ("trending topics on twitter", "realtime"),
    ("weather in london right now", "realtime"),
    ("latest updates on ai", "realtime"),

    # ── OS Engine ──
    ("open chrome", "os_engine"),
    ("take a screenshot", "os_engine"),
    ("write a python script", "os_engine"),
    ("convert pdf to word", "os_engine"),
    ("check running processes", "os_engine"),
    ("shutdown computer", "os_engine"),
    ("create a new folder", "os_engine"),
    ("generate a diagram", "os_engine"),
    ("scan my screen", "os_engine"),
    ("delete this file", "os_engine"),
]


class NeuralCore:
    """
    Manager for loading, running, and managing local PyTorch neural network models.
    Includes a TF-IDF vectorizer for converting raw text into feature vectors
    and provides inference wrappers for fast execution.
    """

    def __init__(self, model_dir: str = "data/models"):
        self.model_dir = model_dir

        # ── Device selection ──
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")

        # ── Models ──
        self.intent_model: Optional[IntentClassifierNet] = None
        self.anomaly_model: Optional[AnomalyDetectorNet] = None

        # ── Text preprocessing ──
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.intent_labels: List[str] = INTENT_LABELS
        self._input_dim: int = 0  # Set after vectorizer fitting

        # ── State ──
        self.is_intent_ready: bool = False
        self.is_anomaly_ready: bool = False

        logger.info(f"NeuralCore initialized. Device: {self.device}")
        os.makedirs(self.model_dir, exist_ok=True)

    # ═══════════════════════ Intent Classification ═══════════════════════

    def train_initial_intent_model(self, epochs: int = 150, lr: float = 0.01) -> None:
        """
        Bootstrap the intent classifier using built-in training phrases.
        Uses TF-IDF to vectorize text and trains an MLP with cross-entropy loss.
        Called once at server startup.
        """
        vectorizer_path = os.path.join(self.model_dir, "tfidf_vectorizer.pkl")
        model_path = os.path.join(self.model_dir, "intent_model.pth")

        texts = [t[0] for t in TRAINING_DATA]
        labels = [self.intent_labels.index(t[1]) for t in TRAINING_DATA]

        # ── Fit TF-IDF ──
        self.vectorizer = TfidfVectorizer(max_features=128, ngram_range=(1, 2))
        X = self.vectorizer.fit_transform(texts).toarray().astype(np.float32)
        y = np.array(labels, dtype=np.int64)

        self._input_dim = X.shape[1]
        num_classes = len(self.intent_labels)

        # ── Build model ──
        self.intent_model = IntentClassifierNet(
            input_dim=self._input_dim,
            hidden_dim=256,
            num_classes=num_classes,
        ).to(self.device)

        # ── Train ──
        X_tensor = torch.tensor(X).to(self.device)
        y_tensor = torch.tensor(y).to(self.device)

        optimizer = optim.Adam(self.intent_model.parameters(), lr=lr)
        criterion = nn.CrossEntropyLoss()

        self.intent_model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            logits = self.intent_model(X_tensor)
            loss = criterion(logits, y_tensor)
            loss.backward()
            optimizer.step()

        self.intent_model.eval()

        # ── Persist weights & vectorizer ──
        torch.save(self.intent_model.state_dict(), model_path)
        with open(vectorizer_path, "wb") as f:
            pickle.dump(self.vectorizer, f)

        self.is_intent_ready = True
        final_loss = loss.item()
        logger.info(
            f"Intent model trained ({epochs} epochs, loss={final_loss:.4f}). "
            f"Saved to {model_path}"
        )

    def load_intent_model(
        self,
        input_dim: int = 0,
        hidden_dim: int = 256,
        num_classes: int = 0,
        model_path: Optional[str] = None,
    ) -> None:
        """Load a previously trained intent model + vectorizer from disk."""
        model_file = model_path or os.path.join(self.model_dir, "intent_model.pth")
        vectorizer_file = os.path.join(self.model_dir, "tfidf_vectorizer.pkl")

        # Load vectorizer
        if os.path.exists(vectorizer_file):
            with open(vectorizer_file, "rb") as f:
                self.vectorizer = pickle.load(f)
            self._input_dim = len(self.vectorizer.get_feature_names_out())
            logger.info(f"Loaded TF-IDF vectorizer (dim={self._input_dim})")
        else:
            logger.warning("No vectorizer found. Call train_initial_intent_model() first.")
            return

        dim = input_dim or self._input_dim
        classes = num_classes or len(self.intent_labels)
        self.intent_model = IntentClassifierNet(dim, hidden_dim, classes).to(self.device)

        if os.path.exists(model_file):
            self.intent_model.load_state_dict(
                torch.load(model_file, map_location=self.device, weights_only=True)
            )
            self.intent_model.eval()
            self.is_intent_ready = True
            logger.info(f"Loaded IntentClassifierNet weights from {model_file}")
        else:
            logger.warning(f"No weights at {model_file}. Model is randomly initialized.")

    def predict_intent_from_text(self, text: str) -> Tuple[str, float]:
        """
        Classify a raw text message into an intent label.
        Returns (intent_label, confidence) — e.g. ("security", 0.93).
        """
        if not self.is_intent_ready or not self.vectorizer or not self.intent_model:
            raise ValueError("Intent model not ready. Train or load it first.")

        # Vectorize
        features = self.vectorizer.transform([text]).toarray().astype(np.float32)

        with torch.no_grad():
            tensor = torch.tensor(features).to(self.device)
            self.intent_model.eval()
            logits = self.intent_model(tensor)
            probs = torch.softmax(logits, dim=1).squeeze(0)

        confidence, idx = probs.max(dim=0)
        label = self.intent_labels[idx.item()]
        return label, confidence.item()

    def predict_intent(self, features: List[float]) -> torch.Tensor:
        """
        Run inference for intent classification from pre-computed features.
        Returns a tensor of probabilities for each class.
        """
        if not self.intent_model:
            raise ValueError("Intent model not loaded.")

        with torch.no_grad():
            tensor_features = torch.tensor([features], dtype=torch.float32).to(self.device)
            self.intent_model.eval()
            logits = self.intent_model(tensor_features)
            probs = torch.softmax(logits, dim=1)
            return probs.squeeze(0)

    # ═══════════════════════ Anomaly Detection ═══════════════════════

    def load_anomaly_model(
        self, input_dim: int, latent_dim: int, model_path: Optional[str] = None
    ) -> None:
        """Initialize or load the anomaly detector weights."""
        self.anomaly_model = AnomalyDetectorNet(input_dim, latent_dim).to(self.device)
        path = model_path or os.path.join(self.model_dir, "anomaly_model.pth")

        if os.path.exists(path):
            self.anomaly_model.load_state_dict(
                torch.load(path, map_location=self.device, weights_only=True)
            )
            logger.info(f"Loaded AnomalyDetectorNet weights from {path}")
        else:
            logger.warning(f"No weights at {path}. AnomalyDetectorNet randomly initialized.")

        self.anomaly_model.eval()
        self.is_anomaly_ready = True

    def detect_anomaly(self, features: List[float]) -> float:
        """
        Run inference for anomaly detection.
        Returns the Mean Squared Error (reconstruction error).
        High MSE → Likely an anomaly.
        """
        if not self.anomaly_model:
            raise ValueError("Anomaly model not loaded. Call load_anomaly_model() first.")

        with torch.no_grad():
            tensor_features = torch.tensor([features], dtype=torch.float32).to(self.device)
            self.anomaly_model.eval()
            reconstructed = self.anomaly_model(tensor_features)
            mse_loss = torch.nn.functional.mse_loss(reconstructed, tensor_features)
            return mse_loss.item()

    # ═══════════════════════ Initialization ═══════════════════════

    def initialize(self) -> None:
        """
        Full initialization: train or load intent model, load anomaly model.
        Called once at server startup from api.py lifespan.
        """
        model_path = os.path.join(self.model_dir, "intent_model.pth")
        vectorizer_path = os.path.join(self.model_dir, "tfidf_vectorizer.pkl")

        if os.path.exists(model_path) and os.path.exists(vectorizer_path):
            logger.info("Found existing neural weights — loading from disk.")
            self.load_intent_model()
        else:
            logger.info("No existing weights — training initial intent model...")
            self.train_initial_intent_model()

        # Initialize anomaly detector with reasonable defaults
        self.load_anomaly_model(input_dim=32, latent_dim=8)

        logger.info(
            f"Neural Engine ready. Intent: {'✓' if self.is_intent_ready else '✗'}, "
            f"Anomaly: {'✓' if self.is_anomaly_ready else '✗'}"
        )


# Global singleton
neural_core = NeuralCore()
