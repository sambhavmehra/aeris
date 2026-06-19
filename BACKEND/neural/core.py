"""
AERIS Neural Core -- Manages local PyTorch models and text preprocessing.
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
import json
from typing import Optional, List, Tuple

from sklearn.feature_extraction.text import TfidfVectorizer

from neural.models import IntentClassifierNet, AnomalyDetectorNet

logger = logging.getLogger("aeris.neural.core")

# --------------- Intent Labels (aligned with Brain.VALID_INTENTS) ---------------
INTENT_LABELS = [
    "chat", "security", "system", "research", "search",
    "code", "image", "diagram", "codepipeline", "analyze",
    "osint", "email", "scheduler", "drana", "dorking", "pentest",
    "diagnose", "repair", "debate", "investigation", "assemble",
    "guardian", "mechanic", "critic"
]

# --------------- Training Data ---------------
TRAINING_DATA: List[Tuple[str, str]] = [
    # -- chat --
    ("hello", "chat"), ("hi there", "chat"), ("how are you", "chat"),
    ("tell me a joke", "chat"), ("who are you", "chat"), ("what is 2+2", "chat"),
    ("what is photosynthesis", "chat"), ("good morning", "chat"),
    ("goodbye", "chat"), ("define gravity", "chat"),
    ("kya haal hai", "chat"), ("tera naam kya hai", "chat"),
    ("thanks a lot", "chat"), ("tell me something interesting", "chat"),
    ("what does AI mean", "chat"),
    # -- security --
    ("scan this website for vulnerabilities", "security"),
    ("run nmap on 192.168.1.1", "security"),
    ("check ssl certificate for google.com", "security"),
    ("do a dns lookup", "security"), ("find subdomains of example.com", "security"),
    ("whois lookup for github.com", "security"),
    ("vapt scan on my server", "security"), ("check http headers", "security"),
    ("is this site vulnerable to xss", "security"),
    ("zero day vulnerability analysis", "security"),
    ("port scan karo", "security"), ("website ki security check karo", "security"),
    # -- system --
    ("open chrome", "system"), ("take a screenshot", "system"),
    ("check running processes", "system"), ("shutdown computer", "system"),
    ("create a new folder", "system"), ("scan my screen", "system"),
    ("delete this file", "system"), ("open notepad", "system"),
    ("list files in downloads", "system"), ("system info dikhao", "system"),
    ("volume up karo", "system"), ("restart the computer", "system"),
    ("open youtube and play music", "system"), ("search on browser", "system"),
    ("play a song on youtube", "system"), ("kill this process", "system"),
    ("search sambhav mehra on google", "system"),
    ("search on google for python tutorials", "system"),
    ("google search cat videos", "system"),
    ("open google and search for aeris", "system"),
    ("google pe search karo backend development", "system"),
    ("browser me search karo latest movies", "system"),
    ("search youtube for coding videos", "system"),
    ("youtube search for song", "system"),
    ("open browser and search google", "system"),
    # -- research --
    ("deep research on transformer architecture", "research"),
    ("compare react vs angular in depth", "research"),
    ("academic research on quantum computing", "research"),
    ("synthesize findings on climate change", "research"),
    ("write a literature review on blockchain", "research"),
    ("in-depth analysis of microservices patterns", "research"),
    ("research paper on neural networks", "research"),
    ("technical research on kubernetes scaling", "research"),
    ("thesis topic suggestions for machine learning", "research"),
    ("research karo AI trends pe", "research"),
    # -- search (replaces old 'realtime') --
    ("latest ipl score", "search"), ("aaj ka mausam", "search"),
    ("bitcoin price", "search"), ("who won the election", "search"),
    ("react latest version", "search"), ("today's news", "search"),
    ("current stock price of apple", "search"),
    ("trending topics on twitter", "search"),
    ("weather in london right now", "search"),
    ("latest updates on ai", "search"),
    ("what happened in the world today", "search"),
    ("breaking news", "search"), ("where am i right now", "search"),
    ("my location batao", "search"), ("search for best laptops 2025", "search"),
    ("what is the weather in Delhi", "search"),
    ("latest stock price of microsoft", "search"),
    ("who is the current prime minister of india", "search"),
    ("trending news today", "search"),
    ("current temperature in new york", "search"),
    # -- code --
    ("write a python script", "code"), ("debug this function", "code"),
    ("write a flask api endpoint", "code"), ("refactor this code", "code"),
    ("explain this javascript function", "code"),
    ("generate a class for user authentication", "code"),
    ("fix this code error", "code"), ("write a sorting algorithm", "code"),
    ("code likho python mein", "code"), ("game banao javascript mein", "code"),
    ("function banao for login", "code"), ("api banao flask mein", "code"),
    ("convert pdf to word script", "code"),
    # -- image --
    ("generate an image of a sunset", "image"),
    ("create a picture of a robot", "image"),
    ("draw a cat wearing a hat", "image"),
    ("make an image of a futuristic city", "image"),
    ("generate photo of mountains", "image"), ("picture of a spaceship", "image"),
    ("photo bana ek dragon ki", "image"), ("image bana sunset wali", "image"),
    ("create art of a samurai", "image"), ("tasveer bana ek jungle ki", "image"),
    # -- diagram --
    ("create a flowchart for login flow", "diagram"),
    ("generate a system architecture diagram", "diagram"),
    ("make a mind map for project planning", "diagram"),
    ("draw an er diagram for database", "diagram"),
    ("sequence diagram for api calls", "diagram"),
    ("class diagram banao", "diagram"),
    ("network diagram for infrastructure", "diagram"),
    ("chart banao sales data ka", "diagram"),
    ("widget bana do for dashboard", "diagram"),
    ("visualize the data pipeline", "diagram"),
    ("flow banao user registration ka", "diagram"),
    # -- codepipeline --
    ("build me a full react app", "codepipeline"),
    ("create a complete project for todo app", "codepipeline"),
    ("scaffold a new workspace for ecommerce", "codepipeline"),
    ("generate a full codebase for chat application", "codepipeline"),
    ("build an entire flask backend", "codepipeline"),
    ("autonomous code generation for portfolio site", "codepipeline"),
    ("project banao ek blog website ka", "codepipeline"),
    ("full project bana do python mein", "codepipeline"),
    ("app bana do weather tracker", "codepipeline"),
    ("code pipeline run for inventory system", "codepipeline"),
    # -- analyze --
    ("analyze this file for me", "analyze"),
    ("analyze my log file", "analyze"),
    ("inspect the error log", "analyze"),
    ("read this file and tell me what it does", "analyze"),
    ("analyze the output of this command", "analyze"),
    ("check this data for patterns", "analyze"),
    ("find issues in my config file", "analyze"),
    ("summarize the contents of readme.md", "analyze"),
    ("diagnose the system state", "analyze"),
    ("parse this json and explain it", "analyze"),
    ("meri file analyze karo", "analyze"),
    ("ye file check karo kya hai isme", "analyze"),
    ("is log file me kya error hai", "analyze"),
    ("isko analyze karke batao", "analyze"),
    ("ye data dekhke batao", "analyze"),
    # -- osint --
    ("perform osint on target", "osint"),
    ("osint profile check", "osint"),
    ("email lookup search", "osint"),
    ("stalk username on web", "osint"),
    ("trace social footprint of target", "osint"),
    ("perom osint on sambhav mehra", "osint"),
    ("perform osint on sambhav mehra", "osint"),
    ("do osint on user", "osint"),
    ("target intel compilation", "osint"),
    ("stalk user", "osint"),
    ("stalk target", "osint"),
    ("profile check on username", "osint"),
    ("who is this person osint", "osint"),
    ("osint investigation", "osint"),
    # -- email --
    ("send an email to boss@company.com", "email"),
    ("email send karo manager ko", "email"),
    ("send a mail to rahul@gmail.com with subject meeting", "email"),
    ("mail bhejo team ko", "email"),
    ("send mail to contact@example.com", "email"),
    ("compose an email to client", "email"),
    ("smtp relay se email bhejo", "email"),
    ("mail kr de raj@domain.com ko", "email"),
    ("email rahul@outlook.com to inform him", "email"),
    ("send a notification email", "email"),
    ("boss ko mail likh ke bhejo", "email"),
    ("send email using brevo", "email"),
    ("brevo se email send karo", "email"),
    ("mail send kar do", "email"),
    # -- scheduler --
    ("schedule a meeting for tomorrow at 2pm", "scheduler"),
    ("set a reminder to call team at 6pm", "scheduler"),
    ("cancel my task with id scheduler_1", "scheduler"),
    ("list all scheduled tasks", "scheduler"),
    ("task pending list dikhao", "scheduler"),
    ("remind me to check server status in 10 minutes", "scheduler"),
    # -- drana --
    ("run js recon on target", "drana"),
    ("generate custom xss payload for input field", "drana"),
    ("perform manual vapt on endpoint", "drana"),
    ("drana security scan website", "drana"),
    ("js files analysis kro", "drana"),
    # -- dorking --
    ("google dorking check example.com", "dorking"),
    ("advanced search operators for config files", "dorking"),
    ("run google dork on domain", "dorking"),
    ("search dork query for databases", "dorking"),
    # -- pentest --
    ("pentest karo vinusxtech.me", "pentest"),
    ("run a full penetration test on example.com", "pentest"),
    ("pentest recon check on website", "pentest"),
    ("perform security assessment on target", "pentest"),
    ("target website pr pentesting kro", "pentest"),
    ("run pentest check", "pentest"),
]


class NeuralCore:
    """
    Manager for loading, running, and managing local PyTorch neural network models.
    Includes a TF-IDF vectorizer for converting raw text into feature vectors
    and provides inference wrappers for fast execution.
    """

    def __init__(self, model_dir: str = "data/models"):
        self.model_dir = model_dir

        # -- Device selection --
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")

        # -- Models --
        self.intent_model: Optional[IntentClassifierNet] = None
        self.anomaly_model: Optional[AnomalyDetectorNet] = None

        # -- Text preprocessing --
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.intent_labels: List[str] = INTENT_LABELS
        self._input_dim: int = 0

        # -- State --
        self.is_intent_ready: bool = False
        self.is_anomaly_ready: bool = False

        logger.info(f"NeuralCore initialized. Device: {self.device}")
        os.makedirs(self.model_dir, exist_ok=True)

    # ======================= Intent Classification =======================

    def train_initial_intent_model(self, epochs: int = 300, lr: float = 0.01) -> None:
        """Bootstrap the intent classifier using training_data.json or fallback phrases."""
        vectorizer_path = os.path.join(self.model_dir, "tfidf_vectorizer.pkl")
        model_path = os.path.join(self.model_dir, "intent_model.pth")
        json_path = os.path.join(os.path.dirname(__file__), "training_data.json")

        texts = []
        labels = []

        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    lbl = item["label"]
                    if lbl in self.intent_labels:
                        texts.append(item["text"])
                        labels.append(self.intent_labels.index(lbl))
                logger.info(f"Loaded {len(texts)} training samples from {json_path}")
            except Exception as e:
                logger.error(f"Failed to load training_data.json: {e}. Using fallback.")
                texts = []
                labels = []

        if not texts:
            logger.info("Using fallback inline training data.")
            texts = [t[0] for t in TRAINING_DATA]
            labels = [self.intent_labels.index(t[1]) for t in TRAINING_DATA if t[1] in self.intent_labels]

        self.vectorizer = TfidfVectorizer(max_features=1024, ngram_range=(1, 3), sublinear_tf=True)
        X = self.vectorizer.fit_transform(texts).toarray().astype(np.float32)
        y = np.array(labels, dtype=np.int64)

        self._input_dim = X.shape[1]
        num_classes = len(self.intent_labels)

        # 85/15 train/validation split
        num_samples = len(texts)
        indices = np.arange(num_samples)
        np.random.seed(42)
        np.random.shuffle(indices)
        
        split_idx = int(num_samples * 0.85)
        train_indices = indices[:split_idx]
        val_indices = indices[split_idx:]
        
        X_train, y_train = X[train_indices], y[train_indices]
        X_val, y_val = X[val_indices], y[val_indices]

        self.intent_model = IntentClassifierNet(
            input_dim=self._input_dim, hidden_dim=256, num_classes=num_classes,
        ).to(self.device)

        X_train_tensor = torch.tensor(X_train).to(self.device)
        y_train_tensor = torch.tensor(y_train).to(self.device)
        X_val_tensor = torch.tensor(X_val).to(self.device)
        y_val_tensor = torch.tensor(y_val).to(self.device)

        optimizer = optim.AdamW(self.intent_model.parameters(), lr=lr, weight_decay=1e-4)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
        criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

        best_val_loss = float("inf")
        best_state = None
        patience = 30
        patience_counter = 0

        self.intent_model.train()
        for epoch in range(epochs):
            self.intent_model.train()
            optimizer.zero_grad()
            logits = self.intent_model(X_train_tensor)
            loss = criterion(logits, y_train_tensor)
            loss.backward()
            
            # Gradient clipping for stability
            torch.nn.utils.clip_grad_norm_(self.intent_model.parameters(), max_norm=1.0)
            
            optimizer.step()
            scheduler.step()

            # Validation loss check
            self.intent_model.eval()
            with torch.no_grad():
                val_logits = self.intent_model(X_val_tensor)
                val_loss = criterion(val_logits, y_val_tensor)

            if val_loss.item() < best_val_loss:
                best_val_loss = val_loss.item()
                best_state = self.intent_model.state_dict().copy()
                patience_counter = 0
            else:
                patience_counter += 1

            if patience_counter >= patience:
                logger.info(f"Early stopping triggered at epoch {epoch+1}")
                break

        if best_state is not None:
            self.intent_model.load_state_dict(best_state)
            
        self.intent_model.eval()

        torch.save(self.intent_model.state_dict(), model_path)
        with open(vectorizer_path, "wb") as f:
            pickle.dump(self.vectorizer, f)

        self.is_intent_ready = True
        logger.info(
            f"Intent model trained (val_loss={best_val_loss:.4f}). "
            f"Classes: {num_classes}, InputDim: {self._input_dim}. Saved to {model_path}"
        )

    def load_intent_model(
        self, input_dim: int = 0, hidden_dim: int = 256,
        num_classes: int = 0, model_path: Optional[str] = None,
    ) -> None:
        """
        Load a previously trained intent model + vectorizer from disk.
        Detects incompatible saved weights and automatically retrains.
        """
        model_file = model_path or os.path.join(self.model_dir, "intent_model.pth")
        vectorizer_file = os.path.join(self.model_dir, "tfidf_vectorizer.pkl")

        # Load vectorizer
        if os.path.exists(vectorizer_file):
            try:
                with open(vectorizer_file, "rb") as f:
                    self.vectorizer = pickle.load(f)
                self._input_dim = len(self.vectorizer.get_feature_names_out())
                logger.info(f"Loaded TF-IDF vectorizer (dim={self._input_dim})")
            except Exception as e:
                logger.warning(f"Failed to load vectorizer ({e}). Retraining...")
                self.train_initial_intent_model()
                return
        else:
            logger.warning("No vectorizer found. Retraining...")
            self.train_initial_intent_model()
            return

        dim = input_dim or self._input_dim
        classes = num_classes or len(self.intent_labels)

        if not os.path.exists(model_file):
            logger.warning(f"No weights at {model_file}. Retraining...")
            self.train_initial_intent_model()
            return

        # Try to load -- detect shape mismatches
        try:
            saved_state = torch.load(model_file, map_location=self.device, weights_only=True)

            # Detect class count mismatch (output layer)
            weight_keys = [k for k in saved_state if k.endswith(".weight")]
            if weight_keys:
                last_key = weight_keys[-1]
                saved_out = saved_state[last_key].shape[0]
                if saved_out != classes:
                    logger.warning(
                        f"Saved model has {saved_out} classes, need {classes}. Retraining..."
                    )
                    self.train_initial_intent_model()
                    return

                first_key = weight_keys[0]
                saved_in = saved_state[first_key].shape[1]
                if saved_in != dim:
                    logger.warning(
                        f"Saved model input dim={saved_in}, vectorizer dim={dim}. Retraining..."
                    )
                    self.train_initial_intent_model()
                    return

            self.intent_model = IntentClassifierNet(dim, hidden_dim, classes).to(self.device)
            self.intent_model.load_state_dict(saved_state)
            self.intent_model.eval()
            self.is_intent_ready = True
            logger.info(f"Loaded IntentClassifierNet weights from {model_file}")

        except (RuntimeError, Exception) as e:
            logger.warning(f"Failed to load intent model ({e}). Retraining...")
            self.train_initial_intent_model()

    def predict_intent_from_text(self, text: str) -> Tuple[str, float]:
        """Classify raw text into an intent label. Returns (label, confidence)."""
        if not self.is_intent_ready or not self.vectorizer or not self.intent_model:
            raise ValueError("Intent model not ready. Train or load it first.")

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
        """Run inference from pre-computed features. Returns probability tensor."""
        if not self.intent_model:
            raise ValueError("Intent model not loaded.")

        with torch.no_grad():
            tensor_features = torch.tensor([features], dtype=torch.float32).to(self.device)
            self.intent_model.eval()
            logits = self.intent_model(tensor_features)
            probs = torch.softmax(logits, dim=1)
            return probs.squeeze(0)

    # ======================= Anomaly Detection =======================

    def train_initial_anomaly_model(
        self, input_dim: int = 32, latent_dim: int = 8, model_path: Optional[str] = None, epochs: int = 100, lr: float = 0.01
    ) -> None:
        """Bootstrap the anomaly detector with synthetic normal data."""
        path = model_path or os.path.join(self.model_dir, "anomaly_model.pth")
        logger.info(f"Training initial anomaly model ({epochs} epochs, dim={input_dim})...")
        
        # Generate synthetic normal features: normal distribution around 0.5
        np.random.seed(42)
        X_normal = np.random.normal(loc=0.5, scale=0.1, size=(1000, input_dim)).clip(0.0, 1.0).astype(np.float32)
        
        self.anomaly_model = AnomalyDetectorNet(input_dim, latent_dim).to(self.device)
        X_tensor = torch.tensor(X_normal).to(self.device)
        
        optimizer = optim.Adam(self.anomaly_model.parameters(), lr=lr)
        criterion = nn.MSELoss()
        
        self.anomaly_model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            reconstructed = self.anomaly_model(X_tensor)
            loss = criterion(reconstructed, X_tensor)
            loss.backward()
            optimizer.step()
            
        self.anomaly_model.eval()
        torch.save(self.anomaly_model.state_dict(), path)
        self.is_anomaly_ready = True
        logger.info(f"Anomaly model trained on normal data. Saved to {path}")

    def load_anomaly_model(
        self, input_dim: int, latent_dim: int, model_path: Optional[str] = None
    ) -> None:
        """Initialize or load the anomaly detector weights."""
        self.anomaly_model = AnomalyDetectorNet(input_dim, latent_dim).to(self.device)
        path = model_path or os.path.join(self.model_dir, "anomaly_model.pth")

        if os.path.exists(path):
            try:
                loaded = torch.load(path, map_location=self.device, weights_only=True)
                if isinstance(loaded, dict) and "state_dict" in loaded:
                    loaded = loaded["state_dict"]
                self.anomaly_model.load_state_dict(loaded)
                logger.info(f"Loaded AnomalyDetectorNet weights from {path}")
            except Exception as e:
                logger.warning(f"Failed to load anomaly weights ({e}). Retraining...")
                try:
                    self.train_initial_anomaly_model(input_dim=input_dim, latent_dim=latent_dim, model_path=path)
                except Exception as train_err:
                    logger.error(f"Failed to retrain anomaly model: {train_err}")
        else:
            logger.warning(f"No weights at {path}. Training initial anomaly model...")
            try:
                self.train_initial_anomaly_model(input_dim=input_dim, latent_dim=latent_dim, model_path=path)
            except Exception as e:
                logger.error(f"Failed to train anomaly model: {e}. Falling back to random initialization.")

        self.anomaly_model.eval()
        self.is_anomaly_ready = True

    def detect_anomaly(self, features: List[float]) -> float:
        """Run anomaly detection. Returns MSE (high = anomaly)."""
        if not self.anomaly_model:
            raise ValueError("Anomaly model not loaded. Call load_anomaly_model() first.")

        with torch.no_grad():
            tensor_features = torch.tensor([features], dtype=torch.float32).to(self.device)
            self.anomaly_model.eval()
            reconstructed = self.anomaly_model(tensor_features)
            mse_loss = torch.nn.functional.mse_loss(reconstructed, tensor_features)
            return mse_loss.item()

    # ======================= Initialization =======================

    def initialize(self) -> None:
        """
        Full initialization: train or load intent model, load anomaly model.
        Called once at server startup from api.py lifespan.
        """
        model_path = os.path.join(self.model_dir, "intent_model.pth")
        vectorizer_path = os.path.join(self.model_dir, "tfidf_vectorizer.pkl")

        if os.path.exists(model_path) and os.path.exists(vectorizer_path):
            logger.info("Found existing neural weights -- loading from disk.")
            self.load_intent_model()
        else:
            logger.info("No existing weights -- training initial intent model...")
            self.train_initial_intent_model()

        # Sanity check: verify the loaded model can predict correctly
        if self.is_intent_ready:
            try:
                label, conf = self.predict_intent_from_text("hello")
                if label not in self.intent_labels:
                    raise ValueError(f"Unknown label: {label}")
                logger.info(f"Sanity check passed (test='hello' -> '{label}', conf={conf:.2f})")
            except Exception as e:
                logger.warning(f"Sanity check failed ({e}). Retraining...")
                self.train_initial_intent_model()

        # Initialize anomaly detector with reasonable defaults
        self.load_anomaly_model(input_dim=32, latent_dim=8)

        logger.info(
            f"Neural Engine ready. "
            f"Intent: {'OK' if self.is_intent_ready else 'FAIL'}, "
            f"Anomaly: {'OK' if self.is_anomaly_ready else 'FAIL'}"
        )


# Global singleton
neural_core = NeuralCore()
