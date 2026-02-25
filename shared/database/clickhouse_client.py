"""
ClickHouse Client Module for SSN Data Operations

This module provides connection pooling and query execution for ClickHouse database.
It's designed to replace SQLite for analytical SSN searches with better performance
on large datasets.

Main Features:
- Connection pooling with configurable pool size
- Parameterized query execution (SQL injection prevention)
- Batch insert operations for bulk data loading
- Automatic retry with exponential backoff
- Health check and automatic reconnection

Environment Variables:
- CLICKHOUSE_HOST: ClickHouse server hostname (default: clickhouse)
- CLICKHOUSE_PORT: Native protocol port (default: 9000)
- CLICKHOUSE_HTTP_PORT: HTTP interface port (default: 8123)
- CLICKHOUSE_DB: Database name (default: ssn_database)
- CLICKHOUSE_USER: Username (default: ssn_user)
- CLICKHOUSE_PASSWORD: Password
- CLICKHOUSE_MAX_CONNECTIONS: Max pool size (default: 10)
"""

import os
import time
import logging
from typing import Any, Dict, List, Optional, Tuple
from contextlib import contextmanager
from threading import Lock

try:
    import clickhouse_connect
    from clickhouse_connect.driver.client import Client
    CLICKHOUSE_AVAILABLE = True
except ImportError:
    CLICKHOUSE_AVAILABLE = False
    Client = None

# Module logger
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_HOST = 'clickhouse'
DEFAULT_PORT = 9000
DEFAULT_HTTP_PORT = 8123
DEFAULT_DATABASE = 'ssn_database'
DEFAULT_USER = 'ssn_user'
DEFAULT_PASSWORD = ''
DEFAULT_MAX_CONNECTIONS = 10
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_SEND_RECEIVE_TIMEOUT = 300

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 0.5  # seconds
MAX_BACKOFF = 30  # seconds


