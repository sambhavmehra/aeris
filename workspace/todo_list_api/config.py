import os
from pathlib import Path
from typing import Dict

class Config:
    """
    Configuration class for the application.
    """
    def __init__(self):
        self.DATABASE_URL = os.environ.get('DATABASE_URL')
        self.DEBUG = os.environ.get('DEBUG', 'False') == 'True'
        self.SECRET_KEY = os.environ.get('SECRET_KEY')
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.SQLALCHEMY_ECHO = self.DEBUG

    def to_dict(self) -> Dict:
        return {
            'DATABASE_URL': self.DATABASE_URL,
            'DEBUG': self.DEBUG,
            'SECRET_KEY': self.SECRET_KEY,
            'SQLALCHEMY_TRACK_MODIFICATIONS': self.SQLALCHEMY_TRACK_MODIFICATIONS,
            'SQLALCHEMY_ECHO': self.SQLALCHEMY_ECHO
        }
