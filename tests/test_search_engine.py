"""
Test infrastructure for SearchEngine class.

This module provides comprehensive testing for the SearchEngine class using unittest.
It includes:
- Base test class with setup/teardown infrastructure
- Helper methods for test data generation (valid, invalid, edge cases)
- Helper methods for assertions and verification
- Infrastructure tests to verify database and test setup

The tests use a temporary SQLite database to ensure isolation from the production database.
"""

import unittest
import tempfile
import os
import json
import sqlite3
from database.search_engine import SearchEngine
from database.db_schema import initialize_database, get_connection, close_connection
from database.csv_importer import DataValidator

# Test constants for valid data
TEST_SSN_VALID = [
    '123-45-6789',
    '987-65-4321',
    '555-12-3456',
    '111-22-3333',
    '999-88-7777',
    '222-33-4444',
    '777-66-5555'
]

TEST_EMAILS_VALID = [
    'test@example.com',
    'user@domain.org',
    'john.doe@company.net',
    'jane_smith@business.com',
    'admin@website.gov',
    'contact@service.io',
    'support@platform.edu'
]

TEST_STATES = ['CA', 'NY', 'TX', 'IL', 'FL', 'WA', 'MA']

TEST_ZIPS = ['12345', '90210', '60601', '75001', '33101', '98101', '02101']


