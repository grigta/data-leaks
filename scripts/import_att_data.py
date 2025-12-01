#!/usr/bin/env python3
"""
Import ATT data from CSV files into ssn_3 table.

This script:
1. Loads decryption mappings for DOB and SSN
2. Parses Name into firstname/lastname
3. Parses Address into address, city, state, zip
4. Imports data into ssn_3 table with proper indexes
"""

import csv
import sqlite3
import re
import sys
import logging
from pathlib import Path
from collections import defaultdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
DB_PATH = '/root/soft/data/ssn_database.db'
ATT_CSV = '/root/soft/newdata/att_final.csv'
DOB_MAPPING_CSV = '/root/soft/newdata/dob_mapping.csv'
SSN_MAPPING_CSV = '/root/soft/newdata/ssn_mapping.csv'

# US State abbreviations for parsing
US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
}

# State abbreviation mapping for common shortened forms
STATE_ABBREV = {
    'FMT': 'CA',  # Fremont
    'FRS': 'CA',  # Fresno
    'SD': 'CA',   # San Diego
    'CHGO': 'IL', # Chicago
    'TWN HRT': 'CA', # Twain Harte
}


def load_dob_mapping(csv_path):
    """Load DOB decryption mapping from CSV."""
    mapping = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                encrypted = row.get('encrypted_value', '').strip()
                decrypted = row.get('decrypted_value', '').strip()
                if encrypted and decrypted:
                    mapping[encrypted] = decrypted
        logger.info(f"Loaded {len(mapping)} DOB mappings")
    except Exception as e:
        logger.error(f"Error loading DOB mapping: {e}")
    return mapping


def load_ssn_mapping(csv_path):
    """Load SSN decryption mapping from CSV."""
    mapping = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                encrypted = row.get('Encrypted Value', '').strip()
                ssn = row.get('SSN', '').strip()
                if encrypted and ssn:
                    mapping[encrypted] = ssn
        logger.info(f"Loaded {len(mapping)} SSN mappings")
    except Exception as e:
        logger.error(f"Error loading SSN mapping: {e}")
    return mapping


def parse_name(full_name):
    """
    Parse full name into firstname and lastname.

    Examples:
    - "RONALD DYMOND" -> ("RONALD", "DYMOND")
    - "DING MA" -> ("DING", "MA")
    - "CINDY. GUITRON" -> ("CINDY", "GUITRON")
    - "*COREY RUSH" -> ("COREY", "RUSH")
    """
    if not full_name:
        return '', ''

    # Remove leading * or .
    name = full_name.strip().lstrip('*').strip()

    # Remove trailing/internal dots
    name = re.sub(r'\.+', '', name)

    # Split by whitespace
    parts = name.split()

    if len(parts) == 0:
        return '', ''
    elif len(parts) == 1:
        return parts[0], ''
    else:
        # First part is firstname, last part is lastname
        return parts[0], parts[-1]


