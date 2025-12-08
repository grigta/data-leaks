"""
Phone Lookup router - search SSN by phone number obtained from DaisySMS.

Flow:
1. User selects a service from dropdown
2. System gets phone number from DaisySMS
3. Phone number is searched via SearchBug API
4. Results are matched against local SSN database
5. User is charged $3.00 only if SSN is found
"""
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from api.common.database import SQLITE_PATH, get_postgres_session
from api.common.models_sqlite import (
    PhoneLookupRequest,
    PhoneLookupResponse,
    PhoneLookupResult,
    DaisySMSService,
    DaisySMSServicesResponse,
    PhoneRentalResponse,
    PhoneRentalsListResponse,
    PhoneRentalRenewResponse,
)
from api.common.models_postgres import (
    User,
    Order,
    OrderStatus,
    OrderType,
    PhoneRental,
    PhoneRentalStatus,
    PhoneLookupSearch,
    RequestSource,
)
from api.public.dependencies import get_current_user
from api.common.searchbug_client import create_searchbug_client, SearchbugAPIError
from api.common.daisysms_client import (
    create_daisysms_client,
    DaisySMSError,
    DaisySMSNoNumbersError,
    DaisySMSBalanceError,
    DaisySMSBadServiceError,
)
from api.common.daisysms_services import SERVICE_CODE_TO_NAME, get_service_name
from api.common.pricing import PHONE_LOOKUP_PRICE, get_user_price
from database.search_engine import SearchEngine


router = APIRouter(tags=["Phone Lookup"])
logger = logging.getLogger(__name__)


# ============================================
# Helper Functions
# ============================================

def extract_person_data_from_searchbug(searchbug_data: dict) -> dict:
    """Extract person data from SearchBug API response."""
    if not searchbug_data:
        return {}

    # Extract names
    names = searchbug_data.get('names', [])
    firstname = None
    lastname = None
    middlename = None

    if names:
        first_name_entry = names[0] if isinstance(names, list) else names
        if isinstance(first_name_entry, dict):
            firstname = first_name_entry.get('first_name') or first_name_entry.get('firstname')
            lastname = first_name_entry.get('last_name') or first_name_entry.get('lastname')
            middlename = first_name_entry.get('middle_name') or first_name_entry.get('middlename')

    # Extract DOB
    dob = searchbug_data.get('dob', '')
    if isinstance(dob, dict):
        dob = dob.get('date', '')

    # Extract primary address
    addresses = searchbug_data.get('addresses', [])
    primary_address = {}
    if addresses and isinstance(addresses, list) and len(addresses) > 0:
        primary_address = addresses[0] if isinstance(addresses[0], dict) else {}

    # Extract primary email
    emails = searchbug_data.get('emails', [])
    primary_email = None
    if emails and isinstance(emails, list) and len(emails) > 0:
        email_entry = emails[0]
        if isinstance(email_entry, dict):
            primary_email = email_entry.get('email') or email_entry.get('email_address')
        elif isinstance(email_entry, str):
            primary_email = email_entry

    return {
        'firstname': firstname,
        'lastname': lastname,
        'middlename': middlename,
        'dob': dob,
        'address': primary_address.get('full_street') or primary_address.get('address'),
        'city': primary_address.get('city'),
        'state': primary_address.get('state'),
        'zip_code': primary_address.get('zip_code') or primary_address.get('zip'),
        'email': primary_email,
    }


def extract_search_params_from_searchbug(searchbug_data: dict) -> dict:
    """Extract search parameters for local SSN database search."""
    if not searchbug_data:
        return {}

    # Extract names
    names = searchbug_data.get('names', [])
    firstname = None
    lastname = None

    if names:
        first_name_entry = names[0] if isinstance(names, list) else names
        if isinstance(first_name_entry, dict):
            firstname = first_name_entry.get('first_name') or first_name_entry.get('firstname')
            lastname = first_name_entry.get('last_name') or first_name_entry.get('lastname')

    # Extract all ZIPs
    addresses = searchbug_data.get('addresses', [])
    all_zips = []
    all_addresses = []
    all_states = []

    for addr in addresses:
        if isinstance(addr, dict):
            zip_code = addr.get('zip_code') or addr.get('zip')
            if zip_code and zip_code not in all_zips:
                all_zips.append(str(zip_code).split('-')[0])  # Remove +4

            full_street = addr.get('full_street') or addr.get('address')
            if full_street and full_street not in all_addresses:
                all_addresses.append(full_street)

            state = addr.get('state')
            if state and state not in all_states:
                all_states.append(state)

    # Extract all phones
    phones = searchbug_data.get('phones', [])
    all_phones = []
    for p in phones:
        if isinstance(p, dict):
            phone_number = p.get('phone_number') or p.get('number')
            if phone_number:
                # Clean phone number
                phone_clean = ''.join(filter(str.isdigit, str(phone_number)))
                if phone_clean and phone_clean not in all_phones:
                    all_phones.append(phone_clean)

    return {
        'firstname': firstname,
        'lastname': lastname,
        'all_zips': all_zips,
        'all_phones': all_phones,
        'all_addresses': all_addresses,
        'all_states': all_states,
    }


