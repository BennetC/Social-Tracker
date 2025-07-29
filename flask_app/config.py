import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Database credentials from environment variables
user = os.getenv('DB_USERNAME', 'postgres')
password = quote_plus(os.getenv('DB_PASSWORD', ''))
db_name = 'socialtracker'
host = 'localhost'
port = os.getenv('DB_PORT', 5432)

class Config:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = f'postgresql://{user}:{password}@{host}:{port}/{db_name}'

    SECRET_KEY = os.getenv('SECRET_KEY')

    # Defines the base score for each relationship priority level.
    PRIORITY_SCORES = {
        'Very High': 2.0,
        'High': 1.0,
        'Medium': 0.25,
        'Low': 0.05,
        'Very Low': 0.01
    }

    # The multiplier applied to the score for any primary item (platform, tag, etc.).
    PRIMARY_ITEM_MULTIPLIER = 1.5

    # Platform Input Rule Configuration
    PLATFORM_CONFIG = {
        'Twitter':   {'requires_handle': True,  'requires_link': False},
        'Instagram': {'requires_handle': True,  'requires_link': False},
        'LinkedIn':  {'requires_handle': False, 'requires_link': True},
        'GitHub':    {'requires_handle': True,  'requires_link': False},
        'Discord':   {'requires_handle': True,  'requires_link': False},
        'Telegram':  {'requires_handle': True,  'requires_link': False},
        'Email':     {'requires_handle': True,  'requires_link': False},
        'Website':   {'requires_handle': False, 'requires_link': True},
        'TikTok':    {'requires_handle': True,  'requires_link': False},
        'Reddit':   {'requires_handle': True,  'requires_link': False},
    }

    PLATFORM_BASE_URLS = {
        'Twitter': 'https://twitter.com/',
        'Instagram': 'https://instagram.com/',
        'GitHub': 'https://github.com/',
        'Telegram': 'https://t.me/',
        'TikTok': 'https://www.tiktok.com/@',
        'Email': 'mailto:',
        'Reddit': 'https://www.reddit.com/user/'
    }

    CONNECTION_TYPES = [
        'Peer', 'Mentor Potential', 'Target Follow-Up',
        'Client Potential', 'Industry Contact', 'Collaborator', 'Real Life'
    ]