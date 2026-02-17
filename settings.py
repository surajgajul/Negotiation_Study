from os import environ
import yaml
import os

# Load study configuration
config_path = os.path.join(os.path.dirname(__file__), 'settings_study.yaml')
with open(config_path, 'r') as f:
    study_config = yaml.safe_load(f)

SESSION_CONFIGS = [
    dict(
        name='ai_negotiation_study',
        app_sequence=['negotiation'],
        num_demo_participants=1,
        doc='Human-AI negotiation experiment',
        # Study parameters
        buyer_range=study_config['study']['buyer_range'],
        supplier_range=study_config['study']['supplier_range'],
        max_turns_per_side=study_config['study']['max_turns_per_side'],
        max_time_per_side_sec=study_config['study']['max_time_per_side_sec'],
        reflection_tokens=study_config['study']['reflection_tokens'],
        temperature=study_config['study']['temperature'],
        model_provider=study_config['study']['model_provider'],
        model_name=study_config['study']['model_name'],
    ),
]

# if you set a property in SESSION_CONFIG_DEFAULTS, it will be inherited by all configs
# in SESSION_CONFIGS, except those that explicitly override it.
# the session config can be accessed from methods in your apps as self.session.config,
# e.g. self.session.config['participation_fee']

SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=1.00, participation_fee=0.00, doc=""
)

PARTICIPANT_FIELDS = []
SESSION_FIELDS = []

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'

# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """ """

SECRET_KEY = '9728728816603'

DEBUG = False
