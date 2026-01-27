"""
Data Validator Module

This module provides validation and normalization for various data fields
used in the SSN database system.
"""

import re
from typing import Optional


class DataValidator:
    """
    Validates and normalizes data fields for database records.

    Provides validation methods for:
    - SSN (Social Security Number)
    - Email addresses
    - Phone numbers
    - Dates
    - ZIP codes
    - State codes
    """

    def __init__(self):
        """Initialize the DataValidator."""
        # SSN pattern: accepts with or without dashes or spaces
        self.ssn_pattern = re.compile(r'^\d{3}[-\s]?\d{2}[-\s]?\d{4}$')

        # Email pattern: basic email validation
        self.email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

        # Phone pattern: accepts various formats
        self.phone_pattern = re.compile(r'^[\d\s\-\(\)\.+]+$')

        # ZIP code pattern: 5 digits or 5+4 format
        self.zip_pattern = re.compile(r'^\d{5}(-\d{4})?$')

        # Date pattern: various formats (YYYY-MM-DD, MM/DD/YYYY, etc.)
        self.date_patterns = [
            re.compile(r'^\d{4}-\d{2}-\d{2}$'),  # YYYY-MM-DD
            re.compile(r'^\d{2}/\d{2}/\d{4}$'),  # MM/DD/YYYY
            re.compile(r'^\d{2}-\d{2}-\d{4}$'),  # MM-DD-YYYY
        ]

    def validate_ssn(self, ssn: str) -> Optional[str]:
        """
        Validate and normalize SSN.

        Args:
            ssn: SSN string to validate

        Returns:
            Normalized SSN in XXX-XX-XXXX format, or None if invalid
        """
        if not ssn or not isinstance(ssn, str):
            return None

        # Remove whitespace
        ssn = ssn.strip()

        # Check pattern
        if not self.ssn_pattern.match(ssn):
            return None

        # Remove dashes and spaces for normalization
        digits = ssn.replace('-', '').replace(' ', '')

        # Validate it's 9 digits
        if len(digits) != 9 or not digits.isdigit():
            return None

        # Return normalized format
        return f"{digits[0:3]}-{digits[3:5]}-{digits[5:9]}"

    def validate_email(self, email: str) -> Optional[str]:
        """
        Validate and normalize email address.

        Args:
            email: Email string to validate

        Returns:
            Normalized email in lowercase, or None if invalid
        """
        if not email or not isinstance(email, str):
            return None

        # Remove whitespace and convert to lowercase
        email = email.strip().lower()

        # Check pattern
        if not self.email_pattern.match(email):
            return None

        return email

    def validate_phone(self, phone: str) -> Optional[str]:
        """
        Validate phone number.

        Args:
            phone: Phone string to validate

        Returns:
            Phone number as-is if valid, or None if invalid
        """
        if not phone or not isinstance(phone, str):
            return None

        # Remove whitespace
        phone = phone.strip()

        # Check pattern (very permissive)
        if not self.phone_pattern.match(phone):
            return None

        # Extract only digits to check length
        digits = re.sub(r'\D', '', phone)
        if len(digits) < 10:  # Minimum 10 digits for valid phone
            return None

        return phone

    def validate_date(self, date: str) -> Optional[str]:
        """
        Validate date string.

        Args:
            date: Date string to validate

        Returns:
            Date string as-is if valid, or None if invalid
        """
        if not date or not isinstance(date, str):
            return None

        # Remove whitespace
        date = date.strip()

        # Check against known patterns
        for pattern in self.date_patterns:
            if pattern.match(date):
                return date

        return None

    def validate_zip(self, zip_code: str) -> Optional[str]:
        """
        Validate ZIP code.

        Args:
            zip_code: ZIP code string to validate

        Returns:
            ZIP code as-is if valid, or None if invalid
        """
        if not zip_code or not isinstance(zip_code, str):
            return None

        # Remove whitespace
        zip_code = zip_code.strip()

        # Check pattern
        if not self.zip_pattern.match(zip_code):
            return None

        return zip_code

    def validate_state(self, state: str) -> Optional[str]:
        """
        Validate and normalize US state code.

        Args:
            state: State code to validate

        Returns:
            State code in uppercase if valid, or None if invalid
        """
        if not state or not isinstance(state, str):
            return None

        # Convert to uppercase and remove whitespace
        state = state.strip().upper()

        # Check it's exactly 2 letters
        if len(state) != 2 or not state.isalpha():
            return None

        # List of valid US state codes
        valid_states = {
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
            'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
            'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
            'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
            'DC', 'AS', 'GU', 'MP', 'PR', 'VI'  # Territories
        }

        if state not in valid_states:
            return None

        return state
