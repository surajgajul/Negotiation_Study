"""
Data export service for OTree negotiation study
Exports to Parquet format compatible with original backend
"""

import json
import pandas as pd
from datetime import datetime
from pathlib import Path


class NegotiationExporter:
    """Export negotiation data to Parquet format"""

    def __init__(self, output_dir='data/exports'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_negotiations(self, sessions):
        """
        Export round-level negotiation outcomes to Parquet

        Args:
            sessions: List of OTree Session objects

        Returns:
            Path to exported parquet file
        """
        data = []

        for session in sessions:
            for subsession in session.subsession_set.all():
                for player in subsession.player_set.all():
                    round_data = {
                        'session_id': session.code,
                        'participant_id': player.participant.code,
                        'round_number': subsession.round_number,
                        'block_number': subsession.block_number,
                        'round_in_block': subsession.round_in_block,
                        'reflection_on': subsession.reflection_on,
                        'initiator': subsession.initiator,
                        'player_role': player.player_role,
                        'final_price': player.final_price,
                        'agreement_reached': player.agreement_reached,
                        'turns_count': len(json.loads(player.group.messages)),
                    }

                    data.append(round_data)

        df = pd.DataFrame(data)

        # Export to Parquet
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = self.output_dir / f'negotiations_{timestamp}.parquet'
        df.to_parquet(output_path, index=False)

        return output_path

    def export_messages(self, sessions):
        """
        Export turn-by-turn conversation logs to Parquet

        Args:
            sessions: List of OTree Session objects

        Returns:
            Path to exported parquet file
        """
        data = []

        for session in sessions:
            for subsession in session.subsession_set.all():
                for player in subsession.player_set.all():
                    messages = json.loads(player.group.messages)

                    for turn_number, msg in enumerate(messages, 1):
                        msg_data = {
                            'session_id': session.code,
                            'participant_id': player.participant.code,
                            'round_number': subsession.round_number,
                            'turn_number': turn_number,
                            'sender': msg['sender'],
                            'message_text': msg['text'],
                            'numeric_offer': msg.get('offer'),
                            'timestamp': msg.get('timestamp'),
                        }

                        data.append(msg_data)

        df = pd.DataFrame(data)

        # Export to Parquet
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = self.output_dir / f'messages_{timestamp}.parquet'
        df.to_parquet(output_path, index=False)

        return output_path

    def export_surveys(self, sessions):
        """
        Export survey responses to CSV

        Args:
            sessions: List of OTree Session objects

        Returns:
            Path to exported CSV file
        """
        data = []

        for session in sessions:
            for subsession in session.subsession_set.all():
                for player in subsession.player_set.all():
                    # Only export once per participant (data is duplicated across rounds)
                    if subsession.round_number == 1:
                        survey_data = {
                            'participant_id': player.participant.code,
                            'age': player.age,
                            'gender': player.gender,
                            'negotiation_experience': player.negotiation_experience,
                            'ai_familiarity': player.ai_familiarity,
                        }
                        data.append(survey_data)

            # Also export post-survey for last round
            last_subsession = session.subsession_set.all().last()
            if last_subsession:
                for player in last_subsession.player_set.all():
                    # Find the survey entry and update it
                    matching = [d for d in data if d['participant_id'] == player.participant.code]
                    if matching:
                        matching[0].update({
                            'ai_ability_rating': player.ai_ability_rating,
                            'behavior_patterns': player.behavior_patterns,
                            'realism_rating': player.realism_rating,
                            'additional_comments': player.additional_comments,
                        })

        df = pd.DataFrame(data)

        # Export to CSV
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_path = self.output_dir / f'surveys_{timestamp}.csv'
        df.to_csv(output_path, index=False)

        return output_path

    def export_all(self, sessions):
        """Export all data types"""
        results = {
            'negotiations': self.export_negotiations(sessions),
            'messages': self.export_messages(sessions),
            'surveys': self.export_surveys(sessions),
        }

        print("\n✓ Data export complete!")
        for key, path in results.items():
            print(f"  {key}: {path}")

        return results
