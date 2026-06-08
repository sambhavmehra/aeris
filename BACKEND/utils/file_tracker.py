"""
AERIS File Tracker
Tracks and remembers all files created, exported, or written by tools and agents.
Saves records to data/created_files.json.
"""
import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import threading

logger = logging.getLogger("aeris.utils.file_tracker")
_tracker_lock = threading.Lock()


def get_tracker_file_path() -> Path:
    from config import settings
    path = Path(settings.DATA_DIR) / "created_files.json"
    return path


def record_file_creation(filepath: str, purpose: str = "General Creation") -> None:
    """Record a file creation event in data/created_files.json."""
    try:
        path = get_tracker_file_path()
        with _tracker_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Resolve path to clean absolute path
            abs_path = str(Path(filepath).resolve())
            
            # Load existing records
            records = []
            if path.exists() and path.stat().st_size > 0:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    records = data.get("created_files", [])
                except Exception as e:
                    logger.warning(f"Failed to read created_files.json: {e}")
            
            # Create new record entry
            new_record = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "file_path": abs_path,
                "filename": os.path.basename(abs_path),
                "purpose": purpose
            }
            
            # Avoid duplicate consecutive identical paths within 2 seconds
            if records:
                last_rec = records[-1]
                if last_rec.get("file_path") == abs_path:
                    # Parse timestamps
                    try:
                        t1 = datetime.fromisoformat(last_rec["timestamp"].replace("Z", ""))
                        t2 = datetime.fromisoformat(new_record["timestamp"].replace("Z", ""))
                        if (t2 - t1).total_seconds() < 2.0:
                            # Update purpose/timestamp instead of appending duplicate
                            last_rec["timestamp"] = new_record["timestamp"]
                            last_rec["purpose"] = purpose
                            path.write_text(json.dumps({"created_files": records}, indent=2, default=str), encoding="utf-8")
                            return
                    except Exception:
                        pass
            
            records.append(new_record)
            
            # Limit history to last 100 entries
            records = records[-100:]
            
            path.write_text(json.dumps({"created_files": records}, indent=2, default=str), encoding="utf-8")
            logger.info(f"Recorded file creation in tracker: {abs_path}")
    except Exception as e:
        logger.error(f"Failed to record file creation: {e}")


def get_created_files() -> List[Dict[str, Any]]:
    """Retrieve all recorded file creation events."""
    try:
        path = get_tracker_file_path()
        with _tracker_lock:
            if path.exists() and path.stat().st_size > 0:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("created_files", [])
    except Exception as e:
        logger.error(f"Failed to load created files records: {e}")
    return []


def resolve_tracked_file(query: str) -> Optional[str]:
    """Resolves a file query/pronoun to a tracked file's absolute path."""
    from typing import Optional
    try:
        records = get_created_files()
        if not records:
            return None
            
        # Lowercase and split into words
        words = query.lower().strip().split()
        
        # Remove common Hinglish/English fillers as full words
        fillers = {"wali", "wala", "file", "sheet", "excel", "document", "ko", "open", "kr", "kar", "show"}
        clean_words = [w for w in words if w not in fillers]
        clean_query = " ".join(clean_words).strip(" ._*?!")
        
        # If it's a general pronoun or empty, return the most recently created file
        pronouns = {"usko", "it", "that", "this", "file", "sheet", "excel", "document", ""}
        if clean_query in pronouns:
            return records[-1].get("file_path")
            
        # Search backward (newest first) for filename or purpose keyword match
        for r in reversed(records):
            filename = r.get("filename", "").lower()
            purpose = r.get("purpose", "").lower()
            file_path = r.get("file_path", "")
            
            if clean_query in filename or clean_query in purpose:
                return file_path
                
        # Shorthand word match
        for r in reversed(records):
            filename = r.get("filename", "").lower()
            if any(w in filename for w in clean_words if len(w) > 1):
                return r.get("file_path")
                
    except Exception as e:
        logger.warning(f"Failed to resolve tracked file for query '{query}': {e}")
    return None