# ============================================
# API Endpoints
# ============================================

@router.get("/services", response_model=DaisySMSServicesResponse)
async def get_services(
    current_user: User = Depends(get_current_user),
):
    """
    Get list of available services for phone lookup dropdown.

    Returns cached list of 500+ services from DaisySMS.
    """
    try:
        async with create_daisysms_client() as client:
            services_data = await client.get_services()

        services = [
            DaisySMSService(
                code=s['code'],
                name=s['name'],
                price=s.get('price')
            )
            for s in services_data
        ]

        return DaisySMSServicesResponse(services=services)

    except DaisySMSError as e:
        logger.error(f"Failed to get services: {e.message}")
        # Return fallback static list
        from api.common.daisysms_services import ALL_SERVICE_CODES
        services = [
            DaisySMSService(code=code, name=get_service_name(code))
            for code in sorted(ALL_SERVICE_CODES, key=lambda x: get_service_name(x).lower())
        ]
        return DaisySMSServicesResponse(services=services)

    except Exception as e:
        logger.error(f"Unexpected error getting services: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to load services list"
        )


@router.post("/search", response_model=PhoneLookupResponse)
async def phone_lookup_search(
    request: PhoneLookupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session),
):
    """
    Perform phone lookup search.

    Flow:
    1. Get phone number from DaisySMS for selected service
    2. Search SearchBug by phone number
    3. Match against local SSN database
    4. Charge user $3.00 only if SSN is found
    5. Return combined results
    """
    logger.info(f"Phone Lookup: user={current_user.username}, service={request.service_code}")

    # Check if user is banned
    if current_user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is banned"
        )

    # Get custom price for user
    phone_lookup_price = await get_user_price(
        db=db,
        access_code=current_user.access_code or '',
        service_name='phone_lookup',
        default_price=PHONE_LOOKUP_PRICE
    )

    # Check balance
    if current_user.balance < phone_lookup_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${phone_lookup_price}, Available: ${current_user.balance}"
        )

    # Create search log
    search_log = PhoneLookupSearch(
        user_id=current_user.id,
        service_code=request.service_code,
        success=False,
        ssn_found=False,
        source=RequestSource.web,
    )
    db.add(search_log)
    await db.commit()
    await db.refresh(search_log)

    phone_id = None
    phone_number = None
    rental = None

    try:
        # Step 1: Get phone from DaisySMS
        async with create_daisysms_client() as daisysms:
            phone_id, phone_number = await daisysms.get_number(request.service_code)

        logger.info(f"Got phone from DaisySMS: {phone_number} (ID: {phone_id})")

        # Update search log
        search_log.phone_number = phone_number

        # Create phone rental record
        service_name = get_service_name(request.service_code)
        rental = PhoneRental(
            user_id=current_user.id,
            daisysms_id=phone_id,
            phone_number=phone_number,
            service_code=request.service_code,
            service_name=service_name,
            status=PhoneRentalStatus.active,
            expires_at=datetime.utcnow() + timedelta(minutes=20),  # Default 20 min rental
        )
        db.add(rental)
        await db.commit()
        await db.refresh(rental)

        search_log.rental_id = rental.id
        await db.commit()

        # Step 2: Search SearchBug by phone
        searchbug_data = None
        try:
            async with create_searchbug_client() as searchbug:
                searchbug_data = await searchbug.search_person_by_phone(phone_number)
        except SearchbugAPIError as e:
            logger.error(f"SearchBug error: {e.message}")
            # Don't fail - just continue without SearchBug data

        if not searchbug_data:
            # No data in SearchBug - finish rental, don't charge
            async with create_daisysms_client() as daisysms:
                await daisysms.finish_number(phone_id)

            rental.status = PhoneRentalStatus.finished
            search_log.success = True
            search_log.error_message = "No person data found in SearchBug"
            await db.commit()

            return PhoneLookupResponse(
                success=True,
                phone_number=phone_number,
                rental_id=str(rental.id),
                daisysms_id=phone_id,
                person_data=None,
                message="No person data found for this phone number",
                new_balance=float(current_user.balance)
            )

        # Save SearchBug data to rental
        rental.searchbug_data = searchbug_data
        await db.commit()

        # Extract person data
        person_info = extract_person_data_from_searchbug(searchbug_data)

        # Step 3: Search local SSN database
        search_params = extract_search_params_from_searchbug(searchbug_data)
        search_params['all_phones'] = [phone_number] + search_params.get('all_phones', [])

        search_engine = SearchEngine(db_path=SQLITE_PATH)
        ssn_matches = []

        if search_params.get('firstname') and search_params.get('lastname'):
            ssn_matches = search_engine.search_by_searchbug_data(
                firstname=search_params['firstname'],
                lastname=search_params['lastname'],
                all_zips=search_params.get('all_zips', []),
                all_phones=search_params.get('all_phones', []),
                all_addresses=search_params.get('all_addresses', []),
                all_states=search_params.get('all_states', []),
            )

        logger.info(f"Found {len(ssn_matches)} SSN match(es)")

        # Build result
        ssn_data = ssn_matches[0] if ssn_matches else None
        result = PhoneLookupResult(
            phone_number=phone_number,
            firstname=person_info.get('firstname'),
            lastname=person_info.get('lastname'),
            middlename=person_info.get('middlename'),
            dob=person_info.get('dob'),
            address=person_info.get('address'),
            city=person_info.get('city'),
            state=person_info.get('state'),
            zip_code=person_info.get('zip_code'),
            email=person_info.get('email'),
            ssn=ssn_data.get('ssn') if ssn_data else None,
            ssn_found=len(ssn_matches) > 0,
            local_db_data=ssn_data,
        )

        # Update rental with SSN data
        rental.ssn_found = len(ssn_matches) > 0
        rental.ssn_data = ssn_data

        # Finish DaisySMS rental
        async with create_daisysms_client() as daisysms:
            await daisysms.finish_number(phone_id)

        rental.status = PhoneRentalStatus.finished

        # Charge user and create order only if SSN found
        if ssn_matches:
            current_user.balance -= phone_lookup_price
            await db.commit()
            await db.refresh(current_user)

            # Create order
            order_items = [{
                "phone_number": phone_number,
                "ssn": result.ssn,
                "firstname": result.firstname,
                "lastname": result.lastname,
                "dob": result.dob,
                "address": result.address,
                "city": result.city,
                "state": result.state,
                "zip": result.zip_code,
                "email": result.email,
                "price": str(phone_lookup_price),
                "source": "phone_lookup",
                "service_code": request.service_code,
                "service_name": service_name,
            }]

            new_order = Order(
                user_id=current_user.id,
                items=order_items,
                total_price=phone_lookup_price,
                status=OrderStatus.completed,
                order_type=OrderType.phone_lookup,
                is_viewed=False,
            )
            db.add(new_order)
            await db.commit()
            await db.refresh(new_order)

            # Update rental and search log
            rental.order_id = new_order.id
            search_log.success = True
            search_log.ssn_found = True
            search_log.order_id = new_order.id
            search_log.user_charged = phone_lookup_price
            await db.commit()

            return PhoneLookupResponse(
                success=True,
                phone_number=phone_number,
                rental_id=str(rental.id),
                daisysms_id=phone_id,
                person_data=result,
                message="SSN found",
                new_balance=float(current_user.balance),
                order_id=str(new_order.id),
                charged_amount=float(phone_lookup_price),
            )
        else:
            search_log.success = True
            search_log.ssn_found = False
            await db.commit()

            return PhoneLookupResponse(
                success=True,
                phone_number=phone_number,
                rental_id=str(rental.id),
                daisysms_id=phone_id,
                person_data=result,
                message="No SSN found for this phone number",
                new_balance=float(current_user.balance),
            )

    except DaisySMSNoNumbersError:
        search_log.error_message = "No numbers available"
        await db.commit()

        return PhoneLookupResponse(
            success=False,
            error="NO_NUMBERS",
            message="No phone numbers available for this service. Try another service.",
            new_balance=float(current_user.balance),
        )

    except DaisySMSBalanceError:
        search_log.error_message = "DaisySMS balance insufficient"
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. Please try again later."
        )

    except DaisySMSBadServiceError:
        search_log.error_message = f"Invalid service code: {request.service_code}"
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid service code: {request.service_code}"
        )

    except DaisySMSError as e:
        search_log.error_message = f"DaisySMS error: {e.message}"
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Phone service error: {e.message}"
        )

    except Exception as e:
        # Cancel DaisySMS number on any error
        if phone_id:
            try:
                async with create_daisysms_client() as daisysms:
                    await daisysms.cancel_number(phone_id)
            except Exception:
                pass

        if rental:
            rental.status = PhoneRentalStatus.cancelled

        logger.error(f"Phone Lookup error: {e}", exc_info=True)
        search_log.error_message = str(e)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/rentals", response_model=PhoneRentalsListResponse)
