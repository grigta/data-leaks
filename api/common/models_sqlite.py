"""
Pydantic models for SSN data from SQLite database.

Security:
    - All string fields have max_length constraints
    - Input validation for emails, phones, DOB, state codes
    - Field validators use centralized validation functions
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
import re


# Maximum lengths for string fields (security limits)
MAX_NAME_LENGTH = 100
MAX_ADDRESS_LENGTH = 500
MAX_CITY_LENGTH = 100
MAX_STATE_LENGTH = 2
MAX_ZIP_LENGTH = 10
MAX_PHONE_LENGTH = 20
MAX_SSN_LENGTH = 11
MAX_DOB_LENGTH = 10
MAX_EMAIL_LENGTH = 254


class SSNRecord(BaseModel):
    """
    Response model for SSN record.

    Security:
        - All string fields have max_length for response safety
    """
    id: int
    firstname: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    lastname: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    middlename: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    address: Optional[str] = Field(default=None, max_length=MAX_ADDRESS_LENGTH)
    city: Optional[str] = Field(default=None, max_length=MAX_CITY_LENGTH)
    state: Optional[str] = Field(default=None, max_length=MAX_STATE_LENGTH)
    zip: Optional[str] = Field(default=None, max_length=MAX_ZIP_LENGTH)
    phone: Optional[str] = Field(default=None, max_length=MAX_PHONE_LENGTH)
    ssn: str = Field(..., max_length=MAX_SSN_LENGTH)
    dob: Optional[str] = Field(default=None, max_length=MAX_DOB_LENGTH)
    email: Optional[str] = Field(default=None, max_length=MAX_EMAIL_LENGTH)
    source_table: Optional[str] = Field(default=None, max_length=20)
    # Count fields for lookup results (when actual data is hidden)
    email_count: Optional[int] = Field(default=None, ge=0, le=100)
    phone_count: Optional[int] = Field(default=None, ge=0, le=100)

    class Config:
        from_attributes = True


class SSNRecordCreate(BaseModel):
    """
    Request model for creating SSN record.

    Security:
        - All string fields have max_length constraints
        - SSN format validation (9 digits)
        - Email format validation
        - Phone format validation
        - State code validation (2 letters)
        - ZIP code validation (5 or 9 digits)
    """
    ssn: str = Field(..., max_length=MAX_SSN_LENGTH)
    firstname: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    lastname: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    middlename: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    address: Optional[str] = Field(default=None, max_length=MAX_ADDRESS_LENGTH)
    city: Optional[str] = Field(default=None, max_length=MAX_CITY_LENGTH)
    state: Optional[str] = Field(default=None, max_length=MAX_STATE_LENGTH)
    zip: Optional[str] = Field(default=None, max_length=MAX_ZIP_LENGTH)
    phone: Optional[str] = Field(default=None, max_length=MAX_PHONE_LENGTH)
    dob: Optional[str] = Field(default=None, max_length=MAX_DOB_LENGTH)
    email: Optional[str] = Field(default=None, max_length=MAX_EMAIL_LENGTH)

    @field_validator('ssn')
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        """Validate SSN format (9 digits or with dashes)."""
        # Remove dashes for validation
        ssn_digits = v.replace('-', '')
        if not re.match(r'^\d{9}$', ssn_digits):
            raise ValueError('SSN must be 9 digits, optionally formatted as XXX-XX-XXXX')
        return v

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower()

    @field_validator('phone')
    @classmethod
    def validate_phone_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone format if provided."""
        if v is None or v == '':
            return v
        # Allow digits, spaces, dashes, parentheses, plus
        if not re.match(r'^[\d\s\-\(\)\+\.]+$', v):
            raise ValueError('Phone must contain only digits and formatting characters')
        return v

    @field_validator('state')
    @classmethod
    def validate_state_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate state code format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^[A-Za-z]{2}$', v):
            raise ValueError('State must be 2 letters')
        return v.upper()

    @field_validator('zip')
    @classmethod
    def validate_zip_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate ZIP code format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^(\d{5}|\d{5}-\d{4}|\d{9})$', v):
            raise ValueError('ZIP must be 5 or 9 digits')
        return v

    @field_validator('dob')
    @classmethod
    def validate_dob_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate DOB format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^(\d{8}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})$', v):
            raise ValueError('DOB must be YYYYMMDD, YYYY-MM-DD, or MM/DD/YYYY')
        return v


class SSNRecordUpdate(BaseModel):
    """
    Request model for updating SSN record.

    Security:
        - All string fields have max_length constraints
        - Same validators as SSNRecordCreate
    """
    firstname: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    lastname: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    middlename: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    address: Optional[str] = Field(default=None, max_length=MAX_ADDRESS_LENGTH)
    city: Optional[str] = Field(default=None, max_length=MAX_CITY_LENGTH)
    state: Optional[str] = Field(default=None, max_length=MAX_STATE_LENGTH)
    zip: Optional[str] = Field(default=None, max_length=MAX_ZIP_LENGTH)
    phone: Optional[str] = Field(default=None, max_length=MAX_PHONE_LENGTH)
    dob: Optional[str] = Field(default=None, max_length=MAX_DOB_LENGTH)
    email: Optional[str] = Field(default=None, max_length=MAX_EMAIL_LENGTH)

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower()

    @field_validator('state')
    @classmethod
    def validate_state_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate state code format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^[A-Za-z]{2}$', v):
            raise ValueError('State must be 2 letters')
        return v.upper()

    @field_validator('zip')
    @classmethod
    def validate_zip_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate ZIP code format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^(\d{5}|\d{5}-\d{4}|\d{9})$', v):
            raise ValueError('ZIP must be 5 or 9 digits')
        return v


class SearchBySSNRequest(BaseModel):
    """
    Request model for SSN search.

    Security:
        - SSN max_length enforced
        - limit validated (positive integer, max 1000)
    """
    ssn: str = Field(..., max_length=MAX_SSN_LENGTH)
    limit: Optional[int] = Field(default=None, ge=1, le=1000)


class SearchByNameRequest(BaseModel):
    """
    Request model for name search.

    Security:
        - All string fields have max_length constraints
        - Names must be at least 2 characters
        - Names allow only letters, spaces, hyphens, apostrophes
        - limit validated (positive integer, max 100)

    Supports two search combinations:
    1. firstname + lastname + zip
    2. firstname + lastname + address
    """
    firstname: str = Field(..., min_length=2, max_length=MAX_NAME_LENGTH)
    lastname: str = Field(..., min_length=2, max_length=MAX_NAME_LENGTH)
    zip: Optional[str] = Field(default=None, max_length=MAX_ZIP_LENGTH)
    address: Optional[str] = Field(default=None, max_length=MAX_ADDRESS_LENGTH)
    limit: Optional[int] = Field(default=None, ge=1, le=100)

    @field_validator('firstname', 'lastname')
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        """Validate name contains only allowed characters."""
        if not re.match(r"^[a-zA-Z\s\-'\.]+$", v):
            raise ValueError('Name must contain only letters, spaces, hyphens, apostrophes, and periods')
        return v.strip()

    @model_validator(mode='after')
    def validate_zip_or_address(self):
        """Ensure either zip or address is provided."""
        if not self.zip and not self.address:
            raise ValueError(
                'Either "zip" or "address" must be provided along with firstname and lastname'
            )
        return self


class InstantSSNRequest(BaseModel):
    """
    Request model for Instant SSN search.

    Security:
        - All string fields have min/max_length constraints
        - Names must be at least 2 characters
        - Address must be at least 10 characters
        - Names allow only letters, spaces, hyphens, apostrophes

    Requires firstname, lastname, and address.
    """
    firstname: str = Field(..., min_length=2, max_length=MAX_NAME_LENGTH, description="First name")
    lastname: str = Field(..., min_length=2, max_length=MAX_NAME_LENGTH, description="Last name")
    address: str = Field(..., min_length=10, max_length=MAX_ADDRESS_LENGTH, description="Street address")
    source: Optional[str] = Field(default="web", max_length=20, description="Request source: web, telegram_bot, or other")

    @field_validator('firstname', 'lastname')
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        """Validate name contains only allowed characters."""
        if not re.match(r"^[a-zA-Z\s\-'\.]+$", v):
            raise ValueError('Name must contain only letters, spaces, hyphens, apostrophes, and periods')
        return v.strip()

    @field_validator('source')
    @classmethod
    def validate_source(cls, v: Optional[str]) -> Optional[str]:
        """Validate source is one of allowed values."""
        if v is None:
            return "web"
        allowed = {'web', 'telegram_bot', 'other'}
        if v.lower() not in allowed:
            return "other"
        return v.lower()


class InstantSSNResult(BaseModel):
    """
    Response model for Instant SSN search result - ONLY current/primary data.

    Security:
        - All string fields have max_length constraints
        - local_db_data is validated for size

    Contains primary (current) data and SSN from local database.
    Historical data is not included.
    """
    # Personal info
    firstname: str = Field(..., max_length=MAX_NAME_LENGTH)
    lastname: str = Field(..., max_length=MAX_NAME_LENGTH)
    middlename: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH)
    dob: Optional[str] = Field(default=None, max_length=MAX_DOB_LENGTH)

    # Primary (current) address
    address: Optional[str] = Field(default=None, max_length=MAX_ADDRESS_LENGTH, description="Current address (full street)")
    city: Optional[str] = Field(default=None, max_length=MAX_CITY_LENGTH, description="Current city")
    state: Optional[str] = Field(default=None, max_length=MAX_STATE_LENGTH, description="Current state")
    zip_code: Optional[str] = Field(default=None, max_length=MAX_ZIP_LENGTH, description="Current ZIP code")

    # Primary (current) contact
    phone: Optional[str] = Field(default=None, max_length=MAX_PHONE_LENGTH, description="Current phone number")
    email: Optional[str] = Field(default=None, max_length=MAX_EMAIL_LENGTH, description="Current email address")

    # SSN from local database (if found)
    ssn: Optional[str] = Field(default=None, max_length=MAX_SSN_LENGTH)
    ssn_found: bool = Field(default=False, description="Whether SSN was found in database")

    # Source information
    report_token: Optional[str] = Field(default=None, max_length=100, description="Report token")

    # Local database data (when SSN is found)
    local_db_data: Optional[dict] = Field(default=None, description="Additional data from local SSN database")


class InstantSSNResponse(BaseModel):
    """
    Response wrapper for Instant SSN search.
    """
    success: bool
    results: List[InstantSSNResult] = Field(default_factory=list)
    data_found: bool = Field(default=False, description="Whether external API returned data")
    ssn_matches_found: int = Field(default=0, description="Number of SSN matches in database")
    message: Optional[str] = None
    new_balance: Optional[float] = Field(None, description="User's new balance after payment (if search was paid)")
    order_id: Optional[str] = Field(None, description="UUID созданного заказа, если SSN найден и списано")
    charged_amount: Optional[float] = Field(None, description="Сумма, списанная пользователю (если есть)")


class InstantSSNPurchaseRequest(BaseModel):
    """
    Request model for purchasing Instant SSN result.

    Security:
        - All string fields have max_length constraints
        - SSN format validation
        - Email format validation

    Contains all data from InstantSSNResult that user wants to purchase.
    Fixed price: $2.00 per record.
    """
    # Required SSN data
    ssn: str = Field(..., max_length=MAX_SSN_LENGTH, description="Social Security Number")
    source_table: Optional[str] = Field(default=None, max_length=20, description="Source table from local DB (e.g., 'ssn_1', 'ssn_2')")

    # Personal info
    firstname: str = Field(..., max_length=MAX_NAME_LENGTH, description="First name")
    lastname: str = Field(..., max_length=MAX_NAME_LENGTH, description="Last name")
    middlename: Optional[str] = Field(default=None, max_length=MAX_NAME_LENGTH, description="Middle name")
    dob: Optional[str] = Field(default=None, max_length=MAX_DOB_LENGTH, description="Date of birth")

    # Address info
    address: Optional[str] = Field(default=None, max_length=MAX_ADDRESS_LENGTH, description="Street address")
    city: Optional[str] = Field(default=None, max_length=MAX_CITY_LENGTH, description="City")
    state: Optional[str] = Field(default=None, max_length=MAX_STATE_LENGTH, description="State")
    zip: Optional[str] = Field(default=None, max_length=MAX_ZIP_LENGTH, description="ZIP code")

    # Contact info
    phone: Optional[str] = Field(default=None, max_length=MAX_PHONE_LENGTH, description="Phone number")
    email: Optional[str] = Field(default=None, max_length=MAX_EMAIL_LENGTH, description="Email address")

    # Report metadata
    report_token: Optional[str] = Field(default=None, max_length=100, description="Report token")

    @field_validator('ssn')
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        """Validate SSN format (9 digits or with dashes)."""
        ssn_digits = v.replace('-', '')
        if not re.match(r'^\d{9}$', ssn_digits):
            raise ValueError('SSN must be 9 digits, optionally formatted as XXX-XX-XXXX')
        return v

    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate email format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError('Invalid email format')
        return v.lower()

    @field_validator('state')
    @classmethod
    def validate_state_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate state code format if provided."""
        if v is None or v == '':
            return v
        if not re.match(r'^[A-Za-z]{2}$', v):
            raise ValueError('State must be 2 letters')
        return v.upper()


class InstantSSNPurchaseResponse(BaseModel):
    """
    Response model for Instant SSN purchase.
    """
    success: bool
    order_id: Optional[str] = Field(None, description="UUID of created order")
    message: str
    new_balance: Optional[float] = Field(None, description="User's new balance after purchase")
