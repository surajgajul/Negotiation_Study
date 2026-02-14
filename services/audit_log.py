"""
Append-only JSONL audit logger for the negotiation study.
Each line in data/audit.jsonl is one JSON object with a timestamp,
session_code, round_number, event_type, and event-specific payload.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class AuditLogger:
    """Append-only JSONL audit logger -- one file for all sessions."""

    _LOG_PATH = Path(__file__).parent.parent / "data" / "audit.jsonl"

    @classmethod
    def log(
        cls,
        *,
        event_type: str,
        session_code: str = "",
        round_number: int = 0,
        participant_code: str = "",
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        cls._LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_code": session_code,
            "participant_code": participant_code,
            "round_number": round_number,
            "event_type": event_type,
            "payload": payload or {},
        }

        try:
            with open(cls._LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            print(f"[AuditLogger] FAILED to write: {record}", file=sys.stderr)