async def get_rentals(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session),
):
    """
    Get user's phone rental history.
    """
    # Query rentals
    query = (
        select(PhoneRental)
        .where(PhoneRental.user_id == current_user.id)
        .order_by(desc(PhoneRental.created_at))
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    rentals = result.scalars().all()

    # Count total
    count_query = (
        select(PhoneRental)
        .where(PhoneRental.user_id == current_user.id)
    )
    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    # Build response
    rental_responses = []
    for r in rentals:
        # Build person_data from searchbug_data and ssn_data
        person_data = None
        if r.searchbug_data or r.ssn_data:
            person_info = extract_person_data_from_searchbug(r.searchbug_data or {})
            person_data = {
                **person_info,
                'ssn': r.ssn_data.get('ssn') if r.ssn_data else None,
                'ssn_found': r.ssn_found,
            }

        rental_responses.append(PhoneRentalResponse(
            id=str(r.id),
            daisysms_id=r.daisysms_id,
            phone_number=r.phone_number,
            service_code=r.service_code,
            service_name=r.service_name,
            status=r.status.value,
            ssn_found=r.ssn_found,
            person_data=person_data,
            created_at=r.created_at.isoformat(),
            expires_at=r.expires_at.isoformat() if r.expires_at else None,
        ))

    return PhoneRentalsListResponse(rentals=rental_responses, total=total)


@router.post("/rentals/{rental_id}/renew", response_model=PhoneRentalRenewResponse)
async def renew_rental(
    rental_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session),
):
    """
    Renew (extend) a phone rental.

    This uses DaisySMS getExtraActivation to extend the rental time.
    """
    # Find rental
    try:
        rental_uuid = UUID(rental_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rental ID"
        )

    query = select(PhoneRental).where(
        PhoneRental.id == rental_uuid,
        PhoneRental.user_id == current_user.id,
    )
    result = await db.execute(query)
    rental = result.scalar_one_or_none()

    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rental not found"
        )

    # Try to renew via DaisySMS
    try:
        async with create_daisysms_client() as daisysms:
            success = await daisysms.get_extra_activation(
                rental.daisysms_id,
                rental.service_code
            )

        if success:
            rental.status = PhoneRentalStatus.active
            rental.renewed_at = datetime.utcnow()
            rental.expires_at = datetime.utcnow() + timedelta(minutes=20)
            await db.commit()

            return PhoneRentalRenewResponse(
                success=True,
                rental_id=str(rental.id),
                new_expires_at=rental.expires_at.isoformat(),
                message="Rental renewed successfully"
            )
        else:
            return PhoneRentalRenewResponse(
                success=False,
                rental_id=str(rental.id),
                error="RENEW_FAILED",
                message="Failed to renew rental. The number may have expired."
            )

    except DaisySMSBalanceError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable (insufficient balance)"
        )

    except DaisySMSError as e:
        return PhoneRentalRenewResponse(
            success=False,
            rental_id=str(rental.id),
            error=e.error_code or "RENEW_ERROR",
            message=f"Failed to renew: {e.message}"
        )


