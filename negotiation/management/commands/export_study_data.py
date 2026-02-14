"""
Django management command to export study data to Parquet/CSV
Usage: python manage.py export_study_data
"""

from django.core.management.base import BaseCommand
from otree.models import Session
import sys
import os

# Add services to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from services.export import NegotiationExporter


class Command(BaseCommand):
    help = 'Export negotiation study data to Parquet and CSV formats'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            type=str,
            default='data/exports',
            help='Output directory for export files'
        )

    def handle(self, *args, **options):
        output_dir = options['output_dir']

        # Get all completed sessions
        sessions = Session.objects.filter(app_sequence__app_name='negotiation')

        if not sessions.exists():
            self.stdout.write(self.style.WARNING('No negotiation sessions found'))
            return

        self.stdout.write(f'Found {sessions.count()} sessions')

        # Export data
        exporter = NegotiationExporter(output_dir=output_dir)

        try:
            results = exporter.export_all(sessions)
            self.stdout.write(self.style.SUCCESS('\n✓ Export successful!'))
            for key, path in results.items():
                self.stdout.write(f'  {key}: {path}')
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Export failed: {e}'))
