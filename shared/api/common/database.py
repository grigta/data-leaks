"""
Database connection management for PostgreSQL and SQLite.
"""
import os
from typing import AsyncGenerator
from contextlib import contextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.db_schema import get_connection, close_connection, DEFAULT_DB_PATH

# PostgreSQL configuration
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+asyncpg://ssn_user:password@localhost:5432/ssn_users')

# SQLite configuration
SQLITE_PATH = os.getenv('SQLITE_PATH', DEFAULT_DB_PATH)

# Helper function to parse boolean environment variables
def parse_bool_env(value: str) -> bool:
    """
    Parse boolean environment variable with flexible input.

    Args:
        value: String value from environment variable

    Returns:
        True for: 'true', '1', 'yes', 'on' (case-insensitive)
        False for: 'false', '0', 'no', 'off' (case-insensitive)
    """
    if isinstance(value, bool):
        return value
    return value.lower().strip() in ('true', '1', 'yes', 'on')


# Database pool configuration from environment variables
DB_POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '30'))
DB_MAX_OVERFLOW = int(os.getenv('DB_MAX_OVERFLOW', '20'))
DB_POOL_TIMEOUT = int(os.getenv('DB_POOL_TIMEOUT', '30'))
DB_POOL_RECYCLE = int(os.getenv('DB_POOL_RECYCLE', '1800'))
DB_POOL_PRE_PING = parse_bool_env(os.getenv('DB_POOL_PRE_PING', 'true'))

# Create PostgreSQL async engine
async_engine = create_async_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    pool_pre_ping=DB_POOL_PRE_PING,
    echo=False
)

# Create async session maker
async_session_maker = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for PostgreSQL async session.
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


@contextmanager
def get_sqlite_connection(read_only: bool = False):
    """
    FastAPI dependency for SQLite connection.

    Args:
        read_only: If True, opens database in read-only mode
    """
    if read_only:
        # Open SQLite in read-only mode using URI
        import sqlite3
        db_uri = f"file:{SQLITE_PATH}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row
    else:
        # Open SQLite in read-write mode
        conn = get_connection(SQLITE_PATH)

    try:
        yield conn
    finally:
        close_connection(conn)


def get_sqlite_connection_public():
    """
    FastAPI dependency for Public API (read-only SQLite).
    """
    return get_sqlite_connection(read_only=True)


def get_sqlite_connection_enrichment():
    """
    FastAPI dependency for Enrichment API (read-write SQLite).
    """
    return get_sqlite_connection(read_only=False)


async def dispose_engine():
    """
    Gracefully close all database connections in the engine pool.
    Should be called on application shutdown.
    """
    try:
        await async_engine.dispose()
    except Exception as e:
        # Log the error but don't raise - shutdown should continue
        import logging
        logging.error(f"Error disposing database engine: {e}")