def parse_address(full_address):
    """
    Parse address into components: address, city, state, zip.

    Examples:
    - "170 SUMTER DR, MARIETTA GA" -> ("170 SUMTER DR", "MARIETTA", "GA", "")
    - "APT 212, 39800 FREMONT BLVD, FREMONT CA" -> ("APT 212, 39800 FREMONT BLVD", "FREMONT", "CA", "")
    - "915 W 32ND, CHGO IL 60608" -> ("915 W 32ND", "CHICAGO", "IL", "60608")
    - "3746 W PERSIMMON LN, FRS CA 93711" -> ("3746 W PERSIMMON LN", "FRESNO", "CA", "93711")
    """
    if not full_address:
        return '', '', '', ''

    address = full_address.strip()
    city = ''
    state = ''
    zip_code = ''
    street = ''

    # Find the last comma - typically separates street from city/state/zip
    last_comma = address.rfind(',')

    if last_comma > 0:
        street = address[:last_comma].strip()
        city_state_zip = address[last_comma + 1:].strip()
    else:
        # No comma - try to parse as is
        city_state_zip = address
        street = ''

    # Parse city, state, zip from the end
    # Pattern: CITY STATE ZIP or CITY STATE or just CITY

    # Try to extract ZIP code (5 digits at the end)
    zip_match = re.search(r'\s(\d{5})(?:-\d{4})?$', city_state_zip)
    if zip_match:
        zip_code = zip_match.group(1)
        city_state_zip = city_state_zip[:zip_match.start()].strip()

    # Split remaining into parts
    parts = city_state_zip.split()

    if len(parts) >= 2:
        # Check if last part is a state abbreviation
        potential_state = parts[-1].upper()
        if potential_state in US_STATES:
            state = potential_state
            city = ' '.join(parts[:-1]).upper()
        elif potential_state in STATE_ABBREV:
            state = STATE_ABBREV[potential_state]
            city = ' '.join(parts[:-1]).upper()
        else:
            # Maybe state is combined, like "GA30301"
            state_match = re.match(r'([A-Z]{2})(\d+)?', potential_state)
            if state_match and state_match.group(1) in US_STATES:
                state = state_match.group(1)
                if state_match.group(2) and not zip_code:
                    zip_code = state_match.group(2)
                city = ' '.join(parts[:-1]).upper()
            else:
                city = city_state_zip.upper()
    elif len(parts) == 1:
        # Just city or state
        if parts[0].upper() in US_STATES:
            state = parts[0].upper()
        else:
            city = parts[0].upper()

    # If no street extracted, use entire address as street
    if not street and city:
        street = ''
    elif not street:
        street = address

    return street, city, state, zip_code


def normalize_ssn(ssn, ssn_mapping):
    """
    Normalize and decrypt SSN if needed.

    Returns SSN in format XXX-XX-XXXX or empty string.
    """
    if not ssn:
        return ''

    ssn = ssn.strip()

    # Check if encrypted (starts with *)
    if ssn.startswith('*'):
        decrypted = ssn_mapping.get(ssn)
        if decrypted:
            ssn = decrypted
        else:
            return ''  # Cannot decrypt

    # Remove non-digits
    digits = re.sub(r'\D', '', ssn)

    if len(digits) != 9:
        return ''

    # Format as XXX-XX-XXXX
    return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"


def normalize_dob(dob, dob_mapping):
    """
    Normalize and decrypt DOB if needed.

    Returns DOB in format YYYYMMDD or empty string.
    """
    if not dob:
        return ''

    dob = dob.strip()

    # Check if encrypted (starts with *)
    if dob.startswith('*'):
        decrypted = dob_mapping.get(dob)
        if decrypted:
            dob = decrypted
        else:
            return ''  # Cannot decrypt

    # Parse date in format YYYY-MM-DD
    date_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', dob)
    if date_match:
        return f"{date_match.group(1)}{date_match.group(2)}{date_match.group(3)}"

    # Try other formats
    date_match = re.match(r'(\d{2})/(\d{2})/(\d{4})', dob)
    if date_match:
        return f"{date_match.group(3)}{date_match.group(1)}{date_match.group(2)}"

    return dob


def normalize_phone(phone):
    """
    Normalize phone number to 10 digits.
    """
    if not phone:
        return ''

    digits = re.sub(r'\D', '', str(phone))

    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]

    if len(digits) == 10:
        return digits

    return ''


def create_table_and_indexes(conn):
    """Create ssn_3 table and indexes if they don't exist."""
    cursor = conn.cursor()

    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ssn_3 (
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
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ssn_3_name_address
        ON ssn_3(firstname COLLATE NOCASE, lastname COLLATE NOCASE, address COLLATE NOCASE)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ssn_3_name_zip
        ON ssn_3(firstname COLLATE NOCASE, lastname COLLATE NOCASE, zip)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ssn_3_ssn
        ON ssn_3(ssn)
    """)

    # Additional indexes for phone and email searches
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ssn_3_phone
        ON ssn_3(phone)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ssn_3_email
        ON ssn_3(email COLLATE NOCASE)
    """)

    conn.commit()
    logger.info("Table ssn_3 and indexes created")


def import_data(conn, dob_mapping, ssn_mapping, batch_size=10000):
    """Import data from ATT CSV into ssn_3 table."""
    cursor = conn.cursor()

    # Track statistics
    stats = {
        'total': 0,
        'imported': 0,
        'skipped_no_ssn': 0,
        'skipped_duplicate': 0,
        'errors': 0
    }

    # Track unique SSNs to avoid duplicates within import
    seen_ssns = set()

    # Check existing SSNs in database
    cursor.execute("SELECT ssn FROM ssn_3")
    for row in cursor.fetchall():
        seen_ssns.add(row[0])
    logger.info(f"Found {len(seen_ssns)} existing records in ssn_3")

    batch = []

    with open(ATT_CSV, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)

        for row in reader:
            stats['total'] += 1

            if stats['total'] % 100000 == 0:
                logger.info(f"Processed {stats['total']:,} rows, imported {stats['imported']:,}")

            try:
                # Parse SSN
                ssn = normalize_ssn(row.get('SSN', ''), ssn_mapping)
                if not ssn:
                    stats['skipped_no_ssn'] += 1
                    continue

                # Check for duplicates
                if ssn in seen_ssns:
                    stats['skipped_duplicate'] += 1
                    continue

                seen_ssns.add(ssn)

                # Parse name
                firstname, lastname = parse_name(row.get('Name', ''))

                # Parse address
                address, city, state, zip_code = parse_address(row.get('Address', ''))

                # Parse DOB
                dob = normalize_dob(row.get('DOB', ''), dob_mapping)

                # Parse phones (use Phone1 as primary)
                phone = normalize_phone(row.get('Phone1', ''))

                # Email
                email = row.get('Email', '').strip().upper()

                # Add to batch
                batch.append((
                    firstname,
                    lastname,
                    '',  # middlename
                    address,
                    city,
                    state,
                    zip_code,
                    phone,
                    ssn,
                    dob,
                    email
                ))

                stats['imported'] += 1

                # Insert batch
                if len(batch) >= batch_size:
                    cursor.executemany("""
                        INSERT INTO ssn_3
                        (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, batch)
                    conn.commit()
                    batch = []

            except Exception as e:
                stats['errors'] += 1
                if stats['errors'] <= 10:
                    logger.error(f"Error processing row {stats['total']}: {e}")

    # Insert remaining batch
    if batch:
        cursor.executemany("""
            INSERT INTO ssn_3
            (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)
        conn.commit()

    return stats


def main():
    logger.info("Starting ATT data import")

    # Load mappings
    logger.info("Loading decryption mappings...")
    dob_mapping = load_dob_mapping(DOB_MAPPING_CSV)
    ssn_mapping = load_ssn_mapping(SSN_MAPPING_CSV)

    # Connect to database
    logger.info(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)

    # Enable WAL mode for better performance
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA cache_size = -64000")  # 64MB cache

    try:
        # Create table and indexes
        create_table_and_indexes(conn)

        # Import data
        logger.info("Starting data import...")
        stats = import_data(conn, dob_mapping, ssn_mapping)

        # Print statistics
        logger.info("=" * 50)
        logger.info("Import completed!")
        logger.info(f"Total rows processed: {stats['total']:,}")
        logger.info(f"Records imported: {stats['imported']:,}")
        logger.info(f"Skipped (no SSN): {stats['skipped_no_ssn']:,}")
        logger.info(f"Skipped (duplicate): {stats['skipped_duplicate']:,}")
        logger.info(f"Errors: {stats['errors']:,}")
        logger.info("=" * 50)

        # Verify count
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ssn_3")
        count = cursor.fetchone()[0]
        logger.info(f"Total records in ssn_3: {count:,}")

    finally:
        conn.close()


if __name__ == '__main__':
    main()
