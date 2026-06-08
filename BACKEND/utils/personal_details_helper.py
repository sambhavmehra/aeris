"""
AERIS Personal Details Storage Helper
Manages reading and writing sensitive profile details (Name, Email, Phone, Age, Role)
to data/personal_details.json.
"""
import os
import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("aeris.utils.personal_details")


def get_details_file_path() -> Path:
    """Resolve Path to data/personal_details.json."""
    from config import settings
    # Use DATA_DIR from settings
    path = Path(settings.DATA_DIR) / "personal_details.json"
    return path


def load_personal_details() -> Dict[str, Any]:
    """Load personal details from local storage."""
    path = get_details_file_path()
    if path.exists() and path.stat().st_size > 0:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read personal_details.json: {e}")
    return {
        "Name": "",
        "Email": "",
        "Phone": "",
        "Age": "",
        "Role": "",
        "Details": {}
    }


def save_personal_details(new_details: Dict[str, Any]) -> Dict[str, Any]:
    """Merge and save new details to personal_details.json."""
    path = get_details_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    
    current = load_personal_details()
    
    # Merge fields
    for k, v in new_details.items():
        if not v:
            continue
        if k in ("Name", "Email", "Phone", "Age", "Role"):
            current[k] = str(v).strip()
        else:
            current.setdefault("Details", {})[k] = v
            
    try:
        path.write_text(json.dumps(current, indent=2, default=str), encoding="utf-8")
        logger.info(f"Successfully saved personal details to {path}")
    except Exception as e:
        logger.error(f"Failed to save personal details: {e}")
        
    return current
