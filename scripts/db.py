import os
import psycopg
from sqlalchemy import create_engine

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_connection():
    return psycopg.connect(DATABASE_URL)

def get_engine():
    return create_engine(DATABASE_URL.replace('postgres://', 'postgresql+psycopg://'))

if __name__ == '__main__':
    with get_connection() as conn:
        print(conn.execute('SELECT current_database(), version()').fetchone())