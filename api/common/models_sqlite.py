"""
Pydantic models for SSN data from SQLite database.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
import re


class SSNRecord(BaseModel):
    """Response model for SSN record."""
    id: int
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    middlename: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    ssn: str
    dob: Optional[str] = None
    email: Optional[str] = None
    source_table: Optional[str] = None
    # Count fields for lookup results (when actual data is hidden)
    email_count: Optional[int] = None
    phone_count: Optional[int] = None

    class Config:
        from_attributes = True


class SSNRecordCreate(BaseModel):
    """Request model for creating SSN record."""
    ssn: str
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    middlename: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    email: Optional[str] = None

    @field_validator('ssn')
    @classmethod
    def validate_ssn(cls, v: str) -> str:
        """Validate SSN format (9 digits or with dashes)."""
        # Remove dashes for validation
        ssn_digits = v.replace('-', '')
        if not re.match(r'^\d{9}$', ssn_digits):
            raise ValueError('SSN must be 9 digits, optionally formatted as XXX-XX-XXXX')
        return v


class SSNRecordUpdate(BaseModel):
    """Request model for updating SSN record."""
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    middlename: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    dob: Optional[str] = None
    email: Optional[str] = None


class SearchBySSNRequest(BaseModel):
    """Request model for SSN search."""
    ssn: str
    limit: Optional[int] = None


class SearchByNameRequest(BaseModel):
    """
    Request model for name search.

    Supports two search combinations:
    1. firstname + lastname + zip
    2. firstname + lastname + address
    """
    firstname: str
    lastname: str
    zip: Optional[str] = None
    address: Optional[str] = None
    limit: Optional[int] = None

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

    Requires firstname, lastname, and address.
    """
    firstname: str = Field(..., min_length=1, description="First name")
    lastname: str = Field(..., min_length=1, description="Last name")
    address: str = Field(..., min_length=1, description="Street address")
    source: Optional[str] = Field(default="web", description="Request source: web, telegram_bot, or other")


class InstantSSNResult(BaseModel):
    """
    Response model for Instant SSN search result - ONLY current/primary data.

    Contains primary (current) data and SSN from local database.
    Historical data is not included.
    """
    # Personal info
    firstname: str
    lastname: str
    middlename: Optional[str] = None
    dob: Optional[str] = None

    # Primary (current) address
    address: Optional[str] = Field(None, description="Current address (full street)")
    city: Optional[str] = Field(None, description="Current city")
    state: Optional[str] = Field(None, description="Current state")
    zip_code: Optional[str] = Field(None, description="Current ZIP code")

    # Primary (current) contact
    phone: Optional[str] = Field(None, description="Current phone number")
    email: Optional[str] = Field(None, description="Current email address")

    # SSN from local database (if found)
    ssn: Optional[str] = None
    ssn_found: bool = Field(default=False, description="Whether SSN was found in database")

    # Source information
    report_token: Optional[str] = Field(None, description="Report token")

    # Local database data (when SSN is found)
    local_db_data: Optional[dict] = Field(None, description="Additional data from local SSN database")


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

    Contains all data from InstantSSNResult that user wants to purchase.
    Fixed price: $2.00 per record.
    """
    # Required SSN data
    ssn: str = Field(..., description="Social Security Number")
    source_table: Optional[str] = Field(None, description="Source table from local DB (e.g., 'ssn_1', 'ssn_2')")

    # Personal info
    firstname: str = Field(..., description="First name")
    lastname: str = Field(..., description="Last name")
    middlename: Optional[str] = Field(None, description="Middle name")
    dob: Optional[str] = Field(None, description="Date of birth")

    # Address info
    address: Optional[str] = Field(None, description="Street address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    zip: Optional[str] = Field(None, description="ZIP code")

    # Contact info
    phone: Optional[str] = Field(None, description="Phone number")
    email: Optional[str] = Field(None, description="Email address")

    # Report metadata
    report_token: Optional[str] = Field(None, description="Report token")


class InstantSSNPurchaseResponse(BaseModel):
    """
    Response model for Instant SSN purchase.
    """
    success: bool
    order_id: Optional[str] = Field(None, description="UUID of created order")
    message: str
    new_balance: Optional[float] = Field(None, description="User's new balance after purchase")
