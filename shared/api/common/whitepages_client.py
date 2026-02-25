"""
WhitePages API Client for person data lookup.

Provides integration with WhitePages API for searching person data
by name/address, returning addresses, phones, emails, and DOB.
"""

import os
import re
import logging
import asyncio
from typing import Optional, Dict, Any, List
import httpx
from api.common.api_error_logger import log_api_error


logger = logging.getLogger("whitepages_client")


# ============================================
# Exception Classes
# ============================================

class WhitepagesAPIError(Exception):
    """Base exception for WhitePages API errors."""

    def __init__(self, message: str, status_code: int = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class WhitepagesRateLimitError(WhitepagesAPIError):
    """Exception raised when API rate limit is exceeded (429)."""
    pass


class WhitepagesNotFoundError(WhitepagesAPIError):
    """Exception raised when no results found."""
    pass


# ============================================
# WhitePages Client
# ============================================

class WhitepagesClient:
    """
    Async client for WhitePages API integration.

    Provides person search by name+address and normalizes response
    into the same format as SearchbugClient for downstream compatibility.
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.whitepages.com/v1/person",
        timeout: int = 30,
        max_retries: int = 3,
    ):
        if not api_key or api_key.strip() == "":
            raise ValueError("WHITEPAGES_API_KEY is required")

        self.api_key = api_key.strip()
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.client: Optional[httpx.AsyncClient] = None

        logger.info(f"WhitepagesClient initialized: api_url={self.api_url}")

    async def open(self):
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True
            )
        return self

    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # ============================================
    # Core HTTP Method
    # ============================================

    async def _make_request(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Make HTTP GET request to WhitePages API with retry logic.

        Returns:
            Parsed JSON response (list of person objects)
        """
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        logger.info(f"Making GET request to {self.api_url} with params={params}")

        for attempt in range(self.max_retries):
            try:
                response = await self.client.get(
                    self.api_url,
                    params=params,
                    headers={"X-Api-Key": self.api_key}
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(
                        f"Rate limit exceeded. Waiting {retry_after}s. "
                        f"Attempt {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                if response.status_code == 404:
                    raise WhitepagesNotFoundError(
                        message="No results found",
                        status_code=404
                    )

                if 400 <= response.status_code < 500:
                    error_message = response.text
                    logger.error(f"Client error {response.status_code}: {error_message}")
                    exc = WhitepagesAPIError(
                        message=f"API error: {error_message}",
                        status_code=response.status_code
                    )
                    await log_api_error('whitepages', '_make_request', exc, response.status_code, params)
                    raise exc

                if response.status_code >= 500:
                    backoff_delay = 2 ** attempt
                    logger.warning(
                        f"Server error {response.status_code}. "
                        f"Retrying in {backoff_delay}s. Attempt {attempt + 1}/{self.max_retries}"
                    )
                    await asyncio.sleep(backoff_delay)
                    continue

                response.raise_for_status()
                result = response.json()

                if isinstance(result, list):
                    return result
                elif isinstance(result, dict):
                    return [result]
                else:
                    return []

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
                    exc = WhitepagesAPIError(
                        message=f"Network error after {self.max_retries} attempts: {str(e)}"
                    )
                    await log_api_error('whitepages', '_make_request', exc, None, params)
                    raise exc

            except httpx.TimeoutException as e:
                logger.error(f"Request timeout: {str(e)}")
                exc = WhitepagesAPIError(message=f"Request timeout: {str(e)}")
                await log_api_error('whitepages', '_make_request', exc, None, params)
                raise exc

            except Exception as e:
                if isinstance(e, (WhitepagesAPIError, WhitepagesRateLimitError, WhitepagesNotFoundError)):
                    raise
                logger.error(f"Unexpected error: {str(e)}")
                exc = WhitepagesAPIError(message=f"Unexpected error: {str(e)}")
                await log_api_error('whitepages', '_make_request', exc, None, params)
                raise exc

        exc = WhitepagesRateLimitError(
            message=f"Rate limit exceeded after {self.max_retries} attempts",
            status_code=429
        )
        await log_api_error('whitepages', '_make_request', exc, 429, params)
        raise exc

    # ============================================
    # Search Method (compatible signature)
    # ============================================

    async def search_person_unified(
        self,
        firstname: str,
        lastname: str,
        zipcode: Optional[str] = None,
        address: Optional[str] = None,
        limit: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Search person by name and address via WhitePages API.
        Returns normalized data in the same format as SearchbugClient.search_person_unified.
        """
        if not firstname or not lastname:
            return None

        params: Dict[str, str] = {
            "name": f"{firstname.strip()} {lastname.strip()}"
        }
        if address:
            params["street"] = address.strip()

        try:
            results = await self._make_request(params)
        except WhitepagesNotFoundError:
            return None

        if not results:
            return None

        person = results[0]
        return self._extract_person_data(person)

    # ============================================
    # Data Extraction & Normalization
    # ============================================

    def _extract_person_data(self, person: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize WhitePages person object into SearchbugClient-compatible format.
        """
        if not person:
            return None

        # Parse names
        names = []
        primary_name = person.get("name", "")
        if primary_name:
            names.append(self._parse_name(primary_name))

        for alias in (person.get("aliases") or []):
            if alias:
                names.append(self._parse_name(alias))

        # Parse addresses
        addresses = []
        for addr_obj in (person.get("current_addresses") or []):
            parsed = self._parse_address_string(addr_obj.get("address", ""))
            if parsed:
                addresses.append(parsed)

        for addr_obj in (person.get("historic_addresses") or []):
            parsed = self._parse_address_string(addr_obj.get("address", ""))
            if parsed:
                addresses.append(parsed)

        # Parse phones
        phones = []
        seen_phones = set()
        for phone_obj in (person.get("phones") or []):
            raw_number = phone_obj.get("number", "")
            normalized = self._normalize_phone(raw_number)
            if normalized and normalized not in seen_phones:
                seen_phones.add(normalized)
                phones.append({
                    "phone_number": normalized,
                    "phone_type": phone_obj.get("type", ""),
                    "carrier": "",
                    "first_date": "",
                    "last_date": ""
                })

        # Parse emails
        emails = list(person.get("emails") or [])

        # DOB
        dob = person.get("date_of_birth", "") or ""

        # Build aggregated lists (same as SearchbugClient.search_person_unified)
        all_zips = []
        for addr in addresses:
            zc = (addr.get("zip_code") or "").strip()
            if zc and zc not in all_zips:
                all_zips.append(zc)

        all_phones = []
        for p in phones:
            all_phones.append({
                "phone_number": p["phone_number"],
                "phone_type": p.get("phone_type", ""),
                "carrier": "",
                "first_date": "",
                "last_date": ""
            })

        primary_address = addresses[0] if addresses else None
        primary_phone = phones[0]["phone_number"] if phones else None
        primary_email = emails[0] if emails else None

        return {
            "report_token": person.get("id", ""),
            "names": names,
            "dob": dob,
            "addresses": addresses,
            "phones": phones,
            "emails": emails,
            "all_zips": all_zips,
            "all_phones": all_phones,
            "primary_address": primary_address,
            "primary_phone": primary_phone,
            "primary_email": primary_email,
        }

    def _parse_name(self, full_name: str) -> Dict[str, str]:
        """Parse 'Thomas L Trapp' into first/middle/last name dict."""
        parts = full_name.strip().split()
        if len(parts) >= 3:
            return {
                "first_name": parts[0],
                "middle_name": " ".join(parts[1:-1]),
                "last_name": parts[-1],
                "first_date": "",
                "last_date": ""
            }
        elif len(parts) == 2:
            return {
                "first_name": parts[0],
                "middle_name": "",
                "last_name": parts[1],
                "first_date": "",
                "last_date": ""
            }
        elif len(parts) == 1:
            return {
                "first_name": parts[0],
                "middle_name": "",
                "last_name": "",
                "first_date": "",
                "last_date": ""
            }
        return {
            "first_name": "",
            "middle_name": "",
            "last_name": "",
            "first_date": "",
            "last_date": ""
        }

    # Known street suffixes (end of street address)
    _STREET_SUFFIXES = {
        'st', 'ave', 'rd', 'dr', 'blvd', 'ln', 'ct', 'cir', 'way', 'pl',
        'ter', 'loop', 'pkwy', 'hwy', 'trl', 'run', 'path', 'pass', 'xing',
        'sq', 'row', 'pike', 'walk', 'aly', 'park', 'oval',
    }

    # Unit designators (take a following value like "Apt C", "Unit 2B")
    _UNIT_DESIGNATORS = {
        'apt', 'unit', 'ste', 'suite', 'box', 'lot', 'fl', 'floor',
        'bldg', 'rm', 'room', '#',
    }

    def _split_street_city(self, street_and_city: str) -> tuple:
        """
        Split '3961 N Everett Rd Apt C Muncie' into ('3961 N Everett Rd Apt C', 'Muncie').

        Finds the last "anchor" word that belongs to the street address:
        - Words containing digits (house number, apt number)
        - Known street suffixes (Rd, St, Ave, Dr, etc.)
        - Known unit designators (Apt, Unit, Box, etc.) + their value
        Everything after the last anchor is the city name.
        """
        words = street_and_city.split()
        if len(words) <= 1:
            return street_and_city, ''

        last_street_idx = 0
        for i, word in enumerate(words):
            w = word.lower().rstrip('.')
            if (any(c.isdigit() for c in word) or
                    w in self._STREET_SUFFIXES or
                    w in self._UNIT_DESIGNATORS):
                last_street_idx = i

        # If anchor is a unit designator, include its following value
        # e.g. "Apt C" → include "C", "Unit 2B" → include "2B"
        anchor = words[last_street_idx].lower().rstrip('.')
        if anchor in self._UNIT_DESIGNATORS and last_street_idx + 1 < len(words):
            next_word = words[last_street_idx + 1]
            if len(next_word) <= 5:
                last_street_idx += 1

        street = ' '.join(words[:last_street_idx + 1])
        city = ' '.join(words[last_street_idx + 1:])
        return street, city

    def _parse_address_string(self, addr_str: str) -> Optional[Dict[str, str]]:
        """
        Parse '3080 Demartini Dr Roseville, CA 95661' into components.

        Strategy:
        1. Extract ', ST ZIP' from the end (comma is a reliable anchor)
        2. Split the remaining 'street city' using _split_street_city heuristic
        """
        if not addr_str:
            return None

        # Try: street_and_city, ST ZIP
        m = re.match(
            r'^(.*),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$',
            addr_str.strip()
        )
        if m:
            street, city = self._split_street_city(m.group(1).strip())
            return {
                "full_street": street,
                "city": city,
                "state": m.group(2),
                "zip_code": m.group(3),
                "county": "",
                "first_date": "",
                "last_date": ""
            }

        # Fallback: street_and_city, ST (without zip)
        m2 = re.match(
            r'^(.*),\s*([A-Z]{2})$',
            addr_str.strip()
        )
        if m2:
            street, city = self._split_street_city(m2.group(1).strip())
            return {
                "full_street": street,
                "city": city,
                "state": m2.group(2),
                "zip_code": "",
                "county": "",
                "first_date": "",
                "last_date": ""
            }

        # Can't parse - return raw as full_street
        return {
            "full_street": addr_str.strip(),
            "city": "",
            "state": "",
            "zip_code": "",
            "county": "",
            "first_date": "",
            "last_date": ""
        }

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to 10-digit format."""
        if not phone:
            return ""
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) == 10:
            return digits
        return ""


# ============================================
# Factory Function
# ============================================

def create_whitepages_client() -> WhitepagesClient:
    """
    Create WhitePages client from environment variables.
    """
    api_key = os.getenv("WHITEPAGES_API_KEY", "")
    api_url = os.getenv("WHITEPAGES_API_URL", "https://api.whitepages.com/v1/person")

    if not api_key:
        raise ValueError(
            "WHITEPAGES_API_KEY environment variable is required. "
            "Please set it in your .env file."
        )

    return WhitepagesClient(
        api_key=api_key,
        api_url=api_url
    )
