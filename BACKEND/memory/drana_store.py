"""
Drana Memory Store — Dedicated persistent JSON storage for DranaAgent.
Saves to BACKEND/data/drana_memory.json
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from config import settings

logger = logging.getLogger("aeris.drana_memory")

class DranaStore:
    def __init__(self):
        self.recon_data = {}
        self.xss_payloads = []
        self.traffic_analysis = []
        self._file_path = settings.DATA_DIR / "drana_memory.json"
        self.load()

    def add_recon(self, data: dict) -> str:
        scan_id = str(uuid.uuid4())[:8]
        self.recon_data[scan_id] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        self.save()
        return scan_id

    def add_xss_payload(self, message: str, response: str):
        self.xss_payloads.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
            "response": response
        })
        # keep last 20
        self.xss_payloads = self.xss_payloads[-20:]
        self.save()

    def add_traffic_analysis(self, request: str, response_text: str, report: str):
        self.traffic_analysis.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request": request,
            "response": response_text,
            "report": report
        })
        self.traffic_analysis = self.traffic_analysis[-20:]
        self.save()

    def get_context_string(self) -> str:
        parts = []
        if self.recon_data:
            latest_id = list(self.recon_data.keys())[-1]
            parts.append(f"Latest JS Recon ({latest_id}):\n{json.dumps(self.recon_data[latest_id]['data'], indent=2)}")
        if self.xss_payloads:
            latest = self.xss_payloads[-1]
            parts.append(f"Latest XSS Payload Gen:\nMsg: {latest['message']}\nResp: {latest['response']}")
        if self.traffic_analysis:
            latest = self.traffic_analysis[-1]
            parts.append(f"Latest Traffic Analysis:\nReq: {latest['request']}\nReport: {latest['report']}")
        
        return "\n\n".join(parts) if parts else "No Drana context available yet."

    def save(self) -> None:
        try:
            data = {
                "recon_data": self.recon_data,
                "xss_payloads": self.xss_payloads,
                "traffic_analysis": self.traffic_analysis,
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save drana memory: {e}")

    def load(self) -> None:
        try:
            if self._file_path.exists():
                data = json.loads(self._file_path.read_text(encoding="utf-8"))
                self.recon_data = data.get("recon_data", {})
                self.xss_payloads = data.get("xss_payloads", [])
                self.traffic_analysis = data.get("traffic_analysis", [])
        except Exception as e:
            logger.error(f"Failed to load drana memory: {e}")
            self.recon_data = {}
            self.xss_payloads = []
            self.traffic_analysis = []

drana_store = DranaStore()
