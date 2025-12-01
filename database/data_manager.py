"""
Data Manager Module for SQLite Database Operations

This module provides functionality for managing individual records in the SQLite database.
It reuses the DataValidator class from csv_importer.py for data validation and connection
functions from db_schema.py.

Main Features:
- Add/Update single records (UPSERT operations)
- Bulk add/update multiple records
- Delete records by SSN
- Partial record updates
- Data validation for all fields
"""

import logging
import sqlite3
from typing import Dict, List, Optional, Any

from database.db_schema import get_connection, close_connection, validate_table_name, DEFAULT_DB_PATH
from database.csv_importer import DataValidator


# Setup module logger
logger = logging.getLogger(__name__)


class DataManager:
    """
    Manages CRUD operations for database records with validation.

    This class provides methods to add, update, delete, and retrieve records
    from the SQLite database. All data is validated before database operations.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize DataManager with database path.

        Args:
            db_path: Path to SQLite database file. Uses DEFAULT_DB_PATH if not specified.
        """
        self.db_path = db_path if db_path else DEFAULT_DB_PATH
        self.validator = DataValidator()
        self.logger = logging.getLogger(self.__class__.__name__)

    def _validate_record_data(self, record_data: Dict[str, Any], current_record: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate and normalize record data before database operations.

        Args:
            record_data: Dictionary containing record fields
            current_record: Optional current record from database (used to preserve old values on validation failure)

        Returns:
            Dictionary with validated and normalized data

        Raises:
            ValueError: If SSN is missing or invalid
        """
        # Check for required SSN field
        if 'ssn' not in record_data or not record_data['ssn']:
            raise ValueError("SSN is required and cannot be empty")

        validated_data = {}

        # Validate SSN (required)
        normalized_ssn = self.validator.validate_ssn(record_data['ssn'])
        if normalized_ssn is None:
            raise ValueError('SSN is invalid')
        validated_data['ssn'] = normalized_ssn

        # Validate email (optional) - preserve old value on validation failure
        if 'email' in record_data and record_data['email']:
            try:
                validated_data['email'] = self.validator.validate_email(record_data['email'])
            except ValueError as e:
                self.logger.warning(f"Invalid email for SSN {validated_data['ssn']}: {e}")
                # Preserve old value if available, otherwise set to None
                validated_data['email'] = current_record.get('email') if current_record else None
        else:
            validated_data['email'] = None

        # Validate phone (optional) - preserve old value on validation failure
        if 'phone' in record_data and record_data['phone']:
            try:
                validated_data['phone'] = self.validator.validate_phone(record_data['phone'])
            except ValueError as e:
                self.logger.warning(f"Invalid phone for SSN {validated_data['ssn']}: {e}")
                # Preserve old value if available, otherwise set to None
                validated_data['phone'] = current_record.get('phone') if current_record else None
        else:
            validated_data['phone'] = None

        # Validate date of birth (optional) - preserve old value on validation failure
        if 'dob' in record_data and record_data['dob']:
            try:
                validated_data['dob'] = self.validator.validate_date(record_data['dob'])
            except ValueError as e:
                self.logger.warning(f"Invalid dob for SSN {validated_data['ssn']}: {e}")
                # Preserve old value if available, otherwise set to None
                validated_data['dob'] = current_record.get('dob') if current_record else None
        else:
            validated_data['dob'] = None

        # Validate ZIP (optional) - preserve old value on validation failure
        if 'zip' in record_data and record_data['zip']:
            try:
                validated_data['zip'] = self.validator.validate_zip(record_data['zip'])
            except ValueError as e:
                self.logger.warning(f"Invalid zip for SSN {validated_data['ssn']}: {e}")
                # Preserve old value if available, otherwise set to None
                validated_data['zip'] = current_record.get('zip') if current_record else None
        else:
            validated_data['zip'] = None

        # Validate state (optional) - preserve old value on validation failure
        if 'state' in record_data and record_data['state']:
            try:
                validated_data['state'] = self.validator.validate_state(record_data['state'])
            except ValueError as e:
                self.logger.warning(f"Invalid state for SSN {validated_data['ssn']}: {e}")
                # Preserve old value if available, otherwise set to None
                validated_data['state'] = current_record.get('state') if current_record else None
        else:
            validated_data['state'] = None

        # Normalize text fields (strip whitespace)
        text_fields = ['firstname', 'lastname', 'middlename', 'address', 'city']
        for field in text_fields:
            if field in record_data and record_data[field]:
                validated_data[field] = str(record_data[field]).strip()
            else:
                validated_data[field] = None

        return validated_data

    def upsert_record(self, table_name: str, record_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert or update a single record in the database.

        Uses INSERT OR REPLACE to perform UPSERT operation based on unique SSN.

        Args:
            table_name: Name of the table (ssn_1 or ssn_2)
            record_data: Dictionary containing record fields

        Returns:
            Dictionary with operation result:
            - success: bool indicating if operation succeeded
            - record_id: int ID of inserted/updated record
            - ssn: str SSN of the record
            - message: str description of the operation
            - error: str error message (if success is False)
        """
        connection = None
        try:
            # Validate table name
            validate_table_name(table_name)

            # Validate record data
            validated_data = self._validate_record_data(record_data)

            # Get database connection
            connection = get_connection(self.db_path)
            cursor = connection.cursor()

            # Prepare SQL query with parameterization
            sql = f"""
                INSERT OR REPLACE INTO {table_name}
                (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            # Prepare values tuple
            values = (
                validated_data.get('firstname'),
                validated_data.get('lastname'),
                validated_data.get('middlename'),
                validated_data.get('address'),
                validated_data.get('city'),
                validated_data.get('state'),
                validated_data.get('zip'),
                validated_data.get('phone'),
                validated_data['ssn'],
                validated_data.get('dob'),
                validated_data.get('email')
            )

            # Execute query
            cursor.execute(sql, values)
            connection.commit()

            # Get stable record ID by querying with SSN
            cursor.execute(f"SELECT id FROM {table_name} WHERE ssn = ?", (validated_data['ssn'],))
            row = cursor.fetchone()
            record_id = row[0] if row else None

            # Log successful operation
            self.logger.info(f"Successfully upserted record with SSN {validated_data['ssn']} in table {table_name} (ID: {record_id})")

            return {
                'success': True,
                'record_id': record_id,
                'ssn': validated_data['ssn'],
                'message': f"Record successfully upserted in {table_name}"
            }

        except ValueError as e:
            self.logger.error(f"Validation error during upsert: {e}")
            return {
                'success': False,
                'error': f"Validation error: {str(e)}"
            }
        except FileNotFoundError as e:
            self.logger.error(f"Database file not found during upsert: {e}")
            return {
                'success': False,
                'error': f"Database file not found at {self.db_path}. Please initialize the database first."
            }
        except sqlite3.IntegrityError as e:
            self.logger.error(f"Integrity error during upsert in {table_name}: {e}")
            return {
                'success': False,
                'error': f"Database integrity error: {str(e)}"
            }
        except sqlite3.Error as e:
            self.logger.error(f"Database error during upsert in {table_name}: {e}")
            return {
                'success': False,
                'error': f"Database error: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Unexpected error during upsert: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
        finally:
            if connection:
                close_connection(connection)

    def bulk_upsert(self, table_name: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Insert or update multiple records in bulk.

        Processes all records, collecting statistics about successful and failed operations.
        Continues processing even if some records fail validation.

        Args:
            table_name: Name of the table (ssn_1 or ssn_2)
            records: List of dictionaries containing record fields

        Returns:
            Dictionary with operation statistics:
            - total: int total number of records processed
            - successful: int number of successfully inserted/updated records
            - failed: int number of failed records
            - failed_records: list of dictionaries with failed record details
            - error: str error message (if critical error occurred)
        """
        connection = None
        try:
            # Validate table name
            validate_table_name(table_name)

            # Check for empty records list
            if not records or len(records) == 0:
                return {
                    'total': 0,
                    'successful': 0,
                    'failed': 0,
                    'failed_records': []
                }

            # Initialize counters
            successful_count = 0
            failed_count = 0
            failed_records = []
            valid_records = []

            # Validate all records
            for idx, record in enumerate(records):
                try:
                    validated_data = self._validate_record_data(record)
                    valid_records.append(validated_data)
                except (ValueError, Exception) as e:
                    failed_count += 1
                    failed_records.append({
                        'record_index': idx,
                        'ssn': record.get('ssn', 'N/A'),
                        'error': str(e)
                    })
                    self.logger.warning(f"Validation failed for record {idx}: {e}")

            # If no valid records, return early
            if not valid_records:
                self.logger.warning(f"No valid records to insert in {table_name}")
                return {
                    'total': len(records),
                    'successful': 0,
                    'failed': failed_count,
                    'failed_records': failed_records
                }

            # Get database connection
            connection = get_connection(self.db_path)
            cursor = connection.cursor()

            # Prepare SQL query
            sql = f"""
                INSERT OR REPLACE INTO {table_name}
                (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            # Prepare list of value tuples
            values_list = []
            for validated_data in valid_records:
                values = (
                    validated_data.get('firstname'),
                    validated_data.get('lastname'),
                    validated_data.get('middlename'),
                    validated_data.get('address'),
                    validated_data.get('city'),
                    validated_data.get('state'),
                    validated_data.get('zip'),
                    validated_data.get('phone'),
                    validated_data['ssn'],
                    validated_data.get('dob'),
                    validated_data.get('email')
                )
                values_list.append(values)

            # Execute bulk insert
            cursor.executemany(sql, values_list)
            connection.commit()

            successful_count = len(valid_records)

            # Log results
            self.logger.info(f"Bulk upsert in {table_name}: {successful_count} successful, {failed_count} failed out of {len(records)} total")

            return {
                'total': len(records),
                'successful': successful_count,
                'failed': failed_count,
                'failed_records': failed_records
            }

        except FileNotFoundError as e:
            self.logger.error(f"Database file not found during bulk upsert: {e}")
            return {
                'success': False,
                'error': f"Database file not found at {self.db_path}. Please initialize the database first."
            }
        except sqlite3.IntegrityError as e:
            if connection:
                connection.rollback()
            self.logger.error(f"Integrity error during bulk upsert in {table_name}: {e}")
            return {
                'success': False,
                'error': f"Database integrity error: {str(e)}"
            }
        except sqlite3.Error as e:
            if connection:
                connection.rollback()
            self.logger.error(f"Database error during bulk upsert in {table_name}: {e}")
            return {
                'success': False,
                'error': f"Database error: {str(e)}"
            }
        except Exception as e:
            if connection:
                connection.rollback()
            self.logger.error(f"Unexpected error during bulk upsert: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
        finally:
            if connection:
                close_connection(connection)

    def delete_record(self, table_name: str, ssn: str) -> Dict[str, Any]:
        """
        Delete a record from the database by SSN.

        Args:
            table_name: Name of the table (ssn_1 or ssn_2)
            ssn: Social Security Number of the record to delete

        Returns:
            Dictionary with operation result:
            - success: bool indicating if operation succeeded
            - deleted: bool indicating if record was found and deleted
            - ssn: str SSN of the deleted record
            - message: str description of the operation
            - error: str error message (if success is False)
        """
        connection = None
        try:
            # Validate table name
            validate_table_name(table_name)

            # Normalize and validate SSN
            normalized_ssn = self.validator.validate_ssn(ssn)
            if normalized_ssn is None:
                raise ValueError('Invalid SSN')

            # Get database connection
            connection = get_connection(self.db_path)
            cursor = connection.cursor()

            # Prepare SQL query with parameterization
            sql = f"DELETE FROM {table_name} WHERE ssn = ?"

            # Execute query
            cursor.execute(sql, (normalized_ssn,))
            connection.commit()

            # Get number of deleted rows
            rows_deleted = cursor.rowcount

            if rows_deleted > 0:
                self.logger.info(f"Successfully deleted record with SSN {normalized_ssn} from table {table_name}")
                return {
                    'success': True,
                    'deleted': True,
                    'ssn': normalized_ssn,
                    'message': f"Record with SSN {normalized_ssn} successfully deleted from {table_name}"
                }
            else:
                self.logger.info(f"No record found with SSN {normalized_ssn} in table {table_name}")
                return {
                    'success': True,
                    'deleted': False,
                    'ssn': normalized_ssn,
                    'message': 'Record not found'
                }

        except ValueError as e:
            self.logger.error(f"Validation error during delete: {e}")
            return {
                'success': False,
                'error': f"Validation error: {str(e)}"
            }
        except FileNotFoundError as e:
            self.logger.error(f"Database file not found during delete: {e}")
            return {
                'success': False,
                'error': f"Database file not found at {self.db_path}. Please initialize the database first."
            }
        except sqlite3.Error as e:
            if connection:
                connection.rollback()
            self.logger.error(f"Database error during delete in {table_name}: {e}")
            return {
                'success': False,
                'error': f"Database error: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Unexpected error during delete: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
        finally:
            if connection:
                close_connection(connection)

    def get_record(self, table_name: str, ssn: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a record from the database by SSN.

        Args:
            table_name: Name of the table (ssn_1 or ssn_2)
            ssn: Social Security Number of the record to retrieve

        Returns:
            Dictionary containing record data, or None if record not found or SSN is invalid
        """
        connection = None
        try:
            # Validate table name
            validate_table_name(table_name)

            # Normalize and validate SSN
            normalized_ssn = self.validator.validate_ssn(ssn)
            if normalized_ssn is None:
                self.logger.error(f"Invalid SSN for get_record: {ssn}")
                return None

            # Get database connection
            connection = get_connection(self.db_path)
            connection.row_factory = sqlite3.Row
            cursor = connection.cursor()

            # Prepare SQL query with parameterization
            sql = f"SELECT * FROM {table_name} WHERE ssn = ?"

            # Execute query
            cursor.execute(sql, (normalized_ssn,))
            row = cursor.fetchone()

            if row:
                # Convert sqlite3.Row to dictionary
                record_dict = dict(row)
                self.logger.info(f"Retrieved record with SSN {normalized_ssn} from table {table_name}")
                return record_dict
            else:
                self.logger.info(f"No record found with SSN {normalized_ssn} in table {table_name}")
                return None

        except sqlite3.Error as e:
            self.logger.error(f"Database error during get_record in {table_name}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error during get_record: {e}")
            return None
        finally:
            if connection:
                close_connection(connection)

    def update_record(self, table_name: str, ssn: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Partially update an existing record in the database.

        Retrieves current record, merges with update_data, validates, and updates.

        Args:
            table_name: Name of the table (ssn_1 or ssn_2)
            ssn: Social Security Number of the record to update
            update_data: Dictionary containing fields to update

        Returns:
            Dictionary with operation result including:
            - success: bool indicating if operation succeeded
            - record_id: database record ID
            - ssn: normalized SSN
            - message: success message
            - updated_fields: list of field names that were updated
            - updated_values: dict containing the validated values that were written to database
        """
        connection = None
        try:
            # Validate table name
            validate_table_name(table_name)

            # Normalize and validate SSN
            normalized_ssn = self.validator.validate_ssn(ssn)
            if normalized_ssn is None:
                raise ValueError('Invalid SSN')

            # Get current record
            current_record = self.get_record(table_name, normalized_ssn)

            if not current_record:
                return {
                    'success': False,
                    'error': f"Record with SSN {normalized_ssn} not found in {table_name}"
                }

            # Merge current data with update data (priority to new data)
            merged_data = {**current_record, **update_data}
            merged_data['ssn'] = normalized_ssn  # Ensure SSN is preserved and normalized

            # Define allowlist of updatable fields
            # IMPORTANT: This includes firstname, lastname, middlename which should be controlled
            # by the calling code. For enrichment operations, the caller (enrichment.py) restricts
            # updates to SAFE_UPDATE_FIELDS = {'dob', 'address', 'city', 'state', 'zip', 'phone', 'email'}
            # to prevent identity field modifications.
            updatable_fields = {'firstname', 'lastname', 'middlename', 'address', 'city', 'state', 'zip', 'phone', 'dob', 'email'}

            # Filter update_data to only include updatable fields
            filtered_update_data = {k: v for k, v in update_data.items() if k in updatable_fields}

            # Check if there are any valid fields to update
            if not filtered_update_data:
                return {
                    'success': False,
                    'error': 'No updatable fields provided'
                }

            # Validate merged data, passing current_record to preserve old values on validation failure
            validated_data = self._validate_record_data(merged_data, current_record=current_record)

            # Get database connection
            connection = get_connection(self.db_path)
            cursor = connection.cursor()

            # Build dynamic UPDATE query for fields in filtered_update_data
            update_fields = []
            update_values = []

            field_mapping = {
                'firstname': validated_data.get('firstname'),
                'lastname': validated_data.get('lastname'),
                'middlename': validated_data.get('middlename'),
                'address': validated_data.get('address'),
                'city': validated_data.get('city'),
                'state': validated_data.get('state'),
                'zip': validated_data.get('zip'),
                'phone': validated_data.get('phone'),
                'dob': validated_data.get('dob'),
                'email': validated_data.get('email')
            }

            for field, value in field_mapping.items():
                if field in filtered_update_data:
                    update_fields.append(f"{field} = ?")
                    update_values.append(value)

            # Add SSN to WHERE clause
            update_values.append(normalized_ssn)

            # Prepare SQL query
            sql = f"""
                UPDATE {table_name}
                SET {', '.join(update_fields)}
                WHERE ssn = ?
            """

            # Execute query
            cursor.execute(sql, update_values)
            connection.commit()

            # Capture updated values (validated/normalized versions)
            updated_values = {}
            for field in filtered_update_data.keys():
                if field in field_mapping:
                    updated_values[field] = field_mapping[field]

            # Log updated fields
            updated_fields_str = ', '.join(filtered_update_data.keys())
            self.logger.info(f"Successfully updated record with SSN {normalized_ssn} in table {table_name} (fields: {updated_fields_str})")

            return {
                'success': True,
                'record_id': current_record.get('id'),
                'ssn': normalized_ssn,
                'message': f"Record successfully updated in {table_name}",
                'updated_fields': list(filtered_update_data.keys()),
                'updated_values': updated_values
            }

        except ValueError as e:
            self.logger.error(f"Validation error during update: {e}")
            return {
                'success': False,
                'error': f"Validation error: {str(e)}"
            }
        except FileNotFoundError as e:
            self.logger.error(f"Database file not found during update: {e}")
            return {
                'success': False,
                'error': f"Database file not found at {self.db_path}. Please initialize the database first."
            }
        except sqlite3.Error as e:
            if connection:
                connection.rollback()
            self.logger.error(f"Database error during update in {table_name}: {e}")
            return {
                'success': False,
                'error': f"Database error: {str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Unexpected error during update: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
        finally:
            if connection:
                close_connection(connection)

    def record_exists(self, table_name: str, ssn: str) -> bool:
        """
        Check if a record exists in the database.

        Args:
            table_name: Name of the table (ssn_1 or ssn_2)
            ssn: Social Security Number to check

        Returns:
            True if record exists, False otherwise
        """
        try:
            record = self.get_record(table_name, ssn)
            return record is not None
        except Exception as e:
            self.logger.error(f"Error checking record existence: {e}")
            return False


# Convenience functions for easy API access

def upsert_record(table_name: str, record_data: Dict[str, Any], db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to add/update a single record.

    Args:
        table_name: Name of the table (ssn_1 or ssn_2)
        record_data: Dictionary containing record fields
        db_path: Optional path to database file

    Returns:
        Dictionary with operation result
    """
    manager = DataManager(db_path)
    return manager.upsert_record(table_name, record_data)


def bulk_upsert(table_name: str, records: List[Dict[str, Any]], db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function for bulk add/update operations.

    Args:
        table_name: Name of the table (ssn_1 or ssn_2)
        records: List of dictionaries containing record fields
        db_path: Optional path to database file

    Returns:
        Dictionary with operation statistics
    """
    manager = DataManager(db_path)
    return manager.bulk_upsert(table_name, records)


def delete_record(table_name: str, ssn: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function to delete a record.

    Args:
        table_name: Name of the table (ssn_1 or ssn_2)
        ssn: Social Security Number of record to delete
        db_path: Optional path to database file

    Returns:
        Dictionary with operation result
    """
    manager = DataManager(db_path)
    return manager.delete_record(table_name, ssn)


def update_record(table_name: str, ssn: str, update_data: Dict[str, Any], db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Convenience function for partial record update.

    Args:
        table_name: Name of the table (ssn_1 or ssn_2)
        ssn: Social Security Number of record to update
        update_data: Dictionary containing fields to update
        db_path: Optional path to database file

    Returns:
        Dictionary with operation result
    """
    manager = DataManager(db_path)
    return manager.update_record(table_name, ssn, update_data)


# Demo/testing code
if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("Data Manager Demo")
    print("=" * 80)

    try:
        # Create DataManager instance
        manager = DataManager()

        # 1. Add new record
        print("\n1. Adding new record...")
        new_record = {
            'firstname': 'John',
            'lastname': 'Doe',
            'address': '123 Main St',
            'city': 'Springfield',
            'state': 'IL',
            'zip': '62701',
            'phone': '217-555-1234',
            'ssn': '123-45-6789',
            'dob': '1990-01-15',
            'email': 'john.doe@example.com'
        }
        result = manager.upsert_record('ssn_1', new_record)
        print(f"Result: {result}")

        # 2. Update existing record
        print("\n2. Updating existing record (changing email and phone)...")
        updated_record = {
            'firstname': 'John',
            'lastname': 'Doe',
            'address': '123 Main St',
            'city': 'Springfield',
            'state': 'IL',
            'zip': '62701',
            'phone': '217-555-9999',
            'ssn': '123-45-6789',
            'dob': '1990-01-15',
            'email': 'john.updated@example.com'
        }
        result = manager.upsert_record('ssn_1', updated_record)
        print(f"Result: {result}")

        # 3. Bulk insert
        print("\n3. Bulk inserting multiple records...")
        bulk_records = [
            {
                'firstname': 'Jane',
                'lastname': 'Smith',
                'address': '456 Oak Ave',
                'city': 'Chicago',
                'state': 'IL',
                'zip': '60601',
                'phone': '312-555-5678',
                'ssn': '987-65-4321',
                'dob': '1985-05-20',
                'email': 'jane.smith@example.com'
            },
            {
                'firstname': 'Bob',
                'lastname': 'Johnson',
                'address': '789 Pine Rd',
                'city': 'Peoria',
                'state': 'IL',
                'zip': '61602',
                'phone': '309-555-8765',
                'ssn': '555-12-3456',
                'dob': '1992-11-30',
                'email': 'bob.johnson@example.com'
            },
            {
                'firstname': 'Invalid',
                'lastname': 'Record',
                'ssn': 'invalid-ssn',  # This will fail validation
                'email': 'test@example.com'
            }
        ]
        result = manager.bulk_upsert('ssn_1', bulk_records)
        print(f"Statistics: Total={result['total']}, Successful={result['successful']}, Failed={result['failed']}")
        if result['failed_records']:
            print(f"Failed records: {result['failed_records']}")

        # 4. Get record
        print("\n4. Retrieving record by SSN...")
        record = manager.get_record('ssn_1', '123-45-6789')
        if record:
            print(f"Retrieved record: {record}")
        else:
            print("Record not found")

        # 5. Partial update
        print("\n5. Partial update (changing only email)...")
        result = manager.update_record('ssn_1', '123-45-6789', {'email': 'john.partial@example.com'})
        print(f"Result: {result}")

        # Verify partial update
        print("\n   Verifying partial update...")
        record = manager.get_record('ssn_1', '123-45-6789')
        if record:
            print(f"   Updated email: {record.get('email')}")

        # 6. Delete record
        print("\n6. Deleting record...")
        result = manager.delete_record('ssn_1', '987-65-4321')
        print(f"Result: {result}")

        # Verify deletion
        print("\n   Verifying deletion...")
        record = manager.get_record('ssn_1', '987-65-4321')
        if record:
            print("   ERROR: Record still exists!")
        else:
            print("   Record successfully deleted")

        # 7. Try to delete non-existent record
        print("\n7. Attempting to delete non-existent record...")
        result = manager.delete_record('ssn_1', '000-00-0000')
        print(f"Result: {result}")

        print("\n" + "=" * 80)
        print("Demo completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