class ClickHouseConfig:
    """Configuration for ClickHouse connection."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        http_port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        max_connections: Optional[int] = None,
        connect_timeout: Optional[int] = None,
        send_receive_timeout: Optional[int] = None,
    ):
        """
        Initialize ClickHouse configuration from parameters or environment.

        Args:
            host: ClickHouse server hostname
            port: Native protocol port
            http_port: HTTP interface port
            database: Database name
            user: Username
            password: Password
            max_connections: Maximum connections in pool
            connect_timeout: Connection timeout in seconds
            send_receive_timeout: Query timeout in seconds
        """
        self.host = host or os.getenv('CLICKHOUSE_HOST', DEFAULT_HOST)
        self.port = port or int(os.getenv('CLICKHOUSE_PORT', DEFAULT_PORT))
        self.http_port = http_port or int(os.getenv('CLICKHOUSE_HTTP_PORT', DEFAULT_HTTP_PORT))
        self.database = database or os.getenv('CLICKHOUSE_DB', DEFAULT_DATABASE)
        self.user = user or os.getenv('CLICKHOUSE_USER', DEFAULT_USER)
        self.password = password or os.getenv('CLICKHOUSE_PASSWORD', DEFAULT_PASSWORD)
        self.max_connections = max_connections or int(
            os.getenv('CLICKHOUSE_MAX_CONNECTIONS', DEFAULT_MAX_CONNECTIONS)
        )
        self.connect_timeout = connect_timeout or DEFAULT_CONNECT_TIMEOUT
        self.send_receive_timeout = send_receive_timeout or DEFAULT_SEND_RECEIVE_TIMEOUT

    def __repr__(self) -> str:
        return (
            f"ClickHouseConfig(host={self.host}, port={self.port}, "
            f"database={self.database}, user={self.user})"
        )


class ClickHouseConnectionPool:
    """
    Connection pool for ClickHouse clients.

    Manages a pool of reusable connections to minimize connection overhead.
    Thread-safe with locking for connection acquisition and release.
    """

    def __init__(self, config: Optional[ClickHouseConfig] = None):
        """
        Initialize connection pool.

        Args:
            config: ClickHouseConfig instance or None to use defaults/environment
        """
        if not CLICKHOUSE_AVAILABLE:
            raise ImportError(
                "clickhouse-connect is not installed. "
                "Install with: pip install clickhouse-connect"
            )

        self.config = config or ClickHouseConfig()
        self._pool: List[Client] = []
        self._lock = Lock()
        self._created_count = 0
        logger.info(f"ClickHouse connection pool initialized: {self.config}")

    def _create_client(self) -> Client:
        """
        Create a new ClickHouse client.

        Returns:
            Client: New ClickHouse client instance

        Raises:
            Exception: If connection fails
        """
        client = clickhouse_connect.get_client(
            host=self.config.host,
            port=self.config.http_port,  # clickhouse-connect uses HTTP port
            database=self.config.database,
            username=self.config.user,
            password=self.config.password,
            connect_timeout=self.config.connect_timeout,
            send_receive_timeout=self.config.send_receive_timeout,
        )
        self._created_count += 1
        logger.debug(f"Created new ClickHouse client (total: {self._created_count})")
        return client

    def get_client(self) -> Client:
        """
        Get a client from the pool or create a new one.

        Returns:
            Client: ClickHouse client instance

        Raises:
            Exception: If unable to create connection
        """
        with self._lock:
            if self._pool:
                client = self._pool.pop()
                logger.debug(f"Reusing client from pool (remaining: {len(self._pool)})")
                return client

        # Create new client outside lock to avoid blocking
        return self._create_client()

    def release_client(self, client: Client) -> None:
        """
        Return a client to the pool for reuse.

        Args:
            client: ClickHouse client to return
        """
        with self._lock:
            if len(self._pool) < self.config.max_connections:
                self._pool.append(client)
                logger.debug(f"Client returned to pool (size: {len(self._pool)})")
            else:
                # Pool is full, close the client
                try:
                    client.close()
                    logger.debug("Client closed (pool full)")
                except Exception as e:
                    logger.warning(f"Error closing client: {e}")

    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for client in self._pool:
                try:
                    client.close()
                except Exception as e:
                    logger.warning(f"Error closing client: {e}")
            self._pool.clear()
            logger.info("All pool connections closed")

    @contextmanager
    def connection(self):
        """
        Context manager for getting and releasing connections.

        Yields:
            Client: ClickHouse client

        Example:
            with pool.connection() as client:
                result = client.query("SELECT 1")
        """
        client = self.get_client()
        try:
            yield client
        finally:
            self.release_client(client)


# Global pool instance (lazy initialization)
_pool: Optional[ClickHouseConnectionPool] = None
_pool_lock = Lock()


def get_pool(config: Optional[ClickHouseConfig] = None) -> ClickHouseConnectionPool:
    """
    Get the global connection pool, creating it if necessary.

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        ClickHouseConnectionPool: Global pool instance
    """
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ClickHouseConnectionPool(config)
    return _pool


def get_client() -> Client:
    """
    Get a ClickHouse client from the global pool.

    Returns:
        Client: ClickHouse client instance
    """
    return get_pool().get_client()


def release_client(client: Client) -> None:
    """
    Release a client back to the global pool.

    Args:
        client: Client to release
    """
    get_pool().release_client(client)


@contextmanager
def get_connection():
    """
    Context manager for ClickHouse connections.

    Yields:
        Client: ClickHouse client

    Example:
        with get_connection() as client:
            result = execute_query(client, "SELECT * FROM ssn_data LIMIT 10")
    """
    with get_pool().connection() as client:
        yield client


def execute_query(
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    client: Optional[Client] = None,
    retries: int = MAX_RETRIES,
) -> List[Dict[str, Any]]:
    """
    Execute a SELECT query and return results as list of dictionaries.

    Security:
        - Uses parameterized queries to prevent SQL injection
        - Parameters are safely escaped by clickhouse-connect

    Args:
        query: SQL query with named parameters (e.g., {ssn:String})
        parameters: Dictionary of parameter values
        client: Optional existing client (uses pool if not provided)
        retries: Number of retry attempts on failure

    Returns:
        List of dictionaries with query results

    Raises:
        Exception: If query fails after all retries

    Example:
        results = execute_query(
            "SELECT * FROM ssn_data WHERE ssn = {ssn:String}",
            {"ssn": "123-45-6789"}
        )
    """
    should_release = client is None
    last_error = None
    backoff = INITIAL_BACKOFF

    for attempt in range(retries + 1):
        try:
            if client is None:
                client = get_client()

            # Execute query
            result = client.query(query, parameters=parameters or {})

            # Convert to list of dicts
            columns = result.column_names
            rows = []
            for row in result.result_rows:
                rows.append(dict(zip(columns, row)))

            logger.debug(f"Query returned {len(rows)} rows")
            return rows

        except Exception as e:
            last_error = e
            logger.warning(f"Query attempt {attempt + 1}/{retries + 1} failed: {e}")

            if attempt < retries:
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF)

                # Get fresh client for retry
                if should_release and client:
                    try:
                        client.close()
                    except Exception:
                        pass
                client = None

        finally:
            if should_release and client:
                release_client(client)
                client = None

    raise last_error


def execute_command(
    query: str,
    parameters: Optional[Dict[str, Any]] = None,
    client: Optional[Client] = None,
) -> None:
    """
    Execute a command (INSERT, CREATE, ALTER, etc.) without returning results.

    Args:
        query: SQL command
        parameters: Optional parameters
        client: Optional existing client

    Raises:
        Exception: If command fails
    """
    should_release = client is None
    try:
        if client is None:
            client = get_client()

        client.command(query, parameters=parameters or {})
        logger.debug("Command executed successfully")

    finally:
        if should_release and client:
            release_client(client)


def execute_batch(
    table: str,
    data: List[Dict[str, Any]],
    column_names: Optional[List[str]] = None,
    client: Optional[Client] = None,
    batch_size: int = 10000,
) -> int:
    """
    Insert multiple rows in batches for optimal performance.

    Args:
        table: Table name to insert into
        data: List of dictionaries with row data
        column_names: Optional list of column names (inferred from first row if not provided)
        client: Optional existing client
        batch_size: Number of rows per batch (default: 10000)

    Returns:
        int: Total number of rows inserted

    Raises:
        ValueError: If data is empty
        Exception: If insert fails

    Example:
        rows = [
            {"ssn": "123-45-6789", "firstname": "John", "lastname": "Doe"},
            {"ssn": "987-65-4321", "firstname": "Jane", "lastname": "Smith"},
        ]
        count = execute_batch("ssn_data", rows)
    """
    if not data:
        raise ValueError("Data cannot be empty")

    should_release = client is None
    total_inserted = 0

    try:
        if client is None:
            client = get_client()

        # Infer column names from first row
        if column_names is None:
            column_names = list(data[0].keys())

        # Process in batches
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]

            # Convert dicts to list of tuples
            rows = []
            for row in batch:
                rows.append([row.get(col) for col in column_names])

            # Insert batch
            client.insert(table, rows, column_names=column_names)
            total_inserted += len(batch)
            logger.info(f"Inserted batch {i // batch_size + 1}: {len(batch)} rows (total: {total_inserted})")

        return total_inserted

    finally:
        if should_release and client:
            release_client(client)


def health_check(client: Optional[Client] = None) -> Tuple[bool, str]:
    """
    Check if ClickHouse connection is healthy.

    Args:
        client: Optional existing client

    Returns:
        Tuple of (is_healthy, message)
    """
    should_release = client is None
    try:
        if client is None:
            client = get_client()

        result = client.query("SELECT 1 as health")
        if result.result_rows and result.result_rows[0][0] == 1:
            return True, "ClickHouse connection healthy"
        return False, "Unexpected health check result"

    except Exception as e:
        return False, f"Health check failed: {e}"

    finally:
        if should_release and client:
            release_client(client)


def get_table_count(table: str, client: Optional[Client] = None) -> int:
    """
    Get the row count of a table.

    Args:
        table: Table name
        client: Optional existing client

    Returns:
        int: Number of rows in table
    """
    result = execute_query(f"SELECT count() as cnt FROM {table}", client=client)
    return result[0]['cnt'] if result else 0


def table_exists(table: str, client: Optional[Client] = None) -> bool:
    """
    Check if a table exists in the database.

    Args:
        table: Table name
        client: Optional existing client

    Returns:
        bool: True if table exists
    """
    should_release = client is None
    try:
        if client is None:
            client = get_client()

        result = client.query(
            "SELECT 1 FROM system.tables WHERE database = {db:String} AND name = {table:String}",
            parameters={"db": client.database, "table": table}
        )
        return len(result.result_rows) > 0

    finally:
        if should_release and client:
            release_client(client)


def close_pool() -> None:
    """Close the global connection pool."""
    global _pool
    if _pool:
        _pool.close_all()
        _pool = None
        logger.info("Global ClickHouse pool closed")


# Cleanup function for application shutdown
def shutdown() -> None:
    """Cleanup function to be called on application shutdown."""
    close_pool()


if __name__ == '__main__':
    # Simple test/demo
    logging.basicConfig(level=logging.DEBUG)

    print("Testing ClickHouse client...")

    try:
        # Test health check
        is_healthy, message = health_check()
        print(f"Health check: {message}")

        if is_healthy:
            # Test query
            with get_connection() as client:
                result = execute_query("SELECT 1 + 1 as result", client=client)
                print(f"Query result: {result}")

                # Test table exists
                exists = table_exists("ssn_data", client=client)
                print(f"Table ssn_data exists: {exists}")

        print("Test completed successfully!")

    except Exception as e:
        print(f"Test failed: {e}")

    finally:
        shutdown()
