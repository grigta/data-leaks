"""
SearchBug API Client for data enrichment.

This module provides integration with SearchBug API for enriching person data
with current addresses, phone numbers, emails, and other personal information.
"""

import os
import re
import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple
import httpx
from api.common.api_error_logger import log_api_error


# Configure logging
logger = logging.getLogger("searchbug_client")


# ============================================
# Exception Classes
# ============================================

class SearchbugAPIError(Exception):
    """Base exception for SearchBug API errors."""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class SearchbugRateLimitError(SearchbugAPIError):
    """Exception raised when API rate limit is exceeded (429)."""
    pass


class SearchbugNotFoundError(SearchbugAPIError):
    """Exception raised when resource is not found (404)."""
    pass


# ============================================
# SearchBug Client
# ============================================

class SearchbugClient:
    """
    Async client for SearchBug API integration.

    Provides methods for searching person data by phone, name/address, or email,
    and enriching existing records with fresh data from SearchBug.
    """

    def __init__(
        self,
        co_code: str,
        password: str,
        api_url: str = "https://data.searchbug.com/api/search.aspx",
        timeout: int = 30,
        max_retries: int = 3,
        default_limit: int = 100
    ):
        """
        Initialize SearchBug API client.

        Args:
            co_code: SearchBug company code
            password: SearchBug API password
            api_url: Base URL for SearchBug API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            default_limit: Default limit for search results

        Raises:
            ValueError: If co_code or password is empty or invalid
        """
        if not co_code or co_code.strip() == "":
            raise ValueError("SEARCHBUG_CO_CODE is required")
        if not password or password.strip() == "":
            raise ValueError("SEARCHBUG_PASSWORD is required")

        self.co_code = co_code.strip()
        self.password = password.strip()
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_limit = default_limit
        self.client: Optional[httpx.AsyncClient] = None

        logger.info(f"SearchbugClient initialized: api_url={self.api_url}")

    async def open(self):
        """
        Explicitly initialize the HTTP client.

        Use this method for manual client lifecycle management.
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
        return self

    async def close(self):
        """
        Explicitly close the HTTP client.

        Use this method for manual client lifecycle management.
        """
        if self.client:
            await self.client.aclose()
            self.client = None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    # ============================================
    # Core HTTP Method
    # ============================================

    async def _make_request(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Make HTTP POST request to SearchBug API with retry logic.

        Args:
            params: POST parameters

        Returns:
            Parsed JSON response

        Raises:
            SearchbugAPIError: On API errors
            SearchbugRateLimitError: On rate limit errors
            SearchbugNotFoundError: On 404 errors
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Add authentication parameters
        request_params = {
            'CO_CODE': self.co_code,
            'PASS': self.password,
            'TYPE': 'api_ppl',
            'FORMAT': 'JSON',
            **params
        }

        # Mask sensitive data for logging
        masked_params = {**request_params}
        masked_params['PASS'] = '***'
        logger.info(f"Making POST request to {self.api_url} with params={masked_params}")

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                response = await self.client.post(
                    self.api_url,
                    data=request_params
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        f"Rate limit exceeded. Waiting {retry_after}s before retry. "
                        f"Attempt {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                # Handle 404
                if response.status_code == 404:
                    logger.warning(f"Resource not found: {self.api_url}")
                    raise SearchbugNotFoundError(
                        message=f"Resource not found",
                        status_code=404
                    )

                # Handle 4xx errors
                if 400 <= response.status_code < 500:
                    error_message = response.text
                    logger.error(f"Client error {response.status_code}: {error_message}")
                    exc = SearchbugAPIError(
                        message=f"API error: {error_message}",
                        status_code=response.status_code
                    )
                    await log_api_error('searchbug', '_make_request', exc, response.status_code, request_params)
                    raise exc

                # Handle 5xx errors - retry with backoff
                if response.status_code >= 500:
                    backoff_delay = 2 ** attempt
                    logger.warning(
                        f"Server error {response.status_code}. "
                        f"Retrying in {backoff_delay}s. Attempt {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(backoff_delay)
                    continue

                # Success
                response.raise_for_status()
                result = response.json()

                # Check for API-level errors
                if result.get('Status') == 'Error':
                    error_msg = result.get('Error', 'Unknown API error')
                    logger.error(f"SearchBug API error: {error_msg}")
                    exc = SearchbugAPIError(
                        message=f"API error: {error_msg}",
                        status_code=200
                    )
                    await log_api_error('searchbug', '_make_request', exc, 200, request_params)
                    raise exc

                logger.info(f"Request successful")
                return result

            except httpx.NetworkError as e:
                backoff_delay = 2 ** attempt
                logger.warning(
                    f"Network error: {str(e)}. "
                    f"Retrying in {backoff_delay}s. Attempt {attempt + 1}/{self.max_retries}"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(backoff_delay)
                    continue
                else:
                    exc = SearchbugAPIError(
                        message=f"Network error after {self.max_retries} attempts: {str(e)}"
                    )
                    await log_api_error('searchbug', '_make_request', exc, None, request_params)
                    raise exc

            except httpx.TimeoutException as e:
                logger.error(f"Request timeout: {str(e)}")
                exc = SearchbugAPIError(message=f"Request timeout: {str(e)}")
                await log_api_error('searchbug', '_make_request', exc, None, request_params)
                raise exc

            except Exception as e:
                if isinstance(e, (SearchbugAPIError, SearchbugRateLimitError, SearchbugNotFoundError)):
                    raise
                logger.error(f"Unexpected error: {str(e)}")
                exc = SearchbugAPIError(message=f"Unexpected error: {str(e)}")
                await log_api_error('searchbug', '_make_request', exc, None, request_params)
                raise exc

        # Max retries exceeded
        exc = SearchbugRateLimitError(
            message=f"Rate limit exceeded after {self.max_retries} attempts",
            status_code=429
        )
        await log_api_error('searchbug', '_make_request', exc, 429, request_params)
        raise exc

    # ============================================
    # Search Methods
    # ============================================

    async def search_person_by_phone(
        self,
        phone: str,
        limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search for person by phone number.

        Args:
            phone: Phone number (will be normalized)
            limit: Maximum number of results

        Returns:
            Person data dict or None if not found
        """
        if not phone:
            return None

        normalized_phone = self._normalize_phone(phone)
        logger.info(f"Searching person by phone: {normalized_phone}")

        params = {
            'F': normalized_phone,
            'LIMIT': limit or self.default_limit
        }

        try:
            result = await self._make_request(params)
            person_data = self._extract_person_data(result)

            if person_data:
                logger.info(f"Found person for phone {normalized_phone}")
                return person_data

            logger.info(f"No results found for phone {normalized_phone}")
            return None

        except SearchbugNotFoundError:
            return None

    async def search_person_by_name_address(
        self,
        firstname: str,
        lastname: str,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zipcode: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search for person by name and address components.

        If state/zipcode not provided explicitly, attempts to parse them from address string.
        Supports formats like "123 Main St, City, FL 34997" or "123 Main St FL".

        Args:
            firstname: First name
            lastname: Last name
            address: Street address (may include city, state, zip)
            city: City name
            state: State code (2 letters)
            zipcode: ZIP code
            limit: Maximum number of results

        Returns:
            Person data dict or None if not found
        """
        if not firstname or not lastname:
            return None

        logger.info(
            f"Searching person by name/address: {firstname} {lastname}, "
            f"address={address}, city={city}, state={state}, zip={zipcode}"
        )

        params = {
            'FNAME': firstname.strip(),
            'LNAME': lastname.strip(),
            'LIMIT': limit or self.default_limit
        }

        if address:
            params['ADDRESS'] = address.strip()
        if city:
            params['CITY'] = city.strip()
        if state:
            params['STATE'] = state.strip().upper()
        if zipcode:
            params['ZIP'] = str(zipcode).strip()

        try:
            result = await self._make_request(params)
            person_data = self._extract_person_data(result)

            if person_data:
                logger.info(f"Found person for {firstname} {lastname}")
                return person_data

            logger.info(f"No results found for {firstname} {lastname}")
            return None

        except SearchbugNotFoundError:
            return None

    async def search_person_by_email(
        self,
        email: str,
        limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search for person by email address.

        Args:
            email: Email address
            limit: Maximum number of results

        Returns:
            Person data dict or None if not found
        """
        if not email:
            return None

        logger.info(f"Searching person by email: {email}")

        params = {
            'EMAIL': email.strip(),
            'LIMIT': limit or self.default_limit
        }

        try:
            result = await self._make_request(params)
            person_data = self._extract_person_data(result)

            if person_data:
                logger.info(f"Found person for email {email}")
                return person_data

            logger.info(f"No results found for email {email}")
            return None

        except SearchbugNotFoundError:
            return None

    async def search_person_by_name_zip(
        self,
        firstname: str,
        lastname: str,
        zipcode: str,
        limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search for person by name and ZIP code.

        Args:
            firstname: First name
            lastname: Last name
            zipcode: ZIP code
            limit: Maximum number of results

        Returns:
            Person data dict or None if not found
        """
        if not firstname or not lastname or not zipcode:
            logger.warning(f"Missing required fields for name+zip search")
            return None

        logger.info(f"Searching person by name+zip: {firstname} {lastname}, zipcode={zipcode}")

        params = {
            'FNAME': firstname.strip(),
            'LNAME': lastname.strip(),
            'ZIP': str(zipcode).strip(),
            'LIMIT': limit or self.default_limit
        }

        try:
            result = await self._make_request(params)
            person_data = self._extract_person_data(result)

            if person_data:
                logger.info(f"Found person for {firstname} {lastname} in ZIP {zipcode}")
                return person_data

            logger.info(f"No results found for {firstname} {lastname} in ZIP {zipcode}")
            return None

        except SearchbugNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error searching by name+zip: {e}")
            return None

    async def search_person_unified(
        self,
        firstname: str,
        lastname: str,
        zipcode: Optional[str] = None,
        address: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Unified search method for Instant SSN feature.
        Searches by name with either ZIP or address (at least one required).

        Args:
            firstname: First name (required)
            lastname: Last name (required)
            zipcode: ZIP code (optional, but either zipcode or address required)
            address: Street address (optional, but either zipcode or address required)
            limit: Maximum number of results

        Returns:
            Person data dict with aggregated ZIP codes and phone numbers, or None if not found

        Raises:
            ValueError: If both zipcode and address are missing
        """
        if not firstname or not lastname:
            logger.warning("Missing required fields: firstname and lastname")
            return None

        if not zipcode and not address:
            raise ValueError("At least one of zipcode or address is required")

        logger.info(
            f"Unified search for {firstname} {lastname}, "
            f"zipcode={zipcode}, address={address}"
        )

        # Priority: ZIP code first, then address
        person_data = None

        if zipcode:
            logger.info(f"Searching by name+ZIP: {firstname} {lastname}, {zipcode}")
            person_data = await self.search_person_by_name_zip(
                firstname=firstname,
                lastname=lastname,
                zipcode=zipcode,
                limit=limit
            )

        if not person_data and address:
            logger.info(f"Searching by name+address: {firstname} {lastname}, {address}")
            person_data = await self.search_person_by_name_address(
                firstname=firstname,
                lastname=lastname,
                address=address,
                limit=limit
            )

        if not person_data:
            logger.info(f"No results found for {firstname} {lastname}")
            return None

        # Extract and aggregate all ZIP codes and phone numbers
        all_zips = []
        all_phones = []

        addresses = person_data.get('addresses', [])
        for addr in addresses:
            zip_code = addr.get('zip_code') or ''
            zip_code = zip_code.strip() if zip_code else ''
            if zip_code and zip_code not in all_zips:
                all_zips.append(zip_code)

        phones = person_data.get('phones', [])
        seen_phones = set()
        for phone in phones:
            phone_number = phone.get('phone_number') or ''
            phone_number = phone_number.strip() if phone_number else ''
            if phone_number:
                normalized = self._normalize_phone(phone_number)
                if normalized and normalized not in seen_phones:
                    seen_phones.add(normalized)
                    all_phones.append({
                        'phone_number': normalized,
                        'phone_type': phone.get('phone_type') or '',
                        'carrier': phone.get('carrier') or '',
                        'first_date': phone.get('first_date') or '',
                        'last_date': phone.get('last_date') or ''
                    })

        # Add aggregated lists to person_data
        person_data['all_zips'] = all_zips
        person_data['all_phones'] = all_phones

        # Determine primary (current) data from SearchBug
        addresses = person_data.get('addresses', [])
        emails = person_data.get('emails', [])

        primary_address = addresses[0] if addresses else None
        primary_phone = self._select_primary_phone(all_phones, primary_address)
        primary_email = emails[0] if emails else None

        # Add primary data to person_data
        person_data['primary_address'] = primary_address
        person_data['primary_phone'] = primary_phone
        person_data['primary_email'] = primary_email

        logger.info(
            f"Found person: {len(all_zips)} unique ZIP codes, "
            f"{len(all_phones)} unique phone numbers, "
            f"primary phone: {primary_phone}, primary email: {primary_email}"
        )

        return person_data

    # ============================================
    # Enrichment Method
    # ============================================

    async def enrich_person_data(self, current_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich person data using SearchBug API.

        Sequential search strategy:
        1. Try Name + Address (if address components available)
        2. Try Name + Phone (if phone available)
        3. Try Name + Zip (if zip available)

        Args:
            current_record: Current person record from database

        Returns:
            Dict with enriched fields (only fields with new/updated values)
        """
        logger.info(f"Enriching person data for SSN: {current_record.get('ssn', 'N/A')}")

        enriched_data = {}
        searchbug_result = None

        # Extract current record fields
        phone = current_record.get("phone")
        firstname = current_record.get("firstname")
        lastname = current_record.get("lastname")
        street = current_record.get("street")
        city = current_record.get("city")
        state = current_record.get("state")
        zipcode = current_record.get("zipcode")

        # Try sequential search
        # Attempt 1: Name + Address
        has_address_component = any([street, city, state, zipcode])
        if firstname and lastname and has_address_component:
            logger.info("Attempt 1: Name + Address search")
            searchbug_result = await self.search_person_by_name_address(
                firstname=firstname,
                lastname=lastname,
                address=street,
                city=city,
                state=state,
                zipcode=zipcode
            )

        # Attempt 2: Name + Phone (if first attempt failed)
        if not searchbug_result and phone and firstname and lastname:
            logger.info("Attempt 2: Name + Phone search")
            searchbug_result = await self.search_person_by_phone(phone=phone)

        # Attempt 3: Name + Zip (if previous attempts failed)
        if not searchbug_result and zipcode and firstname and lastname:
            logger.info("Attempt 3: Name + Zip search")
            searchbug_result = await self.search_person_by_name_zip(
                firstname=firstname,
                lastname=lastname,
                zipcode=zipcode
            )

        # No results found
        if not searchbug_result:
            logger.info("No matching person found in SearchBug API")
            return enriched_data

        # Verify name match for security
        if not self._verify_basic_name_match(searchbug_result, current_record):
            logger.warning("Name verification failed for SearchBug result")
            return enriched_data

        # Extract and map data
        try:
            # Extract primary address
            addresses = searchbug_result.get("addresses", [])
            if addresses and len(addresses) > 0:
                primary_address = addresses[0]
                if primary_address.get("full_street"):
                    enriched_data["street"] = primary_address["full_street"]
                if primary_address.get("city"):
                    enriched_data["city"] = primary_address["city"]
                if primary_address.get("state"):
                    enriched_data["state"] = primary_address["state"]
                if primary_address.get("zip_code"):
                    enriched_data["zipcode"] = primary_address["zip_code"]

            # Extract primary phone
            phones = searchbug_result.get("phones", [])
            if phones and len(phones) > 0:
                primary_phone = phones[0]
                phone_number = primary_phone.get("phone_number", "")
                if phone_number:
                    enriched_data["phone"] = self._format_phone(phone_number)

            # Extract email
            emails = searchbug_result.get("emails", [])
            if emails and len(emails) > 0:
                enriched_data["email"] = emails[0]

            # Extract DOB
            dob = searchbug_result.get("dob")
            if dob:
                enriched_data["dob"] = str(dob)

            # Extract middle name
            names = searchbug_result.get("names", [])
            if names and len(names) > 0:
                middle_name = names[0].get("middle_name")
                if middle_name:
                    enriched_data["middlename"] = middle_name

            logger.info(f"Successfully enriched {len(enriched_data)} fields")

        except Exception as e:
            logger.error(f"Error mapping SearchBug data: {str(e)}")
            return {}

        return enriched_data

    # ============================================
    # Helper Methods
    # ============================================

    def _extract_person_data(self, api_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract person data from SearchBug API response.

        Args:
            api_response: Raw API response

        Returns:
            Structured person data dict or None
        """
        if not api_response:
            return None

        # Navigate to person data
        people = api_response.get('people', {})

        # SearchBug может вернуть people как list или dict
        if isinstance(people, list):
            # Если список - берем первый элемент
            person_data = people[0] if people else {}
        elif isinstance(people, dict):
            # Если словарь - берем ключ 'person'
            person_data = people.get('person', {})
        else:
            person_data = {}

        # SearchBug может вернуть вложенный список [[{...}]]
        # Распаковываем если person_data это список
        if isinstance(person_data, list):
            person_data = person_data[0] if person_data else {}

        if not person_data:
            return None

        # Parse names
        names_raw = person_data.get('names', {})
        if isinstance(names_raw, list):
            # SearchBug returned list directly instead of dict with 'name' key
            names_data = names_raw
        elif isinstance(names_raw, dict):
            # Standard case: dict with 'name' key
            names_data = names_raw.get('name', [])
            if not isinstance(names_data, list):
                names_data = [names_data] if names_data else []
        else:
            names_data = []

        names = []
        for name_item in names_data:
            if name_item:
                names.append({
                    'first_name': name_item.get('firstName', ''),
                    'middle_name': name_item.get('middleName', ''),
                    'last_name': name_item.get('lastName', ''),
                    'first_date': name_item.get('firstDate', ''),
                    'last_date': name_item.get('lastDate', '')
                })

        # Parse addresses
        addresses_raw = person_data.get('addresses', {})
        if isinstance(addresses_raw, list):
            # SearchBug returned list directly instead of dict with 'address' key
            addresses_data = addresses_raw
        elif isinstance(addresses_raw, dict):
            # Standard case: dict with 'address' key
            addresses_data = addresses_raw.get('address', [])
            if not isinstance(addresses_data, list):
                addresses_data = [addresses_data] if addresses_data else []
        else:
            addresses_data = []

        addresses = []
        for addr_item in addresses_data:
            if addr_item:
                addresses.append({
                    'full_street': addr_item.get('fullStreet', ''),
                    'city': addr_item.get('city', ''),
                    'state': addr_item.get('state', ''),
                    'zip_code': addr_item.get('zip', ''),
                    'county': addr_item.get('county', ''),
                    'first_date': addr_item.get('firstDate', ''),
                    'last_date': addr_item.get('lastDate', '')
                })

        # Parse phones
        phones_raw = person_data.get('phones', {})
        if isinstance(phones_raw, list):
            # SearchBug returned list directly instead of dict with 'phone' key
            phones_data = phones_raw
        elif isinstance(phones_raw, dict):
            # Standard case: dict with 'phone' key
            phones_data = phones_raw.get('phone', [])
            if not isinstance(phones_data, list):
                phones_data = [phones_data] if phones_data else []
        else:
            phones_data = []

        phones = []
        for phone_item in phones_data:
            if phone_item:
                phones.append({
                    'phone_number': phone_item.get('phoneNumber', ''),
                    'phone_type': phone_item.get('phoneType', ''),
                    'carrier': phone_item.get('carrier', ''),
                    'first_date': phone_item.get('firstDate', ''),
                    'last_date': phone_item.get('lastDate', '')
                })

        # Parse emails
        email_records_raw = person_data.get('emailRecords', {})
        if isinstance(email_records_raw, list):
            # SearchBug returned list directly instead of dict with 'emailRecord' key
            email_records = email_records_raw
        elif isinstance(email_records_raw, dict):
            # Standard case: dict with 'emailRecord' key
            email_records = email_records_raw.get('emailRecord', [])
            if not isinstance(email_records, list):
                email_records = [email_records] if email_records else []
        else:
            email_records = []

        emails = []
        for er in email_records:
            if er and isinstance(er, dict):  # Защита от None и non-dict
                email_obj = er.get('email')
                if isinstance(email_obj, dict):  # Защита от None и non-dict
                    email_addr = email_obj.get('emailAddress', '')
                    if email_addr:
                        emails.append(email_addr)

        # Extract DOB (take first/primary date if multiple)
        dob_data = person_data.get('DOBs', {})
        dob_value = dob_data.get('DOB', '') if dob_data else ''
        if isinstance(dob_value, list) and len(dob_value) > 0:
            # Take first (primary) date from list
            dob = str(dob_value[0]).strip()
        elif dob_value:
            dob = str(dob_value).strip()
        else:
            dob = ''

        return {
            'report_token': person_data.get('reportToken', ''),
            'names': names,
            'dob': dob,
            'addresses': addresses,
            'phones': phones,
            'emails': emails
        }

    def _parse_date_obj(self, date_obj: Any) -> int:
        """
        Parse date object from SearchBug API to timestamp for comparison.

        Args:
            date_obj: Date object (can be dict with day/month/year or string MM/DD/YYYY)

        Returns:
            Timestamp (days since epoch) or 0 if invalid
        """
        from datetime import datetime

        if not date_obj:
            return 0

        try:
            if isinstance(date_obj, dict):
                # Format: {"day": "15", "month": "03", "year": "2020"}
                day = int(date_obj.get('day', 1))
                month = int(date_obj.get('month', 1))
                year = int(date_obj.get('year', 2000))
                dt = datetime(year, month, day)
            elif isinstance(date_obj, str):
                # Format: "MM/DD/YYYY" or "YYYY-MM-DD"
                if '/' in date_obj:
                    dt = datetime.strptime(date_obj, "%m/%d/%Y")
                elif '-' in date_obj:
                    dt = datetime.strptime(date_obj, "%Y-%m-%d")
                else:
                    return 0
            else:
                return 0

            # Return days since epoch for easy comparison
            return int(dt.timestamp() / 86400)
        except:
            return 0

    def _select_primary_phone(self, phones: List[Dict[str, Any]], current_address: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Select primary (current) phone number from list of phones.

        Criteria:
        1. Maximum lastDate (most recent)
        2. Priority: Mobile > Landline > VOIP > Other
        3. Period overlaps with current address period (if address provided)

        Args:
            phones: List of phone dictionaries with metadata
            current_address: Current address dict (optional, for period overlap check)

        Returns:
            Primary phone number or None
        """
        if not phones:
            return None

        # Filter phones with valid lastDate and sort
        valid_phones = []
        for phone in phones:
            last_date = phone.get('last_date')
            if last_date:
                valid_phones.append(phone)

        if not valid_phones:
            # If no phones have lastDate, return first phone
            return phones[0].get('phone_number') if phones else None

        # Sort by: lastDate (DESC), then phone_type priority
        def phone_priority(p):
            last_date_ts = self._parse_date_obj(p.get('last_date', ''))
            phone_type = p.get('phone_type', '').lower()

            # Type priority: Mobile=3, Landline=2, VOIP=1, Other=0
            type_priority = 0
            if 'mobile' in phone_type or 'cell' in phone_type or 'wireless' in phone_type:
                type_priority = 3
            elif 'landline' in phone_type or 'fixed' in phone_type:
                type_priority = 2
            elif 'voip' in phone_type:
                type_priority = 1

            return (last_date_ts, type_priority)

        sorted_phones = sorted(valid_phones, key=phone_priority, reverse=True)

        return sorted_phones[0].get('phone_number') if sorted_phones else None

    def _normalize_phone(self, phone: str) -> str:
        """
        Normalize phone number for API requests (digits only, no leading 1).

        Args:
            phone: Raw phone number

        Returns:
            Normalized phone number (digits only, 10-digit format)
        """
        if not phone:
            return ""

        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)

        # Remove leading 1 for US numbers
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]

        # Return 10-digit format
        if len(digits) == 10:
            return digits

        return phone  # Return original if can't normalize

    def _format_phone(self, phone: str) -> str:
        """
        Format phone number for storage/display.

        Args:
            phone: Raw phone number

        Returns:
            Formatted phone number (XXX) XXX-XXXX
        """
        if not phone:
            return ""

        # Remove all non-digit characters
        digits = re.sub(r'\D', '', phone)

        # Remove leading 1 for US numbers
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]

        # Return formatted 10-digit format
        if len(digits) == 10:
            return f"({digits[0:3]}) {digits[3:6]}-{digits[6:10]}"

        return phone  # Return original if can't format

    def _verify_basic_name_match(
        self,
        searchbug_data: Dict[str, Any],
        current_record: Dict[str, Any]
    ) -> bool:
        """
        Verify basic name match between SearchBug data and current record.

        Args:
            searchbug_data: SearchBug person data
            current_record: Current database record

        Returns:
            True if names match or verification can be skipped
        """
        # Extract names from current record
        current_firstname = (current_record.get('firstname') or '').strip().lower()
        current_lastname = (current_record.get('lastname') or '').strip().lower()

        # If firstname or lastname is missing, don't block enrichment
        if not current_firstname or not current_lastname:
            logger.debug("Name field missing in current_record, allowing enrichment")
            return True

        # Extract names from SearchBug data
        names = searchbug_data.get('names', [])
        if not names or len(names) == 0:
            logger.debug("No names in SearchBug data")
            return False

        # Check first name from SearchBug
        sb_firstname = (names[0].get('first_name') or '').strip().lower()
        sb_lastname = (names[0].get('last_name') or '').strip().lower()

        if not sb_firstname or not sb_lastname:
            logger.debug("Name field missing in SearchBug data")
            return False

        # Compare names (case-insensitive)
        match = (current_firstname == sb_firstname and current_lastname == sb_lastname)

        if not match:
            logger.debug(
                f"Name mismatch: current='{current_firstname} {current_lastname}' vs "
                f"searchbug='{sb_firstname} {sb_lastname}'"
            )

        return match


# ============================================
# Factory Function
# ============================================

def create_searchbug_client() -> SearchbugClient:
    """
    Create SearchBug client from environment variables.

    Returns:
        Configured SearchbugClient instance

    Raises:
        ValueError: If required environment variables are missing

    Example:
        # Using async context manager (recommended)
        async with create_searchbug_client() as client:
            result = await client.search_person_by_phone("5551234567")

        # Or using explicit initialization
        client = create_searchbug_client()
        await client.open()
        try:
            result = await client.search_person_by_phone("5551234567")
        finally:
            await client.close()
    """
    co_code = os.getenv("SEARCHBUG_CO_CODE", "")
    password = os.getenv("SEARCHBUG_PASSWORD", "")
    api_url = os.getenv("SEARCHBUG_API_URL", "https://data.searchbug.com/api/search.aspx")
    default_limit = int(os.getenv("SEARCHBUG_DEFAULT_LIMIT", "100"))

    if not co_code:
        raise ValueError(
            "SEARCHBUG_CO_CODE environment variable is required. "
            "Please set it in your .env file."
        )

    if not password:
        raise ValueError(
            "SEARCHBUG_PASSWORD environment variable is required. "
            "Please set it in your .env file."
        )

    return SearchbugClient(
        co_code=co_code,
        password=password,
        api_url=api_url,
        default_limit=default_limit
    )


async def create_searchbug_client_dynamic(db) -> SearchbugClient:
    """Create SearchBug client with dynamic credentials from DB.

    Reads credentials from AppSettings (cached 60s), falls back to env vars.
    Use this instead of create_searchbug_client() when db session is available.
    """
    from api.common.pricing import get_searchbug_keys

    keys = await get_searchbug_keys(db)

    co_code = keys.get("searchbug_co_code") or os.getenv("SEARCHBUG_CO_CODE", "")
    password = keys.get("searchbug_password") or os.getenv("SEARCHBUG_PASSWORD", "")
    api_url = os.getenv("SEARCHBUG_API_URL", "https://data.searchbug.com/api/search.aspx")
    default_limit = int(os.getenv("SEARCHBUG_DEFAULT_LIMIT", "100"))

    if not co_code:
        raise ValueError(
            "SearchBug CO_CODE is not configured. "
            "Set it in admin settings or SEARCHBUG_CO_CODE env var."
        )
    if not password:
        raise ValueError(
            "SearchBug password is not configured. "
            "Set it in admin settings or SEARCHBUG_PASSWORD env var."
        )

    return SearchbugClient(
        co_code=co_code,
        password=password,
        api_url=api_url,
        default_limit=default_limit
    )
