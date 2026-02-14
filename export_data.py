#!/usr/bin/env python
"""
Standalone data export script for OTree negotiation study
Exports to Parquet format compatible with original backend

Usage:
    python export_data.py
    python export_data.py --output data/exports
"""

import json
import sqlite3
import pandas as pd
import argparse
from datetime import datetime
from pathlib import Path


def get_db_connection(db_path='db.sqlite3'):
    """Connect to OTree database"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def export_negotiations(conn, output_dir):
    """Export round-level negotiation outcomes"""
    query = """
    SELECT
        s.code as session_id,
        p.code as participant_id,
        subs.round_number,
        n.block_number,
        n.round_in_block,
        n.reflection_on,
        n.initiator,
        pl.player_role,
        pl.final_price,
        pl.agreement_reached,
        CAST(COUNT(g.messages) AS INTEGER) as turns_count
    FROM otree_session s
    JOIN otree_subsession subs ON subs.session_id = s.id
    JOIN otree_group g ON g.subsession_id = subs.id
    JOIN otree_player pl ON pl.group_id = g.id
    JOIN otree_participant p ON p.id = pl.participant_id
    LEFT JOIN negotiation_subsession n ON n.id = subs.basesubsession_ptr_id
    GROUP BY s.id, p.id, subs.round_number
    """

    df = pd.read_sql_query(query, conn)

    # Parse message counts
    if len(df) > 0:
        df['turns_count'] = df['turns_count'].apply(lambda x: 0)  # Default to 0

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = Path(output_dir) / f'negotiations_{timestamp}.parquet'

    df.to_parquet(output_path, index=False)
    return output_path


def export_messages(conn, output_dir):
    """Export turn-by-turn conversation logs"""
    query = """
    SELECT
        s.code as session_id,
        p.code as participant_id,
        subs.round_number,
        pl.id as player_id
    FROM otree_session s
    JOIN otree_subsession subs ON subs.session_id = s.id
    JOIN otree_group g ON g.subsession_id = subs.id
    JOIN otree_player pl ON pl.group_id = g.id
    JOIN otree_participant p ON p.id = pl.participant_id
    """

    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()

    data = []

    for row in rows:
        # Get messages from this player/round
        msg_query = """
        SELECT messages FROM negotiation_group
        WHERE player_id = ? OR (
            SELECT group_id FROM negotiation_player WHERE id = ?
        )
        """
        cursor.execute("SELECT messages FROM negotiation_group WHERE id IN (SELECT group_id FROM negotiation_player WHERE id = ?)", (row['player_id'],))
        msg_row = cursor.fetchone()

        if msg_row and msg_row[0]:
            messages = json.loads(msg_row[0])
            for turn_number, msg in enumerate(messages, 1):
                msg_data = {
                    'session_id': row['session_id'],
                    'participant_id': row['participant_id'],
                    'round_number': row['round_number'],
                    'turn_number': turn_number,
                    'sender': msg.get('sender'),
                    'message_text': msg.get('text'),
                    'numeric_offer': msg.get('offer'),
                    'timestamp': msg.get('timestamp'),
                }
                data.append(msg_data)

    df = pd.DataFrame(data)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = Path(output_dir) / f'messages_{timestamp}.parquet'

    df.to_parquet(output_path, index=False)
    return output_path


def export_surveys(conn, output_dir):
    """Export survey responses"""
    query = """
    SELECT
        p.code as participant_id,
        pl.age,
        pl.gender,
        pl.negotiation_experience,
        pl.ai_familiarity,
        pl.ai_ability_rating,
        pl.behavior_patterns,
        pl.realism_rating,
        pl.additional_comments
    FROM otree_participant p
    JOIN otree_player pl ON pl.participant_id = p.id
    WHERE pl.round_number = 1
    """

    df = pd.read_sql_query(query, conn)

    # Remove duplicates (keep first occurrence)
    df = df.drop_duplicates(subset=['participant_id'], keep='first')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = Path(output_dir) / f'surveys_{timestamp}.csv'

    df.to_csv(output_path, index=False)
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Export OTree negotiation data')
    parser.add_argument('--output', default='data/exports', help='Output directory')
    parser.add_argument('--db', default='db.sqlite3', help='Database path')
    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Exporting data from {args.db} to {args.output}")

    try:
        conn = get_db_connection(args.db)

        print("\n📊 Exporting negotiation data...")
        neg_path = export_negotiations(conn, args.output)
        print(f"  ✓ {neg_path}")

        print("\n💬 Exporting message logs...")
        msg_path = export_messages(conn, args.output)
        print(f"  ✓ {msg_path}")

        print("\n📝 Exporting survey responses...")
        surv_path = export_surveys(conn, args.output)
        print(f"  ✓ {surv_path}")

        conn.close()

        print("\n" + "="*60)
        print("✓ Export complete!")
        print("="*60)

    except Exception as e:
        print(f"\n✗ Export failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
