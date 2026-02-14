#!/usr/bin/env python
"""
View saved session data from JSON files
Usage: python view_sessions.py [session_code]
"""

import json
import sys
from pathlib import Path
from services.session_logger import SessionLogger


def list_sessions():
    """List all available sessions"""
    sessions = SessionLogger.list_sessions()
    if not sessions:
        print("No sessions found in data directory")
        return

    print("Available sessions:")
    for session in sorted(sessions):
        print(f"  - {session}")


def view_session(session_code):
    """View a specific session"""
    logger = SessionLogger(session_code)
    data = logger.get_session_data()

    print(f"\n{'='*60}")
    print(f"Session: {session_code}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2))
    print(f"{'='*60}\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python view_sessions.py [session_code]")
        print("       python view_sessions.py --list\n")
        list_sessions()
    else:
        session_code = sys.argv[1]
        if session_code == "--list":
            list_sessions()
        else:
            view_session(session_code)


if __name__ == "__main__":
    main()
