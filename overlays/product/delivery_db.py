import os
from sqlalchemy import URL, create_engine


def database_url():
    # Credentials are environment-only and not generated source content.
    return URL.create('postgresql+psycopg', username=os.environ.get('DATABASE_USER', 'product'),
                      password=os.environ['DATABASE_PASSWORD'], host=os.environ.get('DATABASE_HOST', 'localhost'),
                      port=int(os.environ.get('DATABASE_PORT', '5432')),
                      database=os.environ.get('DATABASE_NAME', 'product'))


def make_engine():
    return create_engine(database_url(), pool_pre_ping=True)
