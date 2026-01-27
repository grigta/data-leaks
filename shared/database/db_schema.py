import sqlite3
import logging
from pathlib import Path

# Constants
DEFAULT_DB_PATH = '/root/soft/data/ssn_database.db'

# Get logger without global configuration
logger = logging.getLogger(__name__)


def validate_table_name(table_name):
    """
    Validate that the table name is one of the allowed table names.

    Args:
        table_name: Name of the table to validate

    Raises:
        ValueError: If table name is not in the allowed set
    """
    allowed_tables = {'ssn_1', 'ssn_2', 'ssn_3'}
    if table_name not in allowed_tables:
        raise ValueError(f"Invalid table name '{table_name}'. Must be one of {allowed_tables}")


def create_table(cursor, table_name):
    """
    Create a table with the specified name and schema for SSN data.

    Args:
        cursor: SQLite cursor object
        table_name: Name of the table to create
    """
    validate_table_name(table_name)
    table_sql = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        id INTEGER PRIMARY KEY,
        firstname TEXT,
        lastname TEXT,
        middlename TEXT,
        address TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        phone TEXT,
        ssn TEXT UNIQUE NOT NULL,
        dob TEXT,
        email TEXT
    )
    """
    cursor.execute(table_sql)
    logger.info(f"Table '{table_name}' created successfully")


def create_indexes(cursor, table_name):
    """
    Create optimized indexes for fast lookups on the specified table.

    Args:
        cursor: SQLite cursor object
        table_name: Name of the table to create indexes for
    """
    validate_table_name(table_name)

    # Composite index for name + address lookups (case-insensitive)
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_name_address
        ON {table_name}(firstname COLLATE NOCASE, lastname COLLATE NOCASE, address COLLATE NOCASE)
    """)
    logger.info(f"Index 'idx_{table_name}_name_address' created successfully")

    # Composite index for name + ZIP lookups (case-insensitive)
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_name_zip
        ON {table_name}(firstname COLLATE NOCASE, lastname COLLATE NOCASE, zip)
    """)
    logger.info(f"Index 'idx_{table_name}_name_zip' created successfully")

    # Index for SSN lookups
    cursor.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_{table_name}_ssn
        ON {table_name}(ssn)
    """)
    logger.info(f"Index 'idx_{table_name}_ssn' created successfully")


def initialize_database(db_path=None):
    """
    Initialize the SQLite database with tables and indexes.

    Args:
        db_path: Optional path to the database file. Defaults to DEFAULT_DB_PATH.

    Returns:
        sqlite3.Connection: Database connection object

    Raises:
        sqlite3.Error: If database initialization fails
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    try:
        # Create directory if it doesn't exist
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        # Enable foreign keys and optimize performance
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")

        logger.info(f"Connected to database at {db_path}")

        # Create tables
        create_table(cursor, 'ssn_1')
        create_table(cursor, 'ssn_2')
        create_table(cursor, 'ssn_3')

        # Create indexes
        create_indexes(cursor, 'ssn_1')
        create_indexes(cursor, 'ssn_2')
        create_indexes(cursor, 'ssn_3')

        # Commit changes
        connection.commit()
        logger.info("Database initialization completed successfully")

        return connection

    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise


def get_connection(db_path=None):
    """
    Get a connection to the existing database.

    Args:
        db_path: Optional path to the database file. Defaults to DEFAULT_DB_PATH.

    Returns:
        sqlite3.Connection: Database connection object with Row factory enabled

    Raises:
        FileNotFoundError: If database file doesn't exist
        sqlite3.Error: If connection fails
    """
    if db_path is None:
        db_path = DEFAULT_DB_PATH

    try:
        db_file = Path(db_path)
        if not db_file.exists():
            raise FileNotFoundError(f"Database file not found at {db_path}")

        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        logger.info(f"Connected to database at {db_path}")

        return connection

    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise


def close_connection(connection):
    """
    Safely close the database connection.

    Args:
        connection: SQLite connection object to close
    """
    if connection:
        connection.close()
        logger.info("Database connection closed")


if __name__ == '__main__':
    # Configure logging for direct script execution
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Initialize database
    conn = initialize_database()

    if conn:
        print("\n" + "="*50)
        print("Database initialized successfully!")
        print(f"Database path: {DEFAULT_DB_PATH}")
        print("="*50)

        # Close connection
        close_connection(conn)
