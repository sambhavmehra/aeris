"""
AERIS AI OS - Machine Learning Service
Provides ML capabilities using scikit-learn and numpy: Linear Regression,
K-Means Clustering, and Data Classification.
"""
import logging
from typing import Dict, Any, List

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier

logger = logging.getLogger("aeris.services.ml")


class MLService:
    """Service wrapping Scikit-Learn algorithms for system automation and prediction."""

    def __init__(self):
        pass

    def predict_linear_regression(self, x_vals: List[float], y_vals: List[float], target_x: float) -> Dict[str, Any]:
        """
        Train a Linear Regression model on x_vals and y_vals,
        and predict the value for target_x.
        """
        try:
            if len(x_vals) < 2 or len(y_vals) < 2:
                return {"success": False, "error": "At least 2 data points are required for regression."}
            if len(x_vals) != len(y_vals):
                return {"success": False, "error": "Dimensions of X and Y values must match."}

            X = np.array(x_vals).reshape(-1, 1)
            y = np.array(y_vals)

            model = LinearRegression()
            model.fit(X, y)

            prediction = float(model.predict(np.array([[target_x]]))[0])
            r2_score = float(model.score(X, y))
            slope = float(model.coef_[0])
            intercept = float(model.intercept_)

            return {
                "success": True,
                "prediction": prediction,
                "r2_score": r2_score,
                "equation": f"y = {slope:.4f}x + {intercept:.4f}",
                "slope": slope,
                "intercept": intercept
            }
        except Exception as e:
            logger.error(f"Linear regression prediction failed: {e}")
            return {"success": False, "error": str(e)}

    def cluster_kmeans(self, coordinates: List[List[float]], n_clusters: int = 2) -> Dict[str, Any]:
        """
        Perform K-Means clustering on multidimensional coordinate lists.
        """
        try:
            if not coordinates or len(coordinates) < n_clusters:
                return {"success": False, "error": "Number of data points must be greater than or equal to n_clusters."}

            X = np.array(coordinates)
            
            model = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
            model.fit(X)

            centroids = model.cluster_centers_.tolist()
            labels = model.labels_.tolist()

            # Group points by cluster label
            clusters: Dict[int, List[List[float]]] = {i: [] for i in range(n_clusters)}
            for pt, lbl in zip(coordinates, labels):
                clusters[lbl].append(pt)

            return {
                "success": True,
                "centroids": centroids,
                "labels": labels,
                "clusters": {str(k): v for k, v in clusters.items()}
            }
        except Exception as e:
            logger.error(f"K-Means clustering failed: {e}")
            return {"success": False, "error": str(e)}

    def classify_data(
        self, 
        train_features: List[List[float]], 
        train_labels: List[Any], 
        test_features: List[List[float]]
    ) -> Dict[str, Any]:
        """
        Train a Random Forest classifier on labeled training data,
        and predict labels for unlabeled test data.
        """
        try:
            if not train_features or not train_labels or not test_features:
                return {"success": False, "error": "Training features, training labels, and test features are required."}
            if len(train_features) != len(train_labels):
                return {"success": False, "error": "Number of training features must match the number of training labels."}

            X_train = np.array(train_features)
            y_train = np.array(train_labels)
            X_test = np.array(test_features)

            # Initialize and train classifier
            clf = RandomForestClassifier(n_estimators=10, random_state=42)
            clf.fit(X_train, y_train)

            predictions = clf.predict(X_test).tolist()
            # If classes exist, capture class names
            classes = clf.classes_.tolist()

            # Handle probabilities
            probs = clf.predict_proba(X_test).tolist()

            return {
                "success": True,
                "predictions": predictions,
                "probabilities": probs,
                "classes": classes
            }
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
ml_service = MLService()
