from contextlib import contextmanager

import psycopg

from .config import settings


@contextmanager
def get_connection():
    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        yield conn