class TestSearchEngineBase(unittest.TestCase):
    """
    Base class for SearchEngine tests.

    Provides setup/teardown infrastructure for creating and managing a temporary
    test database, populating it with test data, and cleaning up after tests.
    """

    @classmethod
    def setUpClass(cls):
        """
        Create temporary database once for all tests in the class.

        Creates a temporary database file and initializes it with the required
        schema (tables and indexes).
        """
        # Create temporary database file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        cls.test_db_path = temp_file.name
        temp_file.close()

        # Initialize database with schema
        try:
            conn = initialize_database(cls.test_db_path)
            close_connection(conn)
        except Exception as e:
            # Clean up if initialization fails
            if os.path.exists(cls.test_db_path):
                os.unlink(cls.test_db_path)
            raise Exception(f"Failed to initialize test database: {e}")

    def setUp(self):
        """
        Prepare each individual test.

        Creates a SearchEngine instance and populates the database with test data.
        """
        # Create DataValidator instance
        self.validator = DataValidator()

        # Create SearchEngine instance
        self.engine = SearchEngine(db_path=self.test_db_path)

        # Populate database with test data
        self._populate_test_data()

    def tearDown(self):
        """
        Clean up after each test.

        Clears all data from the test database tables and destroys the
        SearchEngine instance.
        """
        # Clear test data from database
        self._clear_test_data()

        # Clean up engine instance
        self.engine = None

    @classmethod
    def tearDownClass(cls):
        """
        Final cleanup after all tests in the class.

        Removes the temporary database file and associated WAL/SHM files.
        """
        # Remove temporary database file
        try:
            if os.path.exists(cls.test_db_path):
                os.unlink(cls.test_db_path)

            # Remove WAL and SHM files if they exist (SQLite WAL mode)
            wal_file = cls.test_db_path + '-wal'
            shm_file = cls.test_db_path + '-shm'

            if os.path.exists(wal_file):
                os.unlink(wal_file)

            if os.path.exists(shm_file):
                os.unlink(shm_file)

        except Exception as e:
            print(f"Warning: Failed to clean up test database files: {e}")

    # ========================================================================
    # Helper methods for test data generation
    # ========================================================================

    def _get_test_data_valid(self):
        """
        Generate valid test data for database population.

        Returns:
            list: List of dictionaries containing valid test records with various
                  combinations of complete and partial data.
        """
        return [
            {
                'firstname': 'John',
                'lastname': 'Doe',
                'ssn': '123-45-6789',
                'address': '123 Main St',
                'city': 'Los Angeles',
                'state': 'CA',
                'zip': '90210',
                'email': 'john.doe@example.com'
            },
            {
                'firstname': 'Jane',
                'lastname': 'Smith',
                'ssn': '987-65-4321',
                'address': '456 Oak Ave',
                'city': 'New York',
                'state': 'NY',
                'zip': '12345',
                'email': 'JANE.SMITH@DOMAIN.ORG'  # Test email normalization
            },
            {
                'firstname': 'Robert',
                'lastname': 'Johnson',
                'ssn': '555 12 3456',  # SSN with spaces
                'address': '789 Pine Rd',
                'city': 'Chicago',
                'state': 'IL',
                'zip': '60601',
                'email': 'robert@company.net'
            },
            {
                'firstname': 'Maria',
                'lastname': 'Garcia',
                'ssn': '111223333',  # SSN without separators
                'address': '321 Elm St',
                'city': 'Dallas',
                'state': 'TX',
                'zip': '75001',
                'email': 'maria.garcia@business.com'
            },
            {
                'firstname': 'Michael',
                'lastname': 'Williams',
                'ssn': '999-88-7777',
                'address': None,  # Partial data
                'city': 'Miami',
                'state': 'FL',
                'zip': '33101',
                'email': None
            },
            {
                'firstname': 'Sarah',
                'lastname': 'Brown',
                'ssn': '222-33-4444',
                'address': '654 Maple Dr',
                'city': 'Seattle',
                'state': 'WA',
                'zip': '98101',
                'email': 'sarah.brown@service.io'
            },
            {
                'firstname': 'David',
                'lastname': 'Brown',  # Same lastname as previous, different location
                'ssn': '777-66-5555',
                'address': '987 Cedar Ln',
                'city': 'Boston',
                'state': 'MA',
                'zip': '02101',
                'email': 'david.brown@platform.edu'
            },
            {
                'firstname': 'John',  # Same firstname as first record
                'lastname': 'Smith',
                'ssn': '444-55-6666',
                'address': '111 First St',
                'city': 'Los Angeles',  # Same city/zip as first record
                'state': 'CA',
                'zip': '90210',
                'email': 'john.smith@test.com'
            },
            {
                'firstname': 'Emily',
                'lastname': 'Davis',
                'ssn': '333-44-5555',
                'address': '222 Second Ave',
                'city': 'Austin',
                'state': 'TX',  # Same state as Maria Garcia
                'zip': '78701',
                'email': 'emily.davis@example.org'
            },
            {
                'firstname': 'Jennifer',
                'lastname': 'Wilson',
                'ssn': '666-77-8888',
                'address': None,  # Minimal data
                'city': None,
                'state': None,
                'zip': None,
                'email': None
            }
        ]

    def _get_test_data_invalid(self):
        """
        Generate invalid test data for negative testing.

        Returns:
            list: List of dictionaries containing invalid test records for testing
                  validation and error handling.
        """
        return [
            # Invalid SSN - too few digits
            {
                'firstname': 'Invalid',
                'lastname': 'SSN1',
                'ssn': '123-45-678',  # Only 8 digits
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345',
                'email': 'test@test.com'
            },
            # Invalid SSN - too many digits
            {
                'firstname': 'Invalid',
                'lastname': 'SSN2',
                'ssn': '123-45-67890',  # 10 digits
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345',
                'email': 'test@test.com'
            },
            # Invalid SSN - contains letters
            {
                'firstname': 'Invalid',
                'lastname': 'SSN3',
                'ssn': '123-AB-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345',
                'email': 'test@test.com'
            },
            # Invalid email - no @
            {
                'firstname': 'Invalid',
                'lastname': 'Email1',
                'ssn': '123-45-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345',
                'email': 'testtest.com'
            },
            # Invalid email - no domain
            {
                'firstname': 'Invalid',
                'lastname': 'Email2',
                'ssn': '123-45-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345',
                'email': 'test@'
            },
            # Invalid email - spaces
            {
                'firstname': 'Invalid',
                'lastname': 'Email3',
                'ssn': '123-45-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345',
                'email': 'test user@test.com'
            },
            # Invalid state code
            {
                'firstname': 'Invalid',
                'lastname': 'State1',
                'ssn': '123-45-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'XX',  # Not a valid state
                'zip': '12345',
                'email': 'test@test.com'
            },
            # Invalid state - not 2 characters
            {
                'firstname': 'Invalid',
                'lastname': 'State2',
                'ssn': '123-45-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'California',  # Full name instead of code
                'zip': '12345',
                'email': 'test@test.com'
            },
            # Invalid ZIP - too short
            {
                'firstname': 'Invalid',
                'lastname': 'Zip1',
                'ssn': '123-45-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '1234',  # Only 4 digits
                'email': 'test@test.com'
            },
            # Invalid ZIP - too long
            {
                'firstname': 'Invalid',
                'lastname': 'Zip2',
                'ssn': '123-45-6789',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '1234567890',  # 10 digits
                'email': 'test@test.com'
            },
            # Empty SSN
            {
                'firstname': 'Invalid',
                'lastname': 'Empty',
                'ssn': '',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345',
                'email': 'test@test.com'
            }
        ]

    def _get_test_data_edge_cases(self):
        """
        Generate edge case test data.

        Returns:
            list: List of dictionaries containing edge case test records including
                  very long strings, special characters, and minimal valid values.
        """
        return [
            # Very long strings
            {
                'firstname': 'A' * 100,  # Very long firstname
                'lastname': 'B' * 100,   # Very long lastname
                'ssn': '123-45-6789',
                'address': 'C' * 200,    # Very long address
                'city': 'D' * 100,       # Very long city
                'state': 'CA',
                'zip': '12345',
                'email': 'test@example.com'
            },
            # Special characters in names
            {
                'firstname': "O'Brien",
                'lastname': 'Smith',
                'ssn': '123-45-6789',
                'address': '123 Main St',
                'city': 'New York',
                'state': 'NY',
                'zip': '12345',
                'email': 'obrien@test.com'
            },
            # Hyphenated name
            {
                'firstname': 'Jean-Pierre',
                'lastname': 'Dubois',
                'ssn': '987-65-4321',
                'address': '456 Oak Ave',
                'city': 'Los Angeles',
                'state': 'CA',
                'zip': '90210',
                'email': 'jean.pierre@test.com'
            },
            # Very long email local part
            {
                'firstname': 'Test',
                'lastname': 'User',
                'ssn': '555-12-3456',
                'address': '789 Pine Rd',
                'city': 'Chicago',
                'state': 'IL',
                'zip': '60601',
                'email': 'verylongemailaddresslocalpart1234567890@example.com'
            },
            # Minimal valid data (only SSN)
            {
                'firstname': None,
                'lastname': None,
                'ssn': '111-22-3333',
                'address': None,
                'city': None,
                'state': None,
                'zip': None,
                'email': None
            },
            # 9-digit ZIP code
            {
                'firstname': 'ZIP',
                'lastname': 'Test',
                'ssn': '999-88-7777',
                'address': '123 Test St',
                'city': 'Test City',
                'state': 'CA',
                'zip': '12345-6789',  # Extended ZIP
                'email': 'ziptest@test.com'
            }
        ]

    def _populate_test_data(self):
        """
        Populate the test database with valid test data.

        Splits the valid test data between ssn_1 and ssn_2 tables, normalizes
        the data using DataValidator, and inserts it into the database.
        """
        conn = None
        try:
            # Get valid test data
            test_data = self._get_test_data_valid()

            # Split data between tables
            mid_point = len(test_data) // 2
            ssn_1_data = test_data[:mid_point]
            ssn_2_data = test_data[mid_point:]

            # Get database connection
            conn = get_connection(self.test_db_path)
            cursor = conn.cursor()

            # Insert data into ssn_1
            for record in ssn_1_data:
                # Validate and normalize SSN
                normalized_ssn = self.validator.validate_ssn(record['ssn'])
                if normalized_ssn is None:
                    raise ValueError(f"Invalid SSN: {record['ssn']}")

                # Validate and normalize email if present
                normalized_email = None
                if record.get('email'):
                    try:
                        normalized_email = self.validator.validate_email(record['email'])
                    except ValueError:
                        normalized_email = None

                cursor.execute('''
                    INSERT INTO ssn_1 (firstname, lastname, middlename, ssn, address, city, state, zip, phone, dob, email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.get('firstname'),
                    record.get('lastname'),
                    record.get('middlename'),
                    normalized_ssn,
                    record.get('address'),
                    record.get('city'),
                    record.get('state'),
                    record.get('zip'),
                    record.get('phone'),
                    record.get('dob'),
                    normalized_email
                ))

            # Insert data into ssn_2
            for record in ssn_2_data:
                # Validate and normalize SSN
                normalized_ssn = self.validator.validate_ssn(record['ssn'])
                if normalized_ssn is None:
                    raise ValueError(f"Invalid SSN: {record['ssn']}")

                # Validate and normalize email if present
                normalized_email = None
                if record.get('email'):
                    try:
                        normalized_email = self.validator.validate_email(record['email'])
                    except ValueError:
                        normalized_email = None

                cursor.execute('''
                    INSERT INTO ssn_2 (firstname, lastname, middlename, ssn, address, city, state, zip, phone, dob, email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.get('firstname'),
                    record.get('lastname'),
                    record.get('middlename'),
                    normalized_ssn,
                    record.get('address'),
                    record.get('city'),
                    record.get('state'),
                    record.get('zip'),
                    record.get('phone'),
                    record.get('dob'),
                    normalized_email
                ))

            # Commit changes
            conn.commit()

        except Exception as e:
            print(f"Error populating test data: {e}")
            raise
        finally:
            # Close connection
            if conn is not None:
                close_connection(conn)

    def _clear_test_data(self):
        """
        Clear all data from test database tables.

        Removes all records from both ssn_1 and ssn_2 tables to ensure test isolation.
        """
        conn = None
        try:
            # Get database connection
            conn = get_connection(self.test_db_path)
            cursor = conn.cursor()

            # Clear both tables
            cursor.execute('DELETE FROM ssn_1')
            cursor.execute('DELETE FROM ssn_2')

            # Commit changes
            conn.commit()

        except Exception as e:
            print(f"Error clearing test data: {e}")
            raise
        finally:
            # Close connection
            if conn is not None:
                close_connection(conn)

    def _insert_record(self, table_name, record_data):
        """
        Insert a single record into a specified table.

        Args:
            table_name (str): Name of the table ('ssn_1' or 'ssn_2')
            record_data (dict): Dictionary containing record fields

        Returns:
            int: ID of the inserted record
        """
        conn = None
        try:
            # Validate table name
            if table_name not in ['ssn_1', 'ssn_2']:
                raise ValueError(f"Invalid table name: {table_name}")

            # Validate and normalize SSN
            normalized_ssn = self.validator.validate_ssn(record_data['ssn'])
            if normalized_ssn is None:
                raise ValueError(f"Invalid SSN: {record_data['ssn']}")

            # Validate and normalize email if present
            normalized_email = None
            if record_data.get('email'):
                try:
                    normalized_email = self.validator.validate_email(record_data['email'])
                except ValueError:
                    normalized_email = None

            # Get database connection
            conn = get_connection(self.test_db_path)
            cursor = conn.cursor()

            # Insert record
            cursor.execute(f'''
                INSERT INTO {table_name} (firstname, lastname, middlename, ssn, address, city, state, zip, phone, dob, email)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record_data.get('firstname'),
                record_data.get('lastname'),
                record_data.get('middlename'),
                normalized_ssn,
                record_data.get('address'),
                record_data.get('city'),
                record_data.get('state'),
                record_data.get('zip'),
                record_data.get('phone'),
                record_data.get('dob'),
                normalized_email
            ))

            # Get inserted record ID
            record_id = cursor.lastrowid

            # Commit changes
            conn.commit()

            return record_id

        except Exception as e:
            print(f"Error inserting record: {e}")
            raise
        finally:
            # Close connection
            if conn is not None:
                close_connection(conn)

    # ========================================================================
    # Helper methods for assertions and verification
    # ========================================================================

    def _assert_json_response(self, json_string, expected_count):
        """
        Parse and validate JSON response from search methods.

        Args:
            json_string (str): JSON string returned by search method
            expected_count (int): Expected number of records in response

        Returns:
            list: Parsed list of records for further assertions
        """
        # Parse JSON
        try:
            records = json.loads(json_string)
        except json.JSONDecodeError as e:
            self.fail(f"Failed to parse JSON response: {e}")

        # Verify it's a list
        self.assertIsInstance(records, list, "Response should be a list")

        # Verify count
        self.assertEqual(len(records), expected_count,
                        f"Expected {expected_count} records, got {len(records)}")

        return records

    def _assert_record_fields(self, record, expected_fields):
        """
        Verify that a record contains the expected fields and values.

        Args:
            record (dict): Record dictionary from search results
            expected_fields (dict): Dictionary of expected field values
        """
        # Check required fields exist
        required_fields = ['id', 'firstname', 'lastname', 'ssn', 'source_table']
        for field in required_fields:
            self.assertIn(field, record, f"Record missing required field: {field}")

        # Check expected field values
        for field, expected_value in expected_fields.items():
            if field in record:
                self.assertEqual(record[field], expected_value,
                               f"Field '{field}' mismatch: expected '{expected_value}', got '{record[field]}'")


class TestSearchEngineSetup(TestSearchEngineBase):
    """
    Test class for verifying test infrastructure setup.

    Ensures that the database, tables, indexes, and test data are properly
    initialized and accessible.
    """

    def test_database_initialization(self):
        """Verify that the temporary test database is created and accessible."""
        # Check that database file exists
        self.assertTrue(os.path.exists(self.test_db_path),
                       "Test database file should exist")

        # Check that we can connect to the database
        conn = None
        try:
            conn = get_connection(self.test_db_path)
            self.assertIsNotNone(conn, "Should be able to connect to test database")
        finally:
            if conn is not None:
                close_connection(conn)

    def test_tables_exist(self):
        """Verify that both ssn_1 and ssn_2 tables exist."""
        conn = None
        try:
            conn = get_connection(self.test_db_path)
            cursor = conn.cursor()

            # Check ssn_1 table exists
            cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='ssn_1'
            ''')
            result = cursor.fetchone()
            self.assertIsNotNone(result, "Table ssn_1 should exist")

            # Check ssn_2 table exists
            cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='ssn_2'
            ''')
            result = cursor.fetchone()
            self.assertIsNotNone(result, "Table ssn_2 should exist")

        finally:
            if conn is not None:
                close_connection(conn)

    def test_indexes_exist(self):
        """Verify that all required indexes are created."""
        conn = None
        try:
            conn = get_connection(self.test_db_path)
            cursor = conn.cursor()

            # Get all indexes
            cursor.execute('''
                SELECT name FROM sqlite_master
                WHERE type='index'
            ''')
            indexes = [row[0] for row in cursor.fetchall()]

            # Check required indexes for ssn_1
            expected_indexes_ssn_1 = [
                'idx_ssn_1_name_zip',
                'idx_ssn_1_name_state',
                'idx_ssn_1_email'
            ]

            for index_name in expected_indexes_ssn_1:
                self.assertIn(index_name, indexes,
                             f"Index {index_name} should exist for ssn_1")

            # Check required indexes for ssn_2
            expected_indexes_ssn_2 = [
                'idx_ssn_2_name_zip',
                'idx_ssn_2_name_state',
                'idx_ssn_2_email'
            ]

            for index_name in expected_indexes_ssn_2:
                self.assertIn(index_name, indexes,
                             f"Index {index_name} should exist for ssn_2")

        finally:
            if conn is not None:
                close_connection(conn)

    def test_test_data_populated(self):
        """Verify that test data is loaded into both tables."""
        conn = None
        try:
            conn = get_connection(self.test_db_path)
            cursor = conn.cursor()

            # Check ssn_1 has data
            cursor.execute('SELECT COUNT(*) FROM ssn_1')
            count_ssn_1 = cursor.fetchone()[0]
            self.assertGreater(count_ssn_1, 0, "Table ssn_1 should contain test data")

            # Check ssn_2 has data
            cursor.execute('SELECT COUNT(*) FROM ssn_2')
            count_ssn_2 = cursor.fetchone()[0]
            self.assertGreater(count_ssn_2, 0, "Table ssn_2 should contain test data")

            # Verify total count matches expected
            total_count = count_ssn_1 + count_ssn_2
            expected_count = len(self._get_test_data_valid())
            self.assertEqual(total_count, expected_count,
                            f"Expected {expected_count} total records, got {total_count}")

        finally:
            if conn is not None:
                close_connection(conn)

    def test_search_engine_instance(self):
        """Verify that SearchEngine instance is created with correct database path."""
        # Check that engine instance exists
        self.assertIsNotNone(self.engine, "SearchEngine instance should be created")

        # Check that engine has the correct database path
        self.assertEqual(self.engine.db_path, self.test_db_path,
                        "SearchEngine should use test database path")


class TestSearchBySSN(TestSearchEngineBase):
    """
    Test class for search_by_ssn() method.

    Tests SSN search functionality including format normalization,
    validation, and cross-table searching.
    """

    def test_search_by_ssn_valid_with_dashes(self):
        """Test successful search with valid SSN in XXX-XX-XXXX format."""
        result = self.engine.search_by_ssn('123-45-6789')
        records = self._assert_json_response(result, 1)

        # Verify record fields
        record = records[0]
        self.assertEqual(record['firstname'], 'John')
        self.assertEqual(record['lastname'], 'Doe')
        self.assertEqual(record['ssn'], '123-45-6789')
        self.assertIn('source_table', record)
        self.assertIn(record['source_table'], ['ssn_1', 'ssn_2'])

    def test_search_by_ssn_without_dashes(self):
        """Test search with SSN without dashes (normalization)."""
        result = self.engine.search_by_ssn('987654321')
        records = self._assert_json_response(result, 1)

        # Verify record found and SSN formatted correctly
        record = records[0]
        self.assertEqual(record['firstname'], 'Jane')
        self.assertEqual(record['lastname'], 'Smith')
        self.assertEqual(record['ssn'], '987-65-4321')

    def test_search_by_ssn_with_spaces(self):
        """Test search with SSN containing spaces."""
        result = self.engine.search_by_ssn('555 12 3456')
        records = self._assert_json_response(result, 1)

        # Verify record found and SSN normalized
        record = records[0]
        self.assertEqual(record['firstname'], 'Robert')
        self.assertEqual(record['ssn'], '555-12-3456')

    def test_search_by_ssn_invalid_too_short(self):
        """Test handling of invalid SSN (less than 9 digits)."""
        result = self.engine.search_by_ssn('12345678')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_ssn_invalid_too_long(self):
        """Test handling of invalid SSN (more than 9 digits)."""
        result = self.engine.search_by_ssn('1234567890')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_ssn_invalid_with_letters(self):
        """Test handling of SSN with letters."""
        result = self.engine.search_by_ssn('123-AB-6789')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_ssn_not_found(self):
        """Test search for non-existent SSN."""
        result = self.engine.search_by_ssn('000-00-0000')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_ssn_from_both_tables(self):
        """Test that search works across both ssn_1 and ssn_2 tables."""
        # Clear and insert specific test data
        self._clear_test_data()

        # Insert record in ssn_1
        self._insert_record('ssn_1', {
            'firstname': 'TestUser1',
            'lastname': 'Table1',
            'ssn': '111-11-1111',
            'address': '123 Test St',
            'city': 'Test City',
            'state': 'CA',
            'zip': '12345',
            'email': 'test1@table1.com'
        })

        # Insert record in ssn_2
        self._insert_record('ssn_2', {
            'firstname': 'TestUser2',
            'lastname': 'Table2',
            'ssn': '222-22-2222',
            'address': '456 Test Ave',
            'city': 'Test Town',
            'state': 'NY',
            'zip': '54321',
            'email': 'test2@table2.com'
        })

        # Search for first SSN
        result1 = self.engine.search_by_ssn('111-11-1111')
        records1 = self._assert_json_response(result1, 1)
        self.assertEqual(records1[0]['source_table'], 'ssn_1')

        # Search for second SSN
        result2 = self.engine.search_by_ssn('222-22-2222')
        records2 = self._assert_json_response(result2, 1)
        self.assertEqual(records2[0]['source_table'], 'ssn_2')

    def test_search_by_ssn_with_limit(self):
        """Test search with limit parameter."""
        result = self.engine.search_by_ssn('123-45-6789', limit=1)
        records = self._assert_json_response(result, 1)
        self.assertLessEqual(len(records), 1)

    def test_search_by_ssn_empty_string(self):
        """Test handling of empty string."""
        result = self.engine.search_by_ssn('')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])


class TestSearchByEmail(TestSearchEngineBase):
    """
    Test class for search_by_email() method.

    Tests email search functionality including case-insensitive matching,
    validation, and normalization.
    """

    def test_search_by_email_valid_lowercase(self):
        """Test successful search with valid lowercase email."""
        result = self.engine.search_by_email('john.doe@example.com')
        records = self._assert_json_response(result, 1)

        # Verify record fields
        record = records[0]
        self.assertEqual(record['firstname'], 'John')
        self.assertEqual(record['lastname'], 'Doe')
        self.assertEqual(record['email'].lower(), 'john.doe@example.com')

    def test_search_by_email_case_insensitive(self):
        """Test case-insensitive search (COLLATE NOCASE)."""
        # Test uppercase
        result_upper = self.engine.search_by_email('JANE.SMITH@DOMAIN.ORG')
        records_upper = self._assert_json_response(result_upper, 1)
        self.assertEqual(records_upper[0]['firstname'], 'Jane')
        self.assertEqual(records_upper[0]['lastname'], 'Smith')

        # Test lowercase
        result_lower = self.engine.search_by_email('jane.smith@domain.org')
        records_lower = self._assert_json_response(result_lower, 1)
        self.assertEqual(records_lower[0]['firstname'], 'Jane')

        # Test mixed case
        result_mixed = self.engine.search_by_email('Jane.Smith@Domain.ORG')
        records_mixed = self._assert_json_response(result_mixed, 1)
        self.assertEqual(records_mixed[0]['firstname'], 'Jane')

    def test_search_by_email_with_whitespace(self):
        """Test that whitespace is removed (normalization)."""
        result = self.engine.search_by_email('  robert@company.net  ')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'Robert')
        self.assertEqual(records[0]['lastname'], 'Johnson')

    def test_search_by_email_invalid_no_at_symbol(self):
        """Test handling of email without @ symbol."""
        result = self.engine.search_by_email('testexample.com')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_email_invalid_no_dot(self):
        """Test handling of email without dot in domain."""
        result = self.engine.search_by_email('test@examplecom')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_email_not_found(self):
        """Test search for non-existent email."""
        result = self.engine.search_by_email('notfound@nowhere.com')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_email_from_both_tables(self):
        """Test that search works across both tables."""
        # Clear and insert specific test data
        self._clear_test_data()

        # Insert record in ssn_1
        self._insert_record('ssn_1', {
            'firstname': 'EmailTest1',
            'lastname': 'Table1',
            'ssn': '111-11-1111',
            'address': '123 Test St',
            'city': 'Test City',
            'state': 'CA',
            'zip': '12345',
            'email': 'test1@table1.com'
        })

        # Insert record in ssn_2
        self._insert_record('ssn_2', {
            'firstname': 'EmailTest2',
            'lastname': 'Table2',
            'ssn': '222-22-2222',
            'address': '456 Test Ave',
            'city': 'Test Town',
            'state': 'NY',
            'zip': '54321',
            'email': 'test2@table2.com'
        })

        # Search for first email
        result1 = self.engine.search_by_email('test1@table1.com')
        records1 = self._assert_json_response(result1, 1)
        self.assertEqual(records1[0]['source_table'], 'ssn_1')

        # Search for second email
        result2 = self.engine.search_by_email('test2@table2.com')
        records2 = self._assert_json_response(result2, 1)
        self.assertEqual(records2[0]['source_table'], 'ssn_2')

    def test_search_by_email_with_limit(self):
        """Test search with limit parameter."""
        result = self.engine.search_by_email('john.doe@example.com', limit=1)
        records = json.loads(result)
        self.assertLessEqual(len(records), 1)

    def test_search_by_email_empty_string(self):
        """Test handling of empty string."""
        result = self.engine.search_by_email('')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_email_special_characters(self):
        """Test search with special characters (dots, underscores)."""
        # Test with email containing dots
        result = self.engine.search_by_email('maria.garcia@business.com')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'Maria')

        # Test with email containing dots and underscores
        result = self.engine.search_by_email('sarah.brown@service.io')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'Sarah')


class TestSearchByNameZip(TestSearchEngineBase):
    """
    Test class for search_by_name_zip() method.

    Tests name and ZIP code search functionality including validation,
    normalization, and composite index usage.
    """

    def test_search_by_name_zip_valid(self):
        """Test successful search by name and ZIP code."""
        result = self.engine.search_by_name_zip('John', 'Doe', '90210')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)

        # Verify all records match criteria
        for record in records:
            self.assertEqual(record['firstname'], 'John')
            self.assertEqual(record['lastname'], 'Doe')
            self.assertEqual(record['zip'], '90210')

    def test_search_by_name_zip_multiple_results(self):
        """Test that multiple matching records are returned."""
        # Search for John Doe in 90210 (exists in test data)
        result = self.engine.search_by_name_zip('John', 'Doe', '90210')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)

        # Search for John Smith in 90210 (also exists)
        result = self.engine.search_by_name_zip('John', 'Smith', '90210')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)

    def test_search_by_name_zip_not_found(self):
        """Test search for non-existent combination."""
        result = self.engine.search_by_name_zip('NonExistent', 'Person', '00000')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_name_zip_missing_firstname(self):
        """Test handling of missing firstname (required field)."""
        # Empty string
        result = self.engine.search_by_name_zip('', 'Doe', '90210')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

        # None
        result = self.engine.search_by_name_zip(None, 'Doe', '90210')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_name_zip_missing_lastname(self):
        """Test handling of missing lastname (required field)."""
        # Empty string
        result = self.engine.search_by_name_zip('John', '', '90210')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

        # None
        result = self.engine.search_by_name_zip('John', None, '90210')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_name_zip_empty_zip(self):
        """Test search with empty ZIP code."""
        result = self.engine.search_by_name_zip('John', 'Doe', '')
        records = json.loads(result)
        # May return empty array or records with empty zip
        self.assertIsInstance(records, list)

    def test_search_by_name_zip_with_whitespace(self):
        """Test that whitespace is removed (normalization)."""
        result = self.engine.search_by_name_zip('  John  ', '  Doe  ', '  90210  ')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]['firstname'], 'John')
        self.assertEqual(records[0]['lastname'], 'Doe')
        self.assertEqual(records[0]['zip'], '90210')

    def test_search_by_name_zip_from_both_tables(self):
        """Test that search works across both tables (UNION)."""
        # Clear and insert specific test data
        self._clear_test_data()

        # Insert record in ssn_1
        self._insert_record('ssn_1', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '111-11-1111',
            'address': '123 Test St',
            'city': 'Test City',
            'state': 'CA',
            'zip': '11111',
            'email': 'test1@test.com'
        })

        # Insert record in ssn_2 with same name and zip
        self._insert_record('ssn_2', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '222-22-2222',
            'address': '456 Test Ave',
            'city': 'Test Town',
            'state': 'NY',
            'zip': '11111',
            'email': 'test2@test.com'
        })

        # Search should return both records
        result = self.engine.search_by_name_zip('Test', 'User', '11111')
        records = json.loads(result)
        self.assertEqual(len(records), 2)

        # Verify different source tables
        source_tables = [r['source_table'] for r in records]
        self.assertIn('ssn_1', source_tables)
        self.assertIn('ssn_2', source_tables)

    def test_search_by_name_zip_with_limit(self):
        """Test search with limit parameter."""
        result = self.engine.search_by_name_zip('John', 'Doe', '90210', limit=1)
        records = json.loads(result)
        self.assertLessEqual(len(records), 1)

    def test_search_by_name_zip_case_sensitive(self):
        """Test that name search is case-sensitive."""
        # Search with lowercase (data has 'John' with capital J)
        result = self.engine.search_by_name_zip('john', 'doe', '90210')
        records = json.loads(result)
        # Should return empty array since search is case-sensitive
        self.assertEqual(len(records), 0)


class TestSearchByNameState(TestSearchEngineBase):
    """
    Test class for search_by_name_state() method.

    Tests name and state search functionality including state code normalization,
    validation, and composite index usage.
    """

    def test_search_by_name_state_valid(self):
        """Test successful search by name and state code."""
        result = self.engine.search_by_name_state('Jane', 'Smith', 'NY')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)

        # Verify record fields
        record = records[0]
        self.assertEqual(record['firstname'], 'Jane')
        self.assertEqual(record['lastname'], 'Smith')
        self.assertEqual(record['state'], 'NY')

    def test_search_by_name_state_uppercase_normalization(self):
        """Test that state code is normalized to uppercase."""
        # Lowercase
        result_lower = self.engine.search_by_name_state('Jane', 'Smith', 'ny')
        records_lower = json.loads(result_lower)
        self.assertGreaterEqual(len(records_lower), 1)
        self.assertEqual(records_lower[0]['state'], 'NY')

        # Mixed case
        result_mixed = self.engine.search_by_name_state('Jane', 'Smith', 'Ny')
        records_mixed = json.loads(result_mixed)
        self.assertGreaterEqual(len(records_mixed), 1)
        self.assertEqual(records_mixed[0]['state'], 'NY')

    def test_search_by_name_state_multiple_results_same_state(self):
        """Test that all records with same state are returned."""
        # Search for Maria Garcia in TX
        result1 = self.engine.search_by_name_state('Maria', 'Garcia', 'TX')
        records1 = json.loads(result1)
        self.assertGreaterEqual(len(records1), 1)

        # Search for Emily Davis in TX
        result2 = self.engine.search_by_name_state('Emily', 'Davis', 'TX')
        records2 = json.loads(result2)
        self.assertGreaterEqual(len(records2), 1)

    def test_search_by_name_state_not_found(self):
        """Test search for non-existent combination."""
        result = self.engine.search_by_name_state('NonExistent', 'Person', 'CA')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_name_state_missing_firstname(self):
        """Test handling of missing firstname (required field)."""
        # Empty string
        result = self.engine.search_by_name_state('', 'Smith', 'NY')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

        # None
        result = self.engine.search_by_name_state(None, 'Smith', 'NY')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_name_state_missing_lastname(self):
        """Test handling of missing lastname (required field)."""
        # Empty string
        result = self.engine.search_by_name_state('Jane', '', 'NY')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

        # None
        result = self.engine.search_by_name_state('Jane', None, 'NY')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_name_state_invalid_state_code(self):
        """Test handling of invalid state code."""
        result = self.engine.search_by_name_state('Jane', 'Smith', 'XX')
        records = json.loads(result)
        # Method logs warning but continues search, returns empty array
        self.assertEqual(len(records), 0)

    def test_search_by_name_state_invalid_state_length(self):
        """Test handling of state code with incorrect length."""
        # Full state name instead of 2-letter code
        result = self.engine.search_by_name_state('Jane', 'Smith', 'California')
        records = json.loads(result)
        # Method logs warning, likely returns empty array
        self.assertIsInstance(records, list)

        # Single character
        result = self.engine.search_by_name_state('Jane', 'Smith', 'C')
        records = json.loads(result)
        self.assertIsInstance(records, list)

    def test_search_by_name_state_with_whitespace(self):
        """Test that whitespace is removed (normalization)."""
        result = self.engine.search_by_name_state('  Jane  ', '  Smith  ', '  ny  ')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]['firstname'], 'Jane')
        self.assertEqual(records[0]['lastname'], 'Smith')
        self.assertEqual(records[0]['state'], 'NY')

    def test_search_by_name_state_from_both_tables(self):
        """Test that search works across both tables (UNION)."""
        # Clear and insert specific test data
        self._clear_test_data()

        # Insert record in ssn_1
        self._insert_record('ssn_1', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '111-11-1111',
            'address': '123 Test St',
            'city': 'Test City',
            'state': 'CA',
            'zip': '12345',
            'email': 'test1@test.com'
        })

        # Insert record in ssn_2 with same name and state
        self._insert_record('ssn_2', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '222-22-2222',
            'address': '456 Test Ave',
            'city': 'Test Town',
            'state': 'CA',
            'zip': '54321',
            'email': 'test2@test.com'
        })

        # Search should return both records
        result = self.engine.search_by_name_state('Test', 'User', 'CA')
        records = json.loads(result)
        self.assertEqual(len(records), 2)

        # Verify different source tables
        source_tables = [r['source_table'] for r in records]
        self.assertIn('ssn_1', source_tables)
        self.assertIn('ssn_2', source_tables)

    def test_search_by_name_state_with_limit(self):
        """Test search with limit parameter."""
        result = self.engine.search_by_name_state('Jane', 'Smith', 'NY', limit=1)
        records = json.loads(result)
        self.assertLessEqual(len(records), 1)

    def test_search_by_name_state_empty_state(self):
        """Test search with empty state."""
        result = self.engine.search_by_name_state('Jane', 'Smith', '')
        records = json.loads(result)
        # May return records with empty state or empty array
        self.assertIsInstance(records, list)


class TestSearchByFields(TestSearchEngineBase):
    """
    Test class for search_by_fields() method - universal search functionality.

    Tests universal search that accepts any combination of fields including:
    middlename, address, city, phone, dob, and combinations with existing fields.
    """

    def test_search_by_middlename(self):
        """Test search by middlename only (new field)."""
        # Clear and insert test data with middlename
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Anderson',
            'middlename': 'James',
            'ssn': '123-45-6789',
            'address': '1234 Oak Street',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'john.anderson@email.com'
        })

        result = self.engine.search_by_fields(middlename='James')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'John')
        self.assertEqual(records[0]['lastname'], 'Anderson')

    def test_search_by_address(self):
        """Test search by address only."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Doe',
            'ssn': '123-45-6789',
            'address': '1234 Oak Street',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'john@test.com'
        })

        result = self.engine.search_by_fields(address='1234 Oak Street')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['address'], '1234 Oak Street')

    def test_search_by_city(self):
        """Test search by city only."""
        result = self.engine.search_by_fields(city='Los Angeles')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        for record in records:
            self.assertEqual(record['city'], 'Los Angeles')

    def test_search_by_phone(self):
        """Test search by phone only."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Doe',
            'ssn': '123-45-6789',
            'address': '123 Main St',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'phone': '(617) 555-0101',
            'email': 'john@test.com'
        })

        result = self.engine.search_by_fields(phone='(617) 555-0101')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['phone'], '(617) 555-0101')

    def test_search_by_dob(self):
        """Test search by date of birth."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Doe',
            'ssn': '123-45-6789',
            'address': '123 Main St',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'dob': '1985-03-15',
            'email': 'john@test.com'
        })

        result = self.engine.search_by_fields(dob='1985-03-15')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['dob'], '1985-03-15')

    def test_search_by_firstname_city(self):
        """Test search by firstname and city combination."""
        result = self.engine.search_by_fields(firstname='John', city='Los Angeles')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        for record in records:
            self.assertEqual(record['firstname'], 'John')
            self.assertEqual(record['city'], 'Los Angeles')

    def test_search_by_firstname_middlename(self):
        """Test search by firstname and middlename."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'Maria',
            'lastname': 'Rodriguez',
            'middlename': 'Louise',
            'ssn': '234-56-7890',
            'address': '5678 Maple Avenue',
            'city': 'San Francisco',
            'state': 'CA',
            'zip': '94102',
            'email': 'maria@test.com'
        })

        result = self.engine.search_by_fields(firstname='Maria', middlename='Louise')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'Maria')
        self.assertEqual(records[0]['lastname'], 'Rodriguez')

    def test_search_by_firstname_lastname_city(self):
        """Test search by firstname, lastname, and city."""
        result = self.engine.search_by_fields(
            firstname='Robert',
            lastname='Johnson',
            city='Chicago'
        )
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        for record in records:
            self.assertEqual(record['firstname'], 'Robert')
            self.assertEqual(record['lastname'], 'Johnson')
            self.assertEqual(record['city'], 'Chicago')

    def test_search_by_address_zip(self):
        """Test search by address and zip."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Doe',
            'ssn': '123-45-6789',
            'address': '1234 Oak Street',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'john@test.com'
        })

        result = self.engine.search_by_fields(address='1234 Oak Street', zip='02101')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['address'], '1234 Oak Street')
        self.assertEqual(records[0]['zip'], '02101')

    def test_search_by_address_city_state(self):
        """Test search by address, city, and state."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'Jennifer',
            'lastname': 'Chen',
            'ssn': '456-78-9012',
            'address': '3456 Elm Drive',
            'city': 'Houston',
            'state': 'TX',
            'zip': '77001',
            'email': 'jennifer@test.com'
        })

        result = self.engine.search_by_fields(
            address='3456 Elm Drive',
            city='Houston',
            state='TX'
        )
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['address'], '3456 Elm Drive')
        self.assertEqual(records[0]['city'], 'Houston')
        self.assertEqual(records[0]['state'], 'TX')

    def test_search_by_phone_state(self):
        """Test search by phone and state."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Doe',
            'ssn': '123-45-6789',
            'address': '123 Main St',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'phone': '(617) 555-0101',
            'email': 'john@test.com'
        })

        result = self.engine.search_by_fields(phone='(617) 555-0101', state='MA')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['phone'], '(617) 555-0101')
        self.assertEqual(records[0]['state'], 'MA')

    def test_search_by_firstname_lastname_middlename(self):
        """Test search by full name (firstname, lastname, middlename)."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Anderson',
            'middlename': 'James',
            'ssn': '123-45-6789',
            'address': '1234 Oak Street',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'john@test.com'
        })

        result = self.engine.search_by_fields(
            firstname='John',
            lastname='Anderson',
            middlename='James'
        )
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'John')
        self.assertEqual(records[0]['lastname'], 'Anderson')

    def test_search_by_city_state_zip(self):
        """Test search by location fields (city, state, zip)."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Doe',
            'ssn': '123-45-6789',
            'address': '123 Main St',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'john@test.com'
        })

        result = self.engine.search_by_fields(city='Boston', state='MA', zip='02101')
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['city'], 'Boston')
        self.assertEqual(records[0]['state'], 'MA')
        self.assertEqual(records[0]['zip'], '02101')

    def test_search_by_firstname_lastname_dob_city(self):
        """Test search by multiple fields including dob."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'Maria',
            'lastname': 'Rodriguez',
            'ssn': '234-56-7890',
            'address': '5678 Maple Avenue',
            'city': 'San Francisco',
            'state': 'CA',
            'zip': '94102',
            'dob': '1990-07-22',
            'email': 'maria@test.com'
        })

        result = self.engine.search_by_fields(
            firstname='Maria',
            lastname='Rodriguez',
            dob='1990-07-22',
            city='San Francisco'
        )
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'Maria')
        self.assertEqual(records[0]['dob'], '1990-07-22')

    def test_search_by_all_fields(self):
        """Test search by maximum number of fields."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'John',
            'lastname': 'Anderson',
            'middlename': 'James',
            'ssn': '123-45-6789',
            'address': '1234 Oak Street',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'phone': '(617) 555-0101',
            'dob': '1985-03-15',
            'email': 'john.anderson@email.com'
        })

        result = self.engine.search_by_fields(
            firstname='John',
            lastname='Anderson',
            middlename='James',
            address='1234 Oak Street',
            city='Boston',
            state='MA',
            zip='02101',
            phone='(617) 555-0101',
            ssn='123-45-6789',
            dob='1985-03-15',
            email='john.anderson@email.com'
        )
        records = self._assert_json_response(result, 1)
        self.assertEqual(records[0]['firstname'], 'John')
        self.assertEqual(records[0]['ssn'], '123-45-6789')
        self.assertEqual(records[0]['email'], 'john.anderson@email.com')

    def test_search_by_fields_with_limit(self):
        """Test search with limit parameter."""
        result = self.engine.search_by_fields(state='CA', limit=2)
        records = json.loads(result)
        self.assertLessEqual(len(records), 2)

    def test_search_by_fields_no_results(self):
        """Test search with no matching records."""
        result = self.engine.search_by_fields(
            firstname='NonExistent',
            city='Nowhere'
        )
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_fields_contradictory_data(self):
        """Test search with contradictory field combinations."""
        # CA zip in MA state
        result = self.engine.search_by_fields(state='CA', zip='02101')
        records = json.loads(result)
        self.assertEqual(len(records), 0)

    def test_search_by_fields_state_normalization(self):
        """Test that state is normalized to uppercase."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '123-45-6789',
            'address': '123 Test St',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'test@test.com'
        })

        # Search with lowercase state
        result = self.engine.search_by_fields(state='ma')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]['state'], 'MA')

    def test_search_by_fields_email_normalization(self):
        """Test that email is normalized to lowercase."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '123-45-6789',
            'address': '123 Test St',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'test@example.com'
        })

        # Search with uppercase email
        result = self.engine.search_by_fields(email='TEST@EXAMPLE.COM')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]['email'].lower(), 'test@example.com')

    def test_search_by_fields_ssn_normalization(self):
        """Test that SSN is normalized to XXX-XX-XXXX format."""
        # Search with SSN without dashes
        result = self.engine.search_by_fields(ssn='123456789')
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]['ssn'], '123-45-6789')

    def test_search_by_fields_invalid_ssn(self):
        """Test search with invalid SSN format."""
        # SSN with only 8 digits
        result = self.engine.search_by_fields(ssn='12345678')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

        # SSN with letters
        result = self.engine.search_by_fields(ssn='123-AB-6789')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_fields_no_valid_fields(self):
        """Test search with no valid search fields."""
        result = self.engine.search_by_fields()
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_fields_from_both_tables(self):
        """Test that search works across both ssn_1 and ssn_2 tables."""
        # Clear and insert test data
        self._clear_test_data()

        # Insert in ssn_1
        self._insert_record('ssn_1', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '111-11-1111',
            'address': '123 Test St',
            'city': 'TestCity',
            'state': 'MA',
            'zip': '11111',
            'email': 'test1@test.com'
        })

        # Insert in ssn_2 with same city
        self._insert_record('ssn_2', {
            'firstname': 'Another',
            'lastname': 'User',
            'ssn': '222-22-2222',
            'address': '456 Test Ave',
            'city': 'TestCity',
            'state': 'NY',
            'zip': '22222',
            'email': 'test2@test.com'
        })

        # Search by city should return both
        result = self.engine.search_by_fields(city='TestCity')
        records = json.loads(result)
        self.assertEqual(len(records), 2)

        # Verify different source tables
        source_tables = [r['source_table'] for r in records]
        self.assertIn('ssn_1', source_tables)
        self.assertIn('ssn_2', source_tables)

    def test_search_by_fields_whitespace_handling(self):
        """Test that whitespace is properly trimmed."""
        # Clear and insert test data
        self._clear_test_data()
        self._insert_record('ssn_1', {
            'firstname': 'Test',
            'lastname': 'User',
            'ssn': '123-45-6789',
            'address': '123 Test St',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'email': 'test@test.com'
        })

        # Search with extra whitespace
        result = self.engine.search_by_fields(
            firstname='  Test  ',
            city='  Boston  '
        )
        records = json.loads(result)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]['firstname'], 'Test')
        self.assertEqual(records[0]['city'], 'Boston')

    def test_search_by_middlename_not_found(self):
        """Test search by non-existent middlename."""
        result = self.engine.search_by_fields(middlename='NonExistentMiddleName')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_address_not_found(self):
        """Test search by non-existent address."""
        result = self.engine.search_by_fields(address='9999 Fake Street')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_phone_not_found(self):
        """Test search by non-existent phone."""
        result = self.engine.search_by_fields(phone='(999) 999-9999')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])

    def test_search_by_dob_not_found(self):
        """Test search by non-existent date of birth."""
        result = self.engine.search_by_fields(dob='2000-01-01')
        records = self._assert_json_response(result, 0)
        self.assertEqual(records, [])


if __name__ == '__main__':
    unittest.main()