@router.post("/rentals/{rental_id}/cancel", response_model=PhoneRentalRenewResponse)
async def cancel_rental(
    rental_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session),
):
    """
    Cancel a phone rental (get refund from DaisySMS).
    """
    # Find rental
    try:
        rental_uuid = UUID(rental_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid rental ID"
        )

    query = select(PhoneRental).where(
        PhoneRental.id == rental_uuid,
        PhoneRental.user_id == current_user.id,
    )
    result = await db.execute(query)
    rental = result.scalar_one_or_none()

    if not rental:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rental not found"
        )

    if rental.status != PhoneRentalStatus.active:
        return PhoneRentalRenewResponse(
            success=False,
            rental_id=str(rental.id),
            error="NOT_ACTIVE",
            message="Can only cancel active rentals"
        )

    # Cancel via DaisySMS
    try:
        async with create_daisysms_client() as daisysms:
            success = await daisysms.cancel_number(rental.daisysms_id)

        if success:
            rental.status = PhoneRentalStatus.cancelled
            await db.commit()

            return PhoneRentalRenewResponse(
                success=True,
                rental_id=str(rental.id),
                message="Rental cancelled successfully"
            )
        else:
            return PhoneRentalRenewResponse(
                success=False,
                rental_id=str(rental.id),
                error="CANCEL_FAILED",
                message="Failed to cancel rental"
            )

    except DaisySMSError as e:
        return PhoneRentalRenewResponse(
            success=False,
            rental_id=str(rental.id),
            error=e.error_code or "CANCEL_ERROR",
            message=f"Failed to cancel: {e.message}"
        )
