"""
AERIS AI OS - Data Analytics Service
Provides data analytics tools using pandas and numpy: dataset descriptive
summaries, missing value metrics, and correlation matrix calculations.
"""
import os
import logging
from typing import Dict, Any, List

import pandas as pd
import numpy as np

logger = logging.getLogger("aeris.services.analytics")


class AnalyticsService:
    """Service wrapping Pandas and NumPy for tabular data analytics."""

    def __init__(self):
        pass

    def summarize_csv(self, csv_path: str) -> Dict[str, Any]:
        """
        Ingest a CSV file and return a comprehensive summary of its data:
        statistics, columns, missing values, shape, and head preview.
        """
        try:
            if not os.path.exists(csv_path):
                return {"success": False, "error": f"CSV file not found at path: {csv_path}"}

            df = pd.read_csv(csv_path)

            # Metadata
            rows, cols = df.shape
            column_names = df.columns.tolist()
            data_types = {col: str(dtype) for col, dtype in df.dtypes.items()}
            
            # Missing values count
            missing_values = df.isnull().sum().to_dict()
            total_missing = int(df.isnull().sum().sum())

            # Descriptive statistics for numeric columns
            numeric_desc = {}
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if numeric_cols:
                desc_df = df[numeric_cols].describe()
                for col in numeric_cols:
                    numeric_desc[col] = {
                        "count": float(desc_df.loc["count", col]),
                        "mean": float(desc_df.loc["mean", col]) if not np.isnan(desc_df.loc["mean", col]) else None,
                        "std": float(desc_df.loc["std", col]) if not np.isnan(desc_df.loc["std", col]) else None,
                        "min": float(desc_df.loc["min", col]),
                        "25%": float(desc_df.loc["25%", col]),
                        "50%": float(desc_df.loc["50%", col]),
                        "75%": float(desc_df.loc["75%", col]),
                        "max": float(desc_df.loc["max", col])
                    }

            # Preview first 5 rows (as list of dictionaries)
            preview = df.head(5).replace({np.nan: None}).to_dict(orient="records")

            return {
                "success": True,
                "shape": {"rows": rows, "columns": cols},
                "columns": column_names,
                "data_types": data_types,
                "missing_values": missing_values,
                "total_missing": total_missing,
                "numeric_statistics": numeric_desc,
                "preview": preview
            }
        except Exception as e:
            logger.error(f"Failed to summarize CSV: {e}")
            return {"success": False, "error": str(e)}

    def calculate_correlation(self, csv_path: str) -> Dict[str, Any]:
        """
        Read a CSV file, isolate numerical columns, and calculate the
        Pearson correlation matrix between them.
        """
        try:
            if not os.path.exists(csv_path):
                return {"success": False, "error": f"CSV file not found at path: {csv_path}"}

            df = pd.read_csv(csv_path)
            
            # Filter numerical columns
            numeric_df = df.select_dtypes(include=[np.number])
            if numeric_df.empty or numeric_df.shape[1] < 2:
                return {
                    "success": False, 
                    "error": "The dataset must contain at least 2 numeric columns to compute correlations."
                }

            # Calculate Pearson correlation matrix
            corr_matrix = numeric_df.corr().replace({np.nan: None}).to_dict()

            return {
                "success": True,
                "columns": numeric_df.columns.tolist(),
                "correlation_matrix": corr_matrix
            }
        except Exception as e:
            logger.error(f"Failed to calculate correlation matrix: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
analytics_service = AnalyticsService()
