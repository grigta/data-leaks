"""
Search router for Public API (integration with SearchEngine).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from typing import List, Dict, Any, Optional, Set
import json
import logging
import asyncio
import os
import random
import time
from decimal import Decimal
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from database.search_engine_factory import get_search_engine
# DataManager removed - using ClickHouse only
from api.common.database import get_postgres_session, async_session_maker
from api.common.models_sqlite import (
    SSNRecord, SearchBySSNRequest, SearchByNameRequest,
    InstantSSNRequest, InstantSSNResponse, InstantSSNResult,
    DebugFlowRequest, DebugFlowResponse, BloomKeyResult, SearchKeyResult, CandidateResult,
    TestSearchResponse, TestSearchHistoryItem, TestSearchHistoryResponse,
    SearchDBRequest, SearchDBResponse, SearchDBRecord,
    UnifiedSearchRequest, UnifiedSearchResponse
)
from api.public.dependencies import get_current_user, limiter
from api.common.models_postgres import User, Order, OrderStatus, OrderType, InstantSSNSearch, InstantSSNAbuseTracking, ManualSSNTicket, TicketStatus, RequestSource, TestSearchHistory
from api.common.searchbug_client import create_searchbug_client, create_searchbug_client_dynamic, SearchbugAPIError
from api.common.searchbug_cache import SearchBugCacheService
# from api.common.whitepages_client import create_whitepages_client, WhitepagesAPIError  # temporarily disabled
from api.common.validators import validate_ssn
from api.common.sanitizers import sanitize_name, sanitize_address, sanitize_metadata
from sqlalchemy import select, desc, update
from api.common.pricing import INSTANT_SSN_PRICE, MANUAL_SSN_PRICE, REVERSE_SSN_PRICE, SEARCHBUG_API_COST, check_maintenance_mode, get_user_price, get_search_flow, parse_search_flow
from api.public.websocket import publish_user_notification, WebSocketEventType
from uuid import UUID


router = APIRouter()
logger = logging.getLogger(__name__)


def log_search_request(user: User, endpoint: str, params: dict, result_count: int):
    """
    Log search request with masked sensitive data.

    Args:
        user: Current authenticated user
        endpoint: Endpoint name
        params: Search parameters
        result_count: Number of results found
    """
    # Mask sensitive data
    masked_params = params.copy()

    # Mask SSN (show last 4 digits)
    if 'ssn' in masked_params:
        ssn = masked_params['ssn']
        masked_params['ssn'] = f"***-**-{ssn[-4:]}" if len(ssn) >= 4 else "****"

    # Mask last4ssn
    if 'last4ssn' in masked_params:
        masked_params['last4ssn'] = '****'

    # Mask email (show first char + domain)
    if 'email' in masked_params:
        email = masked_params['email']
        if '@' in email:
            parts = email.split('@')
            masked_params['email'] = f"{parts[0][0]}***@{parts[1]}"
        else:
            masked_params['email'] = "***"

    logger.info(
        f"User {user.id} ({user.username}) searched {endpoint} with params {masked_params}, "
        f"found {result_count} results"
    )


def normalize_dob(dob: str) -> str:
    """
    Нормализует дату рождения в формат YYYYMMDD.

    Поддерживает различные форматы:
    - YYYYMMDD (уже нормализован)
    - YYYY-MM-DD (с дефисами)
    - MM/DD/YYYY (американский формат)
    - Другие форматы с разделителями

    Args:
        dob: Дата рождения в любом формате

    Returns:
        Нормализованная дата в формате YYYYMMDD или пустая строка
    """
    if not dob or not isinstance(dob, str):
        return ''

    # ВАЖНО: Сначала проверяем разделители в ИСХОДНОЙ строке
    # Если формат MM/DD/YYYY или подобный (с разделителями)
    if '/' in dob or '-' in dob:
        parts = dob.replace('/', '-').split('-')
        if len(parts) == 3:
            # Определяем формат по длине первой части
            if len(parts[0]) == 4:  # YYYY-MM-DD
                year, month, day = parts[0], parts[1], parts[2]
            else:  # MM-DD-YYYY или DD-MM-YYYY
                month, day, year = parts[0], parts[1], parts[2]

            # Формируем YYYYMMDD
            try:
                return f"{year.zfill(4)}{month.zfill(2)}{day.zfill(2)}"
            except:
                pass

    # ТОЛЬКО ПОСЛЕ проверки разделителей удаляем символы кроме цифр
    dob_digits = ''.join(filter(str.isdigit, dob))

    # Если пустое - возвращаем пустую строку
    if not dob_digits:
        return ''

    # Если уже в формате YYYYMMDD (8 цифр без разделителей)
    if len(dob_digits) == 8:
        return dob_digits

    # Если не удалось распарсить - возвращаем как есть (только цифры)
    return dob_digits if len(dob_digits) >= 6 else ''


def filter_by_dob(ssn_matches: List[dict], external_dob: str) -> List[dict]:
    """
    Фильтрует SSN совпадения по дате рождения.

    Логика фильтрации:
    - Если DOB пустой - не фильтруем (возвращаем все записи)
    - Если DOB пустой в локальной записи - пропускаем запись
    - Сравнивает полностью (год + месяц + день) после нормализации
    - Если после фильтрации ничего не осталось - возвращает все исходные результаты

    Args:
        ssn_matches: Список найденных SSN записей из локальной БД
        external_dob: Дата рождения из внешнего API

    Returns:
        Отфильтрованный список SSN записей
    """
    # Если нет совпадений или только одно - не фильтруем
    if len(ssn_matches) <= 1:
        return ssn_matches

    # Нормализуем DOB из внешнего API
    normalized_external_dob = normalize_dob(external_dob)

    # Если DOB пустой - не фильтруем
    if not normalized_external_dob:
        logger.info("External DOB is empty, skipping DOB filter")
        return ssn_matches

    logger.info(f"Filtering {len(ssn_matches)} SSN matches by DOB: {normalized_external_dob}")

    # Фильтруем по совпадению DOB
    filtered = []
    for record in ssn_matches:
        local_dob = record.get('dob', '')
        normalized_local_dob = normalize_dob(local_dob)

        # Если DOB пустой в локальной записи - пропускаем
        if not normalized_local_dob:
            logger.debug(f"Skipping record (empty local DOB): SSN={record.get('ssn')}")
            continue

        # Сравниваем нормализованные DOB
        if normalized_external_dob == normalized_local_dob:
            filtered.append(record)
            logger.debug(f"Keeping record (DOB match): SSN={record.get('ssn')}, DOB={normalized_local_dob}")
        else:
            logger.debug(f"Filtering out record (DOB mismatch): SSN={record.get('ssn')}, "
                        f"local DOB={normalized_local_dob}, external DOB={normalized_external_dob}")

    # Если после фильтрации ничего не осталось - возвращаем все исходные
    if not filtered:
        logger.info("No matches after DOB filter, returning all original results")
        return ssn_matches

    logger.info(f"After DOB filter: {len(filtered)} match(es) remaining")
    return filtered


def check_user_ban(user: User):
    """
    Проверяет, забанен ли пользователь.

    Args:
        user: Текущий пользователь

    Raises:
        HTTPException: Если пользователь забанен
    """
    if user.is_banned:
        ban_reason = user.ban_reason or "Account banned for abuse"
        logger.warning(f"Banned user {user.username} attempted to search")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account banned: {ban_reason}"
        )


async def check_abuse_patterns(
    db: AsyncSession,
    user_id: UUID,
    firstname: str,
    lastname: str,
    address: str,
    dob: str,
    ssn_found: bool
) -> tuple[bool, str]:
    """
    Проверяет паттерны злоупотреблений - строго 3 нарушения подряд.

    ВАЖНО: Вызывается ДО записи текущего запроса в таблицу abuse tracking.
    Функция считает только предыдущие записи и добавляет текущий запрос к счётчику.

    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        firstname: Имя для поиска
        lastname: Фамилия для поиска
        address: Адрес для поиска
        dob: Дата рождения (может быть пустой)
        ssn_found: Найден ли SSN

    Returns:
        Tuple (is_abuse, reason): True если обнаружен паттерн злоупотребления
    """
    # Получаем последние записи для пользователя (больше чем 3 для анализа последовательности)
    stmt = (
        select(InstantSSNAbuseTracking)
        .where(InstantSSNAbuseTracking.user_id == user_id)
        .order_by(desc(InstantSSNAbuseTracking.created_at))
        .limit(10)
    )
    result = await db.execute(stmt)
    last_records = result.scalars().all()

    # Проверка паттерна 1: полный диапазон DOB (1990-2025) 3 раза подряд
    # Проходим по записям в порядке убывания created_at и считаем непрерывную последовательность
    full_dob_range_count = 0
    for record in last_records:
        # Проверяем, является ли запись поиском по полному диапазону DOB
        is_full_dob_search = (
            record.abuse_type == 'full_dob_range' or
            (not record.search_params.get('dob') or record.search_params.get('dob', '').strip() == '')
        )

        if is_full_dob_search:
            full_dob_range_count += 1
        else:
            # Прерываем последовательность при первой записи с указанным DOB
            break

    # Добавляем текущий запрос к счётчику, если у него DOB пустой или отсутствует
    if not dob or dob.strip() == '':
        full_dob_range_count += 1

    if full_dob_range_count >= 3:
        return True, "Banned for searching full DOB range 3 times in a row"

    # Проверка паттерна 2: одна и та же фулка не найдена 3 раза подряд
    # Нормализуем текущие параметры (ПОЛЬЗОВАТЕЛЬСКИЙ ВВОД)
    normalized_firstname = firstname.lower().strip()
    normalized_lastname = lastname.lower().strip()
    normalized_address = address.lower().strip()

    same_not_found_count = 0
    for record in last_records:
        # Проверяем совпадение параметров поиска
        # ВАЖНО: search_params содержит ПОЛЬЗОВАТЕЛЬСКИЙ ВВОД, сохранённый в log_abuse_tracking
        # Сравниваем пользовательский ввод с пользовательским вводом (не нормализованные данные внешнего API)
        search_params = record.search_params
        record_firstname = search_params.get('firstname', '').lower().strip()
        record_lastname = search_params.get('lastname', '').lower().strip()
        record_address = search_params.get('address', '').lower().strip()
        record_ssn_found = search_params.get('ssn_found', False)

        # Проверяем, совпадают ли параметры И SSN не был найден
        if (record_firstname == normalized_firstname and
            record_lastname == normalized_lastname and
            record_address == normalized_address and
            not record_ssn_found):
            same_not_found_count += 1
        else:
            # Прерываем последовательность при первой записи с другими параметрами или с найденным SSN
            break

    # Добавляем текущий запрос к счётчику, если SSN не найден и параметры те же
    if not ssn_found:
        same_not_found_count += 1

    if same_not_found_count >= 3:
        return True, "Banned for searching same fullname not found 3 times in a row"

    return False, ""


async def log_abuse_tracking(
    db: AsyncSession,
    user_id: UUID,
    search_params: dict,
    abuse_type: str,
    is_abuse: bool,
    consecutive_count: int
):
    """
    Записывает информацию о поиске в таблицу abuse tracking.

    Args:
        db: Сессия базы данных
        user_id: ID пользователя
        search_params: Параметры поиска
        abuse_type: Тип злоупотребления ('full_dob_range' или 'same_not_found')
        is_abuse: Является ли это злоупотреблением
        consecutive_count: Количество последовательных нарушений
    """
    tracking_entry = InstantSSNAbuseTracking(
        user_id=user_id,
        search_params=search_params,
        abuse_type=abuse_type,
        is_abuse=is_abuse,
        consecutive_count=consecutive_count
    )
    db.add(tracking_entry)
    await db.commit()
    logger.info(f"Logged abuse tracking: user={user_id}, type={abuse_type}, is_abuse={is_abuse}")


async def ban_user(db: AsyncSession, user: User, reason: str):
    """
    Банит пользователя.

    Args:
        db: Сессия базы данных
        user: Пользователь для бана
        reason: Причина бана
    """
    user.is_banned = True
    user.ban_reason = reason
    user.banned_at = datetime.utcnow()
    await db.commit()
    logger.warning(f"User {user.username} (ID: {user.id}) has been banned: {reason}")


def deduplicate_by_ssn(records: List[dict]) -> List[dict]:
    """
    Удаляет дубликаты записей по SSN, оставляя запись с наиболее полными данными.

    Логика дедупликации:
    - Группирует все записи по SSN
    - Для каждого уникального SSN оставляет только одну запись
    - При выборе между дубликатами предпочитает запись с большим количеством заполненных полей
    - Логирует количество найденных и удаленных дубликатов

    Args:
        records: Список записей (dict) с полем 'ssn'

    Returns:
        Список уникальных записей без дубликатов SSN
    """
    if not records or len(records) <= 1:
        return records

    # Группируем записи по SSN
    ssn_groups = {}
    for record in records:
        ssn = record.get('ssn')
        if not ssn:
            # Записи без SSN пропускаем (не должно быть, но на всякий случай)
            continue

        if ssn not in ssn_groups:
            ssn_groups[ssn] = []
        ssn_groups[ssn].append(record)

    # Подсчитываем дубликаты
    total_duplicates = sum(len(group) - 1 for group in ssn_groups.values() if len(group) > 1)

    if total_duplicates > 0:
        logger.info(f"Found {total_duplicates} duplicate SSN record(s) across {len(ssn_groups)} unique SSN(s)")

    # Для каждого SSN выбираем лучшую запись
    unique_records = []
    for ssn, group in ssn_groups.items():
        if len(group) == 1:
            # Нет дубликатов для этого SSN
            unique_records.append(group[0])
        else:
            # Есть дубликаты - выбираем запись с наибольшим количеством заполненных полей
            best_record = max(
                group,
                key=lambda r: sum(1 for v in r.values() if v and str(v).strip())
            )
            unique_records.append(best_record)
            logger.debug(
                f"Deduplicated SSN {ssn}: kept 1 record out of {len(group)} duplicates "
                f"(source_table: {best_record.get('source_table', 'unknown')})"
            )

    logger.info(f"After deduplication: {len(unique_records)} unique record(s) (removed {total_duplicates} duplicate(s))")
    return unique_records


async def _call_external_api(
    provider: str,
    firstname: str,
    lastname: str,
    address: str,
    db: AsyncSession,
) -> Optional[Dict[str, Any]]:
    """Call external API (searchbug or whitepages). Returns normalized person data or None."""
    if provider == "sb":
        cache_service = SearchBugCacheService(db)
        async with await create_searchbug_client_dynamic(db) as searchbug:
            return await cache_service.search_person_unified_cached(
                searchbug_client=searchbug,
                firstname=firstname,
                lastname=lastname,
                address=address,
            )
    # elif provider == "wp":  # temporarily disabled
    #     async with create_whitepages_client() as wp:
    #         return await wp.search_person_unified(
    #             firstname=firstname,
    #             lastname=lastname,
    #             address=address,
    #         )
    return None


def _extract_api_data(
    api_data: Dict[str, Any],
    request_firstname: str,
    request_lastname: str,
) -> Dict[str, Any]:
    """Extract and prepare data from API response for ClickHouse search."""
    primary_address = api_data.get('primary_address')
    primary_phone = api_data.get('primary_phone')
    primary_email = api_data.get('primary_email')
    names = api_data.get('names', [])
    dob = api_data.get('dob', '')
    report_token = api_data.get('report_token', '')
    all_zips = api_data.get('all_zips', [])
    all_phones = api_data.get('all_phones', [])
    addresses = api_data.get('addresses', [])

    # Get enriched name from API
    firstname = request_firstname
    lastname = request_lastname
    middlename = None
    if names and len(names) > 0:
        firstname = names[0].get('first_name', request_firstname)
        lastname = names[0].get('last_name', request_lastname)
        middlename = names[0].get('middle_name')

    # Extract addresses
    all_addresses = []
    all_states = []
    if addresses and len(addresses) > 0:
        for addr in addresses:
            full_street = addr.get('full_street', '')
            if full_street:
                all_addresses.append(full_street)
            state = addr.get('state', '')
            if state and state not in all_states:
                all_states.append(state)

    # Extract phone numbers
    phone_numbers = []
    if all_phones and len(all_phones) > 0:
        for phone_obj in all_phones:
            if isinstance(phone_obj, dict):
                phone_num = phone_obj.get('phone_number', '')
                if phone_num:
                    phone_numbers.append(phone_num)
            elif isinstance(phone_obj, str):
                phone_numbers.append(phone_obj)

    # Prepare addresses with state
    addresses_with_state = []
    if addresses and len(addresses) > 0:
        for addr in addresses:
            full_street = addr.get('full_street', '')
            state = addr.get('state', '')
            if full_street and state:
                addresses_with_state.append({'address': full_street, 'state': state})

    sb_primary_street = ''
    if primary_address and isinstance(primary_address, dict):
        sb_primary_street = primary_address.get('full_street', '')

    return {
        'primary_address': primary_address,
        'primary_phone': primary_phone,
        'primary_email': primary_email,
        'names': names,
        'dob': dob,
        'report_token': report_token,
        'firstname': firstname,
        'lastname': lastname,
        'middlename': middlename,
        'all_zips': all_zips,
        'phone_numbers': phone_numbers,
        'all_addresses': all_addresses,
        'all_states': all_states,
        'addresses_with_state': addresses_with_state,
        'sb_primary_street': sb_primary_street,
    }


def _run_clickhouse_search(
    extracted: Dict[str, Any],
    request_address: str,
) -> List[Dict[str, Any]]:
    """Run ClickHouse two-level search + fallbacks. Returns list of SSN matches."""
    search_engine = get_search_engine()

    searchbug_search_data = {
        'names': extracted['names'],
        'firstname': extracted['firstname'],
        'middlename': extracted['middlename'],
        'lastname': extracted['lastname'],
        'dob': extracted['dob'],
        'phones': extracted['phone_numbers'],
        'addresses': extracted['addresses_with_state'],
    }

    ssn_matches = search_engine.search_by_searchbug_two_level(
        searchbug_data=searchbug_search_data,
        input_address=request_address,
        searchbug_primary_address=extracted['sb_primary_street'],
    )

    # Fallback to original search if two-level returns nothing
    if not ssn_matches:
        logger.info("Two-level search returned no results, trying fallback search")
        ssn_matches = search_engine.search_by_searchbug_data(
            firstname=extracted['firstname'],
            lastname=extracted['lastname'],
            all_zips=extracted['all_zips'],
            all_phones=extracted['phone_numbers'],
            all_addresses=extracted['all_addresses'],
            all_addresses_with_state=extracted['addresses_with_state'],
            all_states=extracted['all_states'],
        )

    logger.info(f"Found {len(ssn_matches)} SSN match(es) in local database")

    # Deduplication
    ssn_matches = deduplicate_by_ssn(ssn_matches)
    logger.info(f"After deduplication: {len(ssn_matches)} unique SSN(s)")

    # Take only the best (first) result
    if len(ssn_matches) > 1:
        logger.info(f"Taking only the best match out of {len(ssn_matches)}")
        ssn_matches = ssn_matches[:1]

    # Fallback: address + DOB + firstname (for name mismatch cases)
    dob = extracted['dob']
    if not ssn_matches and dob and extracted['all_addresses']:
        logger.info("No matches with firstname+lastname, trying address+DOB+firstname fallback")
        try:
            fallback_matches = search_engine.search_by_address_dob_firstname(
                addresses=extracted['all_addresses'],
                dob=dob,
                firstname=extracted['firstname'],
            )
            if fallback_matches:
                logger.info(f"Fallback successful: found {len(fallback_matches)} match(es)")
                ssn_matches = fallback_matches
            else:
                logger.info("Fallback: no matches by address+DOB+firstname")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error during fallback search: {e}", exc_info=True)

    return ssn_matches


@router.post("/name", response_model=List[SSNRecord])
# @limiter.limit("100/hour")
async def search_by_name(
    req: Request,
    response: Response,
    request: SearchByNameRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Search SSN records by name with ZIP or address.

    Supports only two search combinations:
    1. firstname + lastname + zip
    2. firstname + lastname + address

    Args:
        req: FastAPI request object (required by SlowAPI)
        response: FastAPI response object (required by SlowAPI)
        request: Search request with firstname, lastname, and either zip or address
        current_user: Current authenticated user

    Returns:
        List of matching SSN records (with email/phone hidden, only counts shown)

    Raises:
        HTTPException: If neither zip nor address is provided
    """
    search_engine = get_search_engine()

    # Sanitize input values for safety
    firstname_s = sanitize_name(request.firstname) or request.firstname
    lastname_s = sanitize_name(request.lastname) or request.lastname
    zip_s = request.zip.strip() if request.zip else None
    address_s = sanitize_address(request.address) if request.address else None

    # Determine search type and perform search
    if zip_s:
        # Search by name + zip
        results_json = search_engine.search_by_name_zip(
            firstname_s,
            lastname_s,
            zip_s,
            limit=request.limit
        )
        search_params = sanitize_metadata({
            'firstname': firstname_s,
            'lastname': lastname_s,
            'zip': zip_s
        }) or {}
    elif address_s:
        # Search by name + address
        results_json = search_engine.search_by_name_address(
            firstname_s,
            lastname_s,
            address_s,
            limit=request.limit
        )
        search_params = sanitize_metadata({
            'firstname': firstname_s,
            'lastname': lastname_s,
            'address': address_s
        }) or {}
    else:
        # Neither zip nor address provided
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'zip' or 'address' must be provided along with firstname and lastname"
        )

    results = json.loads(results_json)

    # Remove duplicate SSNs
    results = deduplicate_by_ssn(results)

    # Log the search
    log_search_request(current_user, "search_by_name", search_params, len(results))

    # Convert to Pydantic models and hide sensitive data
    records = []
    for record in results:
        # Count email and phone (check if not empty string)
        email_value = record.get('email', '')
        phone_value = record.get('phone', '')
        email_count = 1 if email_value and email_value.strip() else 0
        phone_count = 1 if phone_value and phone_value.strip() else 0

        # Hide actual email and phone
        record['email'] = None
        record['phone'] = None
        record['email_count'] = email_count
        record['phone_count'] = phone_count

        records.append(SSNRecord(**record))

    return records


@router.get("/record/{ssn}", response_model=SSNRecord)
async def get_record(
    ssn: str,
    req: Request,
    response: Response,
    current_user: User = Depends(get_current_user)
):
    """
    Get full SSN record by SSN.

    Args:
        req: FastAPI request object (required by SlowAPI)
        response: FastAPI response object (required by SlowAPI)
        ssn: SSN to search for
        current_user: Current authenticated user

    Returns:
        SSN record (with email/phone hidden, only counts shown)

    Raises:
        HTTPException: If record not found or SSN format is invalid
    """
    # Validate SSN format before database query
    is_valid, error = validate_ssn(ssn)
    if not is_valid:
        logger.warning(f"Invalid SSN format rejected in get_record: {ssn[:20] if len(ssn) > 20 else ssn}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error
        )

    # Search in ClickHouse
    search_engine = get_search_engine()
    results_json = search_engine.search_by_ssn(ssn, limit=1)
    results = json.loads(results_json)

    if results:
        record = results[0]
        log_search_request(current_user, "get_record", {"ssn": ssn}, 1)

        # Count email and phone
        email_count = 1 if record.get('email') else 0
        phone_count = 1 if record.get('phone') else 0

        # Hide actual email and phone
        record['email'] = None
        record['phone'] = None
        record['email_count'] = email_count
        record['phone_count'] = phone_count

        return SSNRecord(**record)

    # Not found - log before raising
    log_search_request(current_user, "get_record", {"ssn": ssn}, 0)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"SSN record not found: {ssn}"
    )


@router.post("/instant-ssn", response_model=InstantSSNResponse)
# @limiter.limit("10/hour")
async def instant_ssn_search(
    req: Request,
    response: Response,
    request: InstantSSNRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Instant SSN search via external API with local database matching.

    Flow:
    1. Search external API for person data (all ZIPs, all phones)
    2. Match against local SSN database using firstname + lastname + (ZIP OR phone)
    3. Return external API data with SSN from local database (if found)

    Args:
        req: FastAPI request object (required by SlowAPI)
        response: FastAPI response object (required by SlowAPI)
        request: Search request with firstname, lastname, and address
        current_user: Current authenticated user

    Returns:
        InstantSSNResponse with external API data and matched SSNs

    Raises:
        HTTPException: On external API errors or validation errors
    """
    logger.info(
        f"Instant SSN search: user={current_user.username}, "
        f"name={request.firstname} {request.lastname}, "
        f"address={request.address}"
    )

    # Step 0: Check if user is banned
    check_user_ban(current_user)

    # Check if Instant SSN is in maintenance mode
    is_maintenance, maintenance_message = await check_maintenance_mode(db, 'instant_ssn')
    if is_maintenance:
        default_message = "Instant SSN service is currently under maintenance. Please try again later."
        message = maintenance_message or default_message
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=message
        )

    # Get custom price for this user or use configurable default
    from api.common.pricing import get_default_instant_ssn_price
    default_instant_price = await get_default_instant_ssn_price(db)
    instant_ssn_price = await get_user_price(
        db=db,
        access_code=current_user.access_code or '',
        service_name='instant_ssn',
        default_price=default_instant_price
    )

    # Determine source from request
    from api.common.models_postgres import RequestSource
    if request.source == "telegram_bot":
        source = RequestSource.telegram_bot
    elif request.source == "web":
        source = RequestSource.web
    else:
        source = RequestSource.other

    # Sanitize search params for logging
    sanitized_search_params = sanitize_metadata({
        "firstname": request.firstname,
        "lastname": request.lastname,
        "address": request.address
    }, max_depth=3, max_size=5000) or {}

    # Create initial search log entry
    search_log = InstantSSNSearch(
        user_id=current_user.id,
        search_params=sanitized_search_params,
        success=False,
        ssn_found=False,
        api_cost=SEARCHBUG_API_COST,
        user_charged=Decimal("0.00"),
        source=source
    )
    db.add(search_log)
    await db.commit()
    await db.refresh(search_log)

    # Check balance before external API call (but don't charge yet)
    if current_user.balance < instant_ssn_price:
        search_log.error_message = f"Insufficient balance. Required: ${instant_ssn_price}, Available: ${current_user.balance}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${instant_ssn_price}, Available: ${current_user.balance}"
        )

    try:
        # Step 0.5: Get search flow configuration
        search_flow_value = await get_search_flow(db)
        flow_config = parse_search_flow(search_flow_value)
        logger.info(f"Search flow: {search_flow_value} (steps={flow_config['steps']}, manual={flow_config['has_manual_fallback']})")

        # Special case: "manual" flow - skip all APIs, create ticket immediately
        if not flow_config["steps"]:
            new_ticket = ManualSSNTicket(
                user_id=current_user.id,
                firstname=request.firstname,
                lastname=request.lastname,
                address=request.address,
                status=TicketStatus.pending,
                source=source,
            )
            db.add(new_ticket)
            search_log.error_message = "Manual-only flow — ticket created"
            await db.commit()
            await _notify_worker_new_ticket()
            logger.info(f"Manual-only flow: ticket {new_ticket.id} created for {request.firstname} {request.lastname}")

            return InstantSSNResponse(
                success=True,
                results=[],
                data_found=False,
                ssn_matches_found=0,
                message="Request has been sent for manual processing.",
                new_balance=float(current_user.balance),
            )

        # Step 1: Execute API chain — try each provider, search ClickHouse with its data
        ssn_matches = []
        best_extracted = None  # Data from first successful API (for partial results)
        matched_provider = None  # Track which provider found SSN

        for step in flow_config["steps"]:
            try:
                logger.info(f"Trying provider '{step}' for {request.firstname} {request.lastname}")
                step_api_data = await _call_external_api(step, request.firstname, request.lastname, request.address, db)

                if not step_api_data:
                    logger.info(f"Provider '{step}' returned no data, trying next...")
                    continue

                logger.info(f"Provider '{step}' returned data")
                extracted = _extract_api_data(step_api_data, request.firstname, request.lastname)

                # Keep first successful API data for partial results (DOB)
                if best_extracted is None:
                    best_extracted = extracted

                # Step 2: Search ClickHouse with this provider's data
                matches = _run_clickhouse_search(extracted, request.address)

                if matches:
                    ssn_matches = matches
                    best_extracted = extracted  # Use the provider that found SSN
                    matched_provider = step  # Save which provider found SSN
                    logger.info(f"Provider '{step}': SSN found ({len(matches)} match(es))")
                    break

                logger.info(f"Provider '{step}': data found but no SSN match, trying next...")
            except SearchbugAPIError as api_err:  # WhitepagesAPIError temporarily disabled
                logger.warning(f"Provider '{step}' API error: {api_err}, trying next...")
                continue

        # No API returned data at all
        if best_extracted is None:
            logger.info("No external API returned data")
            if flow_config["has_manual_fallback"]:
                new_ticket = ManualSSNTicket(
                    user_id=current_user.id,
                    firstname=request.firstname,
                    lastname=request.lastname,
                    address=request.address,
                    status=TicketStatus.pending,
                    source=source,
                )
                db.add(new_ticket)
                search_log.error_message = "No API data — sent to worker"
                await db.commit()
                await _notify_worker_new_ticket()
                logger.info(f"No API data — manual ticket created for {request.firstname} {request.lastname}")

                return InstantSSNResponse(
                    success=True,
                    results=[],
                    data_found=False,
                    ssn_matches_found=0,
                    message="No data found. Request has been sent for manual processing.",
                    new_balance=float(current_user.balance),
                )
            else:
                search_log.error_message = "No data found"
                await db.commit()
                return InstantSSNResponse(
                    success=True,
                    results=[],
                    data_found=False,
                    ssn_matches_found=0,
                    message="No data found for the given search criteria",
                    new_balance=float(current_user.balance),
                )

        # At this point: best_extracted has API data, ssn_matches may or may not have results
        dob = best_extracted['dob']
        report_token = best_extracted['report_token']
        primary_address = best_extracted['primary_address']
        primary_phone = best_extracted['primary_phone']
        primary_email = best_extracted['primary_email']
        firstname = best_extracted['firstname']
        lastname = best_extracted['lastname']
        middlename = best_extracted['middlename']

        # Auto-create manual ticket if SSN not found and flow has manual fallback
        manual_ticket_created = False
        if not ssn_matches and flow_config["has_manual_fallback"]:
            new_ticket = ManualSSNTicket(
                user_id=current_user.id,
                firstname=request.firstname,
                lastname=request.lastname,
                address=request.address,
                status=TicketStatus.pending,
                source=source,
            )
            db.add(new_ticket)
            await db.commit()
            await _notify_worker_new_ticket()
            manual_ticket_created = True
            logger.info(f"SSN not found — manual ticket {new_ticket.id} created")

        # Step 2.7: Abuse detection
        ssn_found = len(ssn_matches) > 0
        is_full_dob_range = not dob or dob.strip() == ''
        abuse_type = 'full_dob_range' if is_full_dob_range else 'same_not_found'
        if not ssn_found:
            abuse_type = 'same_not_found'

        is_abuse, ban_reason = await check_abuse_patterns(
            db=db,
            user_id=current_user.id,
            firstname=request.firstname,
            lastname=request.lastname,
            address=request.address,
            dob=dob,
            ssn_found=ssn_found
        )

        await log_abuse_tracking(
            db=db,
            user_id=current_user.id,
            search_params={
                "firstname": request.firstname,
                "lastname": request.lastname,
                "address": request.address,
                "dob": dob,
                "ssn_found": ssn_found
            },
            abuse_type=abuse_type,
            is_abuse=is_full_dob_range or (not ssn_found and abuse_type == 'same_not_found'),
            consecutive_count=1
        )

        if is_abuse:
            await ban_user(db, current_user, ban_reason)
            search_log.error_message = ban_reason
            await db.commit()
            logger.warning(f"User {current_user.username} banned: {ban_reason}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ban_reason
            )

        # Step 3: Build results
        results = []

        if ssn_matches and len(ssn_matches) > 0:
            # SSN found — use local DB data, fallback to API data
            for ssn_record in ssn_matches:
                _ssn_val = ssn_record.get('ssn', '')
                _masked = f"***-**-{_ssn_val[-4:]}" if _ssn_val and len(_ssn_val) >= 4 else "N/A"
                logger.info(f"SSN record from DB: id={ssn_record.get('id')}, SSN={_masked}")
                result = InstantSSNResult(
                    firstname=ssn_record.get('firstname') or firstname,
                    lastname=ssn_record.get('lastname') or lastname,
                    middlename=ssn_record.get('middlename') or middlename,
                    dob=ssn_record.get('dob') or dob,
                    address=ssn_record.get('address') or (primary_address.get('full_street') if (primary_address and isinstance(primary_address, dict)) else None),
                    city=ssn_record.get('city') or (primary_address.get('city') if (primary_address and isinstance(primary_address, dict)) else None),
                    state=ssn_record.get('state') or (primary_address.get('state') if (primary_address and isinstance(primary_address, dict)) else None),
                    zip_code=ssn_record.get('zip') or (primary_address.get('zip_code') if (primary_address and isinstance(primary_address, dict)) else None),
                    phone=ssn_record.get('phone') or primary_phone,
                    email=ssn_record.get('email') or primary_email,
                    ssn=ssn_record.get('ssn'),
                    ssn_found=True,
                    report_token=report_token,
                    local_db_data={
                        'firstname': ssn_record.get('firstname'),
                        'lastname': ssn_record.get('lastname'),
                        'dob': ssn_record.get('dob'),
                        'address': ssn_record.get('address'),
                        'city': ssn_record.get('city'),
                        'state': ssn_record.get('state'),
                        'zip': ssn_record.get('zip'),
                        'phone': ssn_record.get('phone'),
                        'email': ssn_record.get('email'),
                        'source_table': ssn_record.get('source_table')
                    }
                )
                results.append(result)
        else:
            # No SSN found — return USER INPUT data + DOB from API (Task 2: partial results)
            result = InstantSSNResult(
                firstname=request.firstname,
                lastname=request.lastname,
                middlename=None,
                dob=dob,
                address=request.address,
                city=None,
                state=None,
                zip_code=None,
                phone=None,
                email=None,
                ssn=None,
                ssn_found=False,
                report_token=report_token,
            )
            results.append(result)

        # Log the search
        log_search_request(
            current_user,
            "instant_ssn_search",
            {
                "firstname": request.firstname,
                "lastname": request.lastname,
                "address": request.address
            },
            len(results)
        )

        # ONLY charge and create order if SSN was found
        if ssn_matches and len(ssn_matches) > 0:
            # Charge user for successful search
            current_user.balance -= instant_ssn_price
            await db.commit()
            await db.refresh(current_user)

            logger.info(
                f"User {current_user.username} charged ${instant_ssn_price} for Instant SSN search (SSN found). "
                f"New balance: ${current_user.balance}"
            )

            # Notify about balance change via WebSocket
            await publish_user_notification(
                str(current_user.id),
                WebSocketEventType.BALANCE_UPDATED,
                {"user_id": str(current_user.id), "new_balance": float(current_user.balance)}
            )

            # Create order for purchased Instant SSN search
            order_items = []
            for result in results:
                order_item = {
                    "ssn": result.ssn if result.ssn else "Not found",
                    "source_table": result.local_db_data.get('source_table') if result.local_db_data else "instant_ssn",
                    "ssn_record_id": f"{result.local_db_data.get('source_table', 'instant_ssn')}:{result.ssn}" if result.ssn else "instant_ssn:not_found",
                    "price": str(instant_ssn_price),
                    "source": "instant_ssn",
                    "firstname": result.firstname,
                    "lastname": result.lastname,
                    "middlename": result.middlename,
                    "dob": result.dob,
                    "address": result.address,
                    "city": result.city,
                    "state": result.state,
                    "zip": result.zip_code,
                    "phone": result.phone,
                    "email": result.email,
                    "report_token": result.report_token,
                    "purchased_at": datetime.utcnow().isoformat(),
                    "ssn_found": result.ssn_found,
                    "search_method": matched_provider or "unknown"
                }
                order_items.append(order_item)

            new_order = Order(
                user_id=current_user.id,
                items=order_items,
                total_price=instant_ssn_price,
                status=OrderStatus.completed,
                order_type=OrderType.instant_ssn,
                is_viewed=False
            )
            db.add(new_order)
            await db.commit()
            await db.refresh(new_order)

            logger.info(
                f"Created order {new_order.id} for Instant SSN search. "
                f"User: {current_user.username}, SSN matches: {len(ssn_matches)}"
            )

            search_log.success = True
            search_log.ssn_found = True
            search_log.order_id = new_order.id
            search_log.user_charged = instant_ssn_price
            await db.commit()
        else:
            logger.info(
                f"No SSN found for {request.firstname} {request.lastname} - user NOT charged"
            )
            search_log.success = False
            search_log.ssn_found = False
            search_log.error_message = "No SSN matches found in local database"
            await db.commit()

        # Build response message
        if ssn_matches:
            message = f"Found {len(ssn_matches)} SSN match(es)"
        elif manual_ticket_created:
            message = "No SSN found. Request sent for manual processing."
        else:
            message = "No SSN matches found in database"

        return InstantSSNResponse(
            success=True,
            results=results,
            data_found=True,
            ssn_matches_found=len(ssn_matches),
            message=message,
            new_balance=float(current_user.balance),
            order_id=str(new_order.id) if ssn_matches else None,
            charged_amount=float(instant_ssn_price) if ssn_matches else None
        )

    except SearchbugAPIError as e:  # WhitepagesAPIError temporarily disabled
        logger.error(f"External API error: {e.message}")
        search_log.error_message = f"External API error: {e.message}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service is temporarily unavailable: {e.message}"
        )
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        search_log.error_message = f"Validation error: {str(e)}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in instant_ssn_search: {str(e)}", exc_info=True)
        search_log.error_message = f"Unexpected error: {str(e)}"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during Instant SSN search"
        )


@router.post("/debug-flow", response_model=DebugFlowResponse)
async def debug_flow_search(
    request: DebugFlowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Debug endpoint to visualize full two-level search flow.
    Only available for admin users.

    Returns detailed information about:
    1. SearchBug API response
    2. Generated bloom keys and their matches
    3. Generated search keys (Level 2) and their matches
    4. Found fullz from database
    """
    # Check admin access
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    logger.info(
        f"Debug flow search: user={current_user.username}, "
        f"name={request.firstname} {request.lastname}, "
        f"address={request.address}"
    )

    # Import bloom/search key generators
    from database.bloom_key_generator import (
        generate_bloom_key_phone,
        generate_bloom_key_address,
        generate_all_bloom_keys_from_searchbug,
    )
    from database.search_key_generator import (
        generate_query_keys_from_searchbug,
        generate_candidate_keys,
        extract_searchbug_mn_and_dob,
        extract_all_searchbug_mn,
        extract_dob_year,
    )
    from database.clickhouse_search_engine import (
        MATCH_METHOD_PRIORITY,
        _get_best_match_priority,
        _rank_sort_key,
    )
    from database.clickhouse_schema import (
        SSN_BLOOM_PHONE_LOOKUP,
        SSN_MUTANTS_BLOOM_PHONE_LOOKUP,
        SSN_BLOOM_ADDRESS_LOOKUP,
        SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP,
    )
    from database.clickhouse_client import execute_query

    try:
        # Step 1: Search API (SearchBug or WhitePages)
        if request.provider == "whitepages":
            async with create_whitepages_client() as wp:
                searchbug_data = await wp.search_person_unified(
                    firstname=request.firstname,
                    lastname=request.lastname,
                    address=request.address
                )
        else:
            cache_service = SearchBugCacheService(db)
            async with await create_searchbug_client_dynamic(db) as searchbug:
                searchbug_data = await cache_service.search_person_unified_cached(
                    searchbug_client=searchbug,
                    firstname=request.firstname,
                    lastname=request.lastname,
                    address=request.address
                )

        if not searchbug_data:
            return DebugFlowResponse(
                provider=request.provider,
                searchbug_data={},
                bloom_keys_phone=[],
                bloom_keys_address=[],
                level1_candidates_count=0,
                query_keys=[],
                candidates_with_keys=[],
                final_results=[],
                final_count=0
            )

        # Extract data from SearchBug response
        names = searchbug_data.get('names', [])
        firstname = request.firstname
        lastname = request.lastname
        middlename = None
        if names and len(names) > 0:
            firstname = names[0].get('first_name', request.firstname)
            lastname = names[0].get('last_name', request.lastname)
            middlename = names[0].get('middle_name')

        dob = searchbug_data.get('dob', '')
        addresses = searchbug_data.get('addresses', []) or []
        all_phones_raw = searchbug_data.get('all_phones', []) or []

        # Extract phone numbers
        all_phones = []
        for phone_obj in all_phones_raw:
            if isinstance(phone_obj, dict):
                phone_num = phone_obj.get('phone_number', '')
                if phone_num:
                    all_phones.append(phone_num)
            elif isinstance(phone_obj, str):
                all_phones.append(phone_obj)

        # Prepare addresses with state
        addresses_with_state = []
        for addr in addresses:
            full_street = addr.get('full_street', '')
            state = addr.get('state', '')
            if full_street and state:
                addresses_with_state.append({
                    'address': full_street,
                    'state': state
                })

        # Step 2: Generate and check bloom keys
        # ВАЖНО: передаём массив names для обработки ВСЕХ вариаций имён
        searchbug_search_data = {
            'names': names,  # массив всех имён от SearchBug
            'firstname': firstname,  # fallback - первое имя
            'middlename': middlename,
            'lastname': lastname,
            'dob': dob,
            'phones': all_phones,
            'addresses': addresses_with_state
        }

        bloom_results = generate_all_bloom_keys_from_searchbug(searchbug_search_data)
        bloom_keys_phone_list = bloom_results.get('bloom_keys_phone', [])
        bloom_keys_address_list = bloom_results.get('bloom_keys_address', [])

        bloom_keys_phone_results: List[BloomKeyResult] = []
        bloom_keys_address_results: List[BloomKeyResult] = []
        all_candidates: List[Dict[str, Any]] = []

        # Check each phone bloom key
        for key in bloom_keys_phone_list:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone = {{key:String}}
            UNION ALL
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone = {{key:String}}
            LIMIT 100
            """
            candidates = execute_query(query, parameters={"key": key})
            bloom_keys_phone_results.append(BloomKeyResult(
                key=key,
                type='phone',
                found_in_db=len(candidates) > 0,
                candidates_count=len(candidates)
            ))
            all_candidates.extend(candidates)

        # Check each address bloom key
        for key in bloom_keys_address_list:
            query = f"""
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address = {{key:String}}
            UNION ALL
            SELECT
                id, firstname, lastname, middlename, address, city, state, zip,
                phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address = {{key:String}}
            LIMIT 100
            """
            candidates = execute_query(query, parameters={"key": key})
            bloom_keys_address_results.append(BloomKeyResult(
                key=key,
                type='address',
                found_in_db=len(candidates) > 0,
                candidates_count=len(candidates)
            ))
            all_candidates.extend(candidates)

        # НЕ дедуплицируем до Level 2 — мутанты с тем же SSN могут не пройти
        # Level 2, а оригинальная запись — пройдёт. Дедупликация будет после matching.

        # Step 3: Generate query keys from SearchBug data
        # Извлекаем ВСЕ вариации MN (SearchBug может вернуть несколько имён)
        all_sb_mn = extract_all_searchbug_mn(searchbug_search_data)
        sb_dob = searchbug_search_data.get('dob')
        sb_dob_year = extract_dob_year(sb_dob) if sb_dob else None
        # Для отображения берём первый не-None mn
        sb_mn = next((m for m in all_sb_mn if m is not None), None)

        query_keys_dict = generate_query_keys_from_searchbug(searchbug_search_data)

        # Build query keys list for response
        query_keys_results: List[SearchKeyResult] = []
        for key_value, method_name in sorted(query_keys_dict.items(), key=lambda x: x[1]):
            # Will be marked as matched later
            query_keys_results.append(SearchKeyResult(
                key=key_value,
                key_type=method_name,
                matched=False
            ))

        # Step 4: Filter candidates through Level 2 matching
        candidates_with_keys: List[CandidateResult] = []
        final_results: List[CandidateResult] = []
        matched_query_keys: Set[str] = set()
        seen_final_ssns: Set[str] = set()

        for candidate in all_candidates:
            # Генерируем ключи кандидата только из данных самой записи БД
            candidate_keys = generate_candidate_keys(candidate)
            matched_key_values = candidate_keys.keys() & query_keys_dict.keys()
            matched = {k: query_keys_dict[k] for k in matched_key_values}

            matched_keys_list = [f"{method}: {key}" for key, method in matched.items()]
            best_priority = _get_best_match_priority(matched_keys_list) if matched_keys_list else None

            candidate_result = CandidateResult(
                ssn=candidate.get('ssn', ''),
                firstname=candidate.get('firstname'),
                lastname=candidate.get('lastname'),
                middlename=candidate.get('middlename'),
                dob=candidate.get('dob'),
                address=candidate.get('address'),
                city=candidate.get('city'),
                state=candidate.get('state'),
                zip=candidate.get('zip'),
                phone=candidate.get('phone'),
                email=candidate.get('email'),
                source_table=candidate.get('source_table'),
                matched_keys=matched_keys_list,
                candidate_keys=[f"{method}: {key}" for key, method in candidate_keys.items()],
                matched_keys_count=len(matched_keys_list),
                best_match_priority=best_priority if best_priority != 999 else None
            )
            candidates_with_keys.append(candidate_result)

            if matched:
                ssn_val = candidate.get('ssn', '')
                if ssn_val not in seen_final_ssns:
                    seen_final_ssns.add(ssn_val)
                    final_results.append(candidate_result)
                else:
                    # Merge matched_keys with existing result for same SSN
                    for existing_r in final_results:
                        if existing_r.ssn == ssn_val:
                            # Merge keys
                            merged_keys = set(existing_r.matched_keys or []) | set(matched_keys_list)
                            existing_r.matched_keys = sorted(merged_keys)
                            existing_r.matched_keys_count = len(existing_r.matched_keys)
                            existing_r.best_match_priority = _get_best_match_priority(existing_r.matched_keys)
                            # Prefer record with matching address
                            from database.clickhouse_search_engine import _normalize_address_for_match as _df_norm
                            existing_addr_key = _df_norm(existing_r.address or '')
                            new_addr_key = _df_norm(candidate.get('address', ''))
                            input_addr_key_df = _df_norm(request.address)
                            if input_addr_key_df and new_addr_key == input_addr_key_df and existing_addr_key != input_addr_key_df:
                                # New record has matching address — replace record data
                                existing_r.firstname = candidate.get('firstname')
                                existing_r.lastname = candidate.get('lastname')
                                existing_r.middlename = candidate.get('middlename')
                                existing_r.dob = candidate.get('dob')
                                existing_r.address = candidate.get('address')
                                existing_r.city = candidate.get('city')
                                existing_r.state = candidate.get('state')
                                existing_r.zip = candidate.get('zip')
                                existing_r.phone = candidate.get('phone')
                                existing_r.email = candidate.get('email')
                                existing_r.source_table = candidate.get('source_table')
                            break
                matched_query_keys.update(matched)

        # Update query keys with match status
        for qk in query_keys_results:
            qk.matched = qk.key in matched_query_keys

        # Sort: quantity first (more keys = better), then quality (lower priority = better)
        final_results.sort(
            key=lambda r: (
                -r.matched_keys_count,
                r.best_match_priority or 999
            )
        )

        # Build response
        response = DebugFlowResponse(
            provider=request.provider,
            searchbug_data={
                'names': names,  # все вариации имён от SearchBug
                'firstname': firstname,
                'middlename': middlename,
                'lastname': lastname,
                'dob': dob,
                'phones': all_phones,
                'addresses': addresses_with_state,
                'primary_address': searchbug_data.get('primary_address'),
                'primary_phone': searchbug_data.get('primary_phone'),
                'primary_email': searchbug_data.get('primary_email'),
            },
            bloom_keys_phone=bloom_keys_phone_results,
            bloom_keys_address=bloom_keys_address_results,
            level1_candidates_count=len(all_candidates),
            query_keys=query_keys_results,
            searchbug_mn=sb_mn,
            searchbug_dob_year=sb_dob_year,
            candidates_with_keys=candidates_with_keys,
            final_results=final_results,
            final_count=len(final_results)
        )

        logger.info(
            f"Debug flow completed: bloom_phone={len(bloom_keys_phone_results)}, "
            f"bloom_address={len(bloom_keys_address_results)}, "
            f"level1_candidates={len(all_candidates)}, "
            f"query_keys={len(query_keys_results)}, "
            f"final_results={len(final_results)}"
        )

        return response

    except SearchbugAPIError as e:  # WhitepagesAPIError temporarily disabled
        logger.error(f"API error in debug_flow: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"API error: {e.message}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in debug_flow: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/test-search", response_model=TestSearchResponse)
async def test_search(
    request: DebugFlowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Test search endpoint — simplified two-level search without balance deduction.
    Available for all authenticated users.
    """
    logger.info(
        f"Test search: user={current_user.username}, "
        f"name={request.firstname} {request.lastname}, "
        f"address={request.address}"
    )

    from database.bloom_key_generator import generate_all_bloom_keys_from_searchbug
    from database.search_key_generator import (
        generate_query_keys_from_searchbug,
        generate_candidate_keys,
        extract_all_searchbug_mn,
        extract_dob_year,
    )
    from database.clickhouse_search_engine import _get_best_match_priority, _rank_sort_key
    from database.clickhouse_schema import (
        SSN_BLOOM_PHONE_LOOKUP,
        SSN_MUTANTS_BLOOM_PHONE_LOOKUP,
        SSN_BLOOM_ADDRESS_LOOKUP,
        SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP,
    )
    from database.clickhouse_client import execute_query

    input_fullname = request.fullname.strip().title() if request.fullname else f"{request.firstname} {request.lastname}"
    input_address = request.address

    try:
        # Step 1: SearchBug API via cache
        cache_service = SearchBugCacheService(db)

        async with await create_searchbug_client_dynamic(db) as searchbug:
            searchbug_data = await cache_service.search_person_unified_cached(
                searchbug_client=searchbug,
                firstname=request.firstname,
                lastname=request.lastname,
                address=request.address
            )

        if not searchbug_data:
            return TestSearchResponse(
                input_fullname=input_fullname,
                input_address=input_address,
            )

        # Extract data from SearchBug response
        names = searchbug_data.get('names', [])
        firstname = request.firstname
        lastname = request.lastname
        middlename = None
        if names and len(names) > 0:
            firstname = names[0].get('first_name', request.firstname)
            lastname = names[0].get('last_name', request.lastname)
            middlename = names[0].get('middle_name')

        dob = searchbug_data.get('dob', '')
        addresses = searchbug_data.get('addresses', []) or []
        all_phones_raw = searchbug_data.get('all_phones', []) or []

        all_phones = []
        for phone_obj in all_phones_raw:
            if isinstance(phone_obj, dict):
                phone_num = phone_obj.get('phone_number', '')
                if phone_num:
                    all_phones.append(phone_num)
            elif isinstance(phone_obj, str):
                all_phones.append(phone_obj)

        addresses_with_state = []
        for addr in addresses:
            full_street = addr.get('full_street', '')
            state = addr.get('state', '')
            if full_street and state:
                addresses_with_state.append({
                    'address': full_street,
                    'state': state
                })

        # Step 2: Generate bloom keys and find candidates
        searchbug_search_data = {
            'names': names,
            'firstname': firstname,
            'middlename': middlename,
            'lastname': lastname,
            'dob': dob,
            'phones': all_phones,
            'addresses': addresses_with_state
        }

        bloom_results = generate_all_bloom_keys_from_searchbug(searchbug_search_data)
        bloom_keys_phone_list = bloom_results.get('bloom_keys_phone', [])
        bloom_keys_address_list = bloom_results.get('bloom_keys_address', [])
        all_candidates: List[Dict[str, Any]] = []

        for key in bloom_keys_phone_list:
            query = f"""
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone = {{key:String}}
            UNION ALL
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_PHONE_LOOKUP}
            WHERE bloom_key_phone = {{key:String}}
            LIMIT 100
            """
            candidates = execute_query(query, parameters={"key": key})
            all_candidates.extend(candidates)

        for key in bloom_keys_address_list:
            query = f"""
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address = {{key:String}}
            UNION ALL
            SELECT id, firstname, lastname, middlename, address, city, state, zip,
                   phone, ssn, dob, email, source_table
            FROM {SSN_MUTANTS_BLOOM_ADDRESS_LOOKUP}
            WHERE bloom_key_address = {{key:String}}
            LIMIT 100
            """
            candidates = execute_query(query, parameters={"key": key})
            all_candidates.extend(candidates)

        # Step 3: Level 2 matching — collect all matches, deduplicate, rank, take best
        query_keys_dict = generate_query_keys_from_searchbug(searchbug_search_data)

        all_matched: List[Dict[str, Any]] = []

        for candidate in all_candidates:
            candidate_keys = generate_candidate_keys(candidate)
            matched_key_values = candidate_keys.keys() & query_keys_dict.keys()

            if matched_key_values:
                candidate['matched_keys'] = [
                    f"{query_keys_dict[k]}: {k}" for k in matched_key_values
                ]
                all_matched.append(candidate)

        # Deduplicate by SSN: merge matched_keys, keep best record
        # Priority: 1) address match (SB primary > input), 2) filled fields count
        from database.clickhouse_search_engine import _normalize_address_for_match
        sb_primary_addr = searchbug_data.get('primary_address')
        sb_primary_street = ''
        if sb_primary_addr and isinstance(sb_primary_addr, dict):
            sb_primary_street = sb_primary_addr.get('full_street', '')

        sb_key = _normalize_address_for_match(sb_primary_street)
        ts_input_key = _normalize_address_for_match(request.address)

        def _ts_dedup_addr_score(rec):
            addr_key = _normalize_address_for_match(rec.get('address', ''))
            score = 0
            if sb_key and addr_key == sb_key:
                score += 2
            if ts_input_key and addr_key == ts_input_key:
                score += 1
            return score

        ssn_best: Dict[str, Dict[str, Any]] = {}
        ssn_all_matched_keys: Dict[str, set] = {}

        for record in all_matched:
            ssn = record.get('ssn')
            if not ssn:
                continue
            if ssn not in ssn_best:
                ssn_best[ssn] = record
                ssn_all_matched_keys[ssn] = set(record.get('matched_keys', []))
            else:
                ssn_all_matched_keys[ssn].update(record.get('matched_keys', []))
                existing = ssn_best[ssn]
                existing_score = _ts_dedup_addr_score(existing)
                current_score = _ts_dedup_addr_score(record)
                if current_score > existing_score:
                    ssn_best[ssn] = record
                elif current_score == existing_score:
                    existing_fields = sum(1 for v in existing.values() if v and str(v).strip())
                    current_fields = sum(1 for v in record.values() if v and str(v).strip())
                    if current_fields > existing_fields:
                        ssn_best[ssn] = record

        for ssn, record in ssn_best.items():
            record['matched_keys'] = sorted(ssn_all_matched_keys[ssn])
        # Rank: quantity first (more keys = better), then quality (lower priority = better)
        ranked = sorted(ssn_best.values(), key=_rank_sort_key)

        # Take only the best result
        ssn_results: List[str] = []
        matched_candidates: List[Dict[str, Any]] = []
        if ranked:
            best = ranked[0]
            ssn_results.append(best.get('ssn', ''))
            matched_candidates.append(best)

        logger.info(
            f"Test search completed: user={current_user.username}, "
            f"candidates={len(all_candidates)}, results={len(ssn_results)}"
        )

        # Save results to history
        result_fullname = f"{firstname} {lastname}"
        primary_address = searchbug_data.get('primary_address')
        result_address = (primary_address.get('full_street', '') if primary_address and isinstance(primary_address, dict) else input_address)

        if ssn_results:
            # Save the single best match as a history entry
            candidate = matched_candidates[0] if matched_candidates else None
            history_entry = TestSearchHistory(
                user_id=current_user.id,
                input_fullname=input_fullname,
                input_address=input_address,
                result_fullname=input_fullname,
                result_address=candidate.get('address', result_address) if candidate else result_address,
                ssn=ssn_results[0],
                dob=dob or (candidate.get('dob') if candidate else None),
                found=True,
                search_source='test_search'
            )
            db.add(history_entry)
        else:
            # Save not_found entry
            history_entry = TestSearchHistory(
                user_id=current_user.id,
                input_fullname=input_fullname,
                input_address=input_address,
                result_fullname=input_fullname,
                result_address=result_address,
                ssn='',
                dob=dob or None,
                found=False,
                search_source='test_search'
            )
            db.add(history_entry)

        await db.commit()

        return TestSearchResponse(
            input_fullname=input_fullname,
            input_address=input_address,
            searchbug_dob=dob if dob else None,
            ssn_results=ssn_results,
            count=len(ssn_results)
        )

    except SearchbugAPIError as e:
        logger.error(f"SearchBug API error in test_search: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"SearchBug API error: {e.message}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in test_search: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.get("/test-search/history", response_model=TestSearchHistoryResponse)
async def get_test_search_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session),
    source: Optional[str] = None
):
    """
    Get test search history and stats for the current user.
    Returns all history entries and aggregate statistics.
    Optional source filter: 'test_search' or 'unified_search'.
    """
    # Get all history entries ordered by created_at desc
    stmt = (
        select(TestSearchHistory)
        .where(TestSearchHistory.user_id == current_user.id)
    )
    if source:
        stmt = stmt.where(TestSearchHistory.search_source == source)
    stmt = stmt.order_by(desc(TestSearchHistory.created_at))
    result = await db.execute(stmt)
    entries = result.scalars().all()

    history_items = []
    total_requests = 0
    successful_requests = 0
    total_found = 0

    for entry in entries:
        total_requests += 1
        if entry.found:
            successful_requests += 1
            total_found += 1

        history_items.append(TestSearchHistoryItem(
            id=str(entry.id),
            input_fullname=entry.input_fullname,
            input_address=entry.input_address,
            result_fullname=entry.result_fullname,
            result_address=entry.result_address,
            ssn=entry.ssn,
            dob=entry.dob,
            found=entry.found,
            status=entry.status or ('done' if entry.found else 'nf'),
            search_time=entry.search_time,
            created_at=entry.created_at.isoformat()
        ))

    return TestSearchHistoryResponse(
        history=history_items,
        total_requests=total_requests,
        successful_requests=successful_requests,
        total_found=total_found
    )


async def _notify_worker_new_ticket():
    """Notify worker_api about a new ticket so it can push to connected workers."""
    try:
        import httpx
        _internal_key = os.getenv("INTERNAL_API_KEY", "")
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                "http://worker_api:8003/internal/notify-new-ticket",
                headers={"X-Internal-Api-Key": _internal_key}
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Failed to notify worker_api about new ticket: {e}")


async def _run_search_background(
    user_id: UUID,
    username: str,
    history_entry_id: UUID,
    search_log_id: UUID,
    firstname: str,
    lastname: str,
    fullname: str,
    address: str,
    instant_ssn_price: Decimal,
    source: RequestSource,
):
    """
    Background task: performs API chain + ClickHouse search, updates TestSearchHistory status.
    Uses its own DB session since the request-scoped one is already closed.
    Respects the search flow setting from admin panel.
    """
    search_start_time = time.monotonic()
    async with async_session_maker() as db:
        try:
            # Load search_log
            search_log = await db.get(InstantSSNSearch, search_log_id)

            # Step 0.5: Get search flow configuration
            search_flow_value = await get_search_flow(db)
            flow_config = parse_search_flow(search_flow_value)
            logger.info(f"Background search flow: {search_flow_value} (steps={flow_config['steps']}, manual={flow_config['has_manual_fallback']})")

            # Special case: "manual" flow - skip all APIs, create ticket immediately
            if not flow_config["steps"]:
                if search_log:
                    search_log.error_message = "Manual-only flow — ticket created"
                    search_log.ssn_found = False

                new_ticket = ManualSSNTicket(
                    user_id=user_id,
                    firstname=firstname,
                    lastname=lastname,
                    address=address,
                    status=TicketStatus.pending,
                    source=source,
                    test_search_history_id=history_entry_id
                )
                db.add(new_ticket)
                await db.commit()
                logger.info(f"Manual-only flow: ticket {new_ticket.id} created for {firstname} {lastname}")
                await _notify_worker_new_ticket()
                return

            # Step 1: Execute API chain — try each provider, search ClickHouse with its data
            ssn_matches = []
            best_extracted = None
            matched_provider = None  # Track which provider found SSN

            for step in flow_config["steps"]:
                try:
                    logger.info(f"Background: trying provider '{step}' for {firstname} {lastname}")
                    step_api_data = await _call_external_api(step, firstname, lastname, address, db)

                    if not step_api_data:
                        logger.info(f"Background: provider '{step}' returned no data, trying next...")
                        continue

                    logger.info(f"Background: provider '{step}' returned data")
                    extracted = _extract_api_data(step_api_data, firstname, lastname)

                    if best_extracted is None:
                        best_extracted = extracted

                    matches = _run_clickhouse_search(extracted, address)

                    if matches:
                        ssn_matches = matches
                        best_extracted = extracted
                        matched_provider = step  # Save which provider found SSN
                        logger.info(f"Background: provider '{step}': SSN found ({len(matches)} match(es))")
                        break

                    logger.info(f"Background: provider '{step}': data found but no SSN match, trying next...")
                except SearchbugAPIError as api_err:  # WhitepagesAPIError temporarily disabled
                    logger.warning(f"Background: provider '{step}' API error: {api_err}, trying next...")
                    continue

            # No API returned data at all
            if best_extracted is None:
                logger.info(f"Background: no external API returned data for {firstname} {lastname}")

                if flow_config["has_manual_fallback"]:
                    if search_log:
                        search_log.error_message = "No API data — sent to worker"
                        search_log.ssn_found = False

                    new_ticket = ManualSSNTicket(
                        user_id=user_id,
                        firstname=firstname,
                        lastname=lastname,
                        address=address,
                        status=TicketStatus.pending,
                        source=source,
                        test_search_history_id=history_entry_id
                    )
                    db.add(new_ticket)
                    await db.commit()
                    logger.info(f"No API data — ticket {new_ticket.id} created for worker")
                    await _notify_worker_new_ticket()
                else:
                    if search_log:
                        search_log.error_message = "No API data — no manual fallback"
                        search_log.ssn_found = False
                    hist_stmt = (
                        update(TestSearchHistory)
                        .where(TestSearchHistory.id == history_entry_id)
                        .values(status='nf', found=False, search_time=round(time.monotonic() - search_start_time, 1))
                    )
                    await db.execute(hist_stmt)
                    await db.commit()
                return

            # At this point: best_extracted has API data
            dob = best_extracted['dob']
            report_token = best_extracted['report_token']
            primary_address = best_extracted['primary_address']
            primary_phone = best_extracted['primary_phone']
            primary_email = best_extracted['primary_email']
            sb_firstname = best_extracted['firstname']
            sb_lastname = best_extracted['lastname']
            middlename = best_extracted['middlename']

            ssn_found = len(ssn_matches) > 0

            # Abuse tracking
            is_full_dob_range = not dob or dob.strip() == ''
            abuse_type = 'full_dob_range' if is_full_dob_range else 'same_not_found'
            if not ssn_found:
                abuse_type = 'same_not_found'

            is_abuse, ban_reason = await check_abuse_patterns(
                db=db, user_id=user_id,
                firstname=firstname, lastname=lastname,
                address=address, dob=dob, ssn_found=ssn_found
            )

            await log_abuse_tracking(
                db=db, user_id=user_id,
                search_params={
                    "firstname": firstname, "lastname": lastname,
                    "address": address, "dob": dob, "ssn_found": ssn_found
                },
                abuse_type=abuse_type,
                is_abuse=is_full_dob_range or (not ssn_found and abuse_type == 'same_not_found'),
                consecutive_count=1
            )

            if is_abuse:
                # Ban user
                user_obj = await db.get(User, user_id)
                if user_obj:
                    await ban_user(db, user_obj, ban_reason)
                if search_log:
                    search_log.error_message = ban_reason
                # Update history entry → nf
                hist_stmt = (
                    update(TestSearchHistory)
                    .where(TestSearchHistory.id == history_entry_id)
                    .values(status='nf', found=False, search_time=round(time.monotonic() - search_start_time, 1))
                )
                await db.execute(hist_stmt)
                await db.commit()
                return

            input_fullname = fullname.strip().title()
            input_address = address.strip().title()

            if ssn_found:
                # Build results
                results = []
                for ssn_record in ssn_matches:
                    result_item = InstantSSNResult(
                        firstname=ssn_record.get('firstname') or sb_firstname,
                        lastname=ssn_record.get('lastname') or sb_lastname,
                        middlename=ssn_record.get('middlename') or middlename,
                        dob=dob or ssn_record.get('dob'),
                        address=ssn_record.get('address') or (primary_address.get('full_street') if (primary_address and isinstance(primary_address, dict)) else None),
                        city=ssn_record.get('city') or (primary_address.get('city') if (primary_address and isinstance(primary_address, dict)) else None),
                        state=ssn_record.get('state') or (primary_address.get('state') if (primary_address and isinstance(primary_address, dict)) else None),
                        zip_code=ssn_record.get('zip') or (primary_address.get('zip_code') if (primary_address and isinstance(primary_address, dict)) else None),
                        phone=ssn_record.get('phone') or primary_phone,
                        email=ssn_record.get('email') or primary_email,
                        ssn=ssn_record.get('ssn'),
                        ssn_found=True,
                        report_token=report_token,
                        local_db_data={
                            'firstname': ssn_record.get('firstname'),
                            'lastname': ssn_record.get('lastname'),
                            'dob': ssn_record.get('dob'),
                            'address': ssn_record.get('address'),
                            'city': ssn_record.get('city'),
                            'state': ssn_record.get('state'),
                            'zip': ssn_record.get('zip'),
                            'phone': ssn_record.get('phone'),
                            'email': ssn_record.get('email'),
                            'source_table': ssn_record.get('source_table')
                        }
                    )
                    results.append(result_item)

                # Create order
                order_items = []
                for r in results:
                    order_items.append({
                        "ssn": r.ssn or "Not found",
                        "source_table": r.local_db_data.get('source_table') if r.local_db_data else "instant_ssn",
                        "price": str(instant_ssn_price),
                        "source": "instant_ssn",
                        "firstname": r.firstname,
                        "lastname": r.lastname,
                        "middlename": r.middlename,
                        "dob": r.dob,
                        "address": r.address,
                        "city": r.city,
                        "state": r.state,
                        "zip": r.zip_code,
                        "phone": r.phone,
                        "email": r.email,
                        "report_token": r.report_token,
                        "purchased_at": datetime.utcnow().isoformat(),
                        "ssn_found": r.ssn_found,
                        "search_method": matched_provider or "unknown"
                    })

                new_order = Order(
                    user_id=user_id,
                    items=order_items,
                    total_price=instant_ssn_price,
                    status=OrderStatus.completed,
                    order_type=OrderType.instant_ssn,
                    is_viewed=False
                )
                db.add(new_order)
                await db.commit()
                await db.refresh(new_order)

                # Update search log
                if search_log:
                    search_log.success = True
                    search_log.ssn_found = True
                    search_log.order_id = new_order.id
                    await db.commit()

                # Artificial delay 30-50 seconds so result doesn't appear instantly
                await asyncio.sleep(random.randint(30, 50))

                # Update history entry → done (use first match data)
                first_match = ssn_matches[0]
                hist_stmt = (
                    update(TestSearchHistory)
                    .where(TestSearchHistory.id == history_entry_id)
                    .values(
                        status='done',
                        found=True,
                        result_fullname=input_fullname,
                        result_address=first_match.get('address', ''),
                        ssn=first_match.get('ssn', ''),
                        dob=dob or first_match.get('dob') or '',
                        search_time=round(time.monotonic() - search_start_time, 1),
                    )
                )
                await db.execute(hist_stmt)
                await db.commit()

                logger.info(f"Background search done for {username}: found {len(ssn_matches)} SSN(s)")
            else:
                # Not found — create manual ticket if flow allows
                if flow_config["has_manual_fallback"]:
                    new_ticket = ManualSSNTicket(
                        user_id=user_id,
                        firstname=firstname,
                        lastname=lastname,
                        address=address,
                        status=TicketStatus.pending,
                        source=source,
                        test_search_history_id=history_entry_id
                    )
                    db.add(new_ticket)

                    if search_log:
                        search_log.success = False
                        search_log.ssn_found = False
                        search_log.error_message = "No SSN found — sent to worker"

                    hist_stmt = (
                        update(TestSearchHistory)
                        .where(TestSearchHistory.id == history_entry_id)
                        .values(
                            result_fullname=input_fullname,
                            result_address=address,
                        )
                    )
                    await db.execute(hist_stmt)
                    await db.commit()

                    logger.info(f"No SSN found for {firstname} {lastname} — ticket {new_ticket.id} created for worker (status stays processing)")
                    await _notify_worker_new_ticket()
                else:
                    # No manual fallback — mark as not found
                    if search_log:
                        search_log.success = False
                        search_log.ssn_found = False
                        search_log.error_message = "No SSN found — no manual fallback"

                    hist_stmt = (
                        update(TestSearchHistory)
                        .where(TestSearchHistory.id == history_entry_id)
                        .values(
                            status='nf',
                            found=False,
                            result_fullname=input_fullname,
                            result_address=address,
                            search_time=round(time.monotonic() - search_start_time, 1),
                        )
                    )
                    await db.execute(hist_stmt)
                    await db.commit()

                    logger.info(f"No SSN found for {firstname} {lastname} — no manual fallback, marked as nf")

        except SearchbugAPIError as e:  # WhitepagesAPIError temporarily disabled
            error_msg = e.message if hasattr(e, 'message') else str(e)
            logger.error(f"API error in background search: {error_msg}")
            try:
                refund_stmt = (
                    update(User)
                    .where(User.id == user_id)
                    .values(balance=User.balance + instant_ssn_price)
                )
                await db.execute(refund_stmt)
                search_log_obj = await db.get(InstantSSNSearch, search_log_id)
                if search_log_obj:
                    search_log_obj.error_message = f"API error: {error_msg} — refunded"
                    search_log_obj.user_charged = Decimal("0.00")
                hist_stmt = (
                    update(TestSearchHistory)
                    .where(TestSearchHistory.id == history_entry_id)
                    .values(status='nf', found=False, search_time=round(time.monotonic() - search_start_time, 1))
                )
                await db.execute(hist_stmt)
                await db.commit()
            except Exception:
                logger.critical(f"Failed to refund after API error for user {user_id}")

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in background search: {str(e)}", exc_info=True)
            try:
                refund_stmt = (
                    update(User)
                    .where(User.id == user_id)
                    .values(balance=User.balance + instant_ssn_price)
                )
                await db.execute(refund_stmt)
                search_log_obj = await db.get(InstantSSNSearch, search_log_id)
                if search_log_obj:
                    search_log_obj.error_message = f"Unexpected error: {str(e)} — refunded"
                    search_log_obj.user_charged = Decimal("0.00")
                hist_stmt = (
                    update(TestSearchHistory)
                    .where(TestSearchHistory.id == history_entry_id)
                    .values(status='nf', found=False, search_time=round(time.monotonic() - search_start_time, 1))
                )
                await db.execute(hist_stmt)
                await db.commit()
            except Exception:
                logger.critical(f"Failed to refund after error for user {user_id}")


@router.post("/unified-search", response_model=UnifiedSearchResponse)
async def unified_search(
    request: UnifiedSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Unified search: fullname + address → charge $2 → return immediately → search in background.

    Flow:
    1. Parse fullname into firstname + lastname
    2. Check ban, maintenance, balance
    3. Atomic balance deduction ($2)
    4. Create TestSearchHistory with status='processing'
    5. Return immediately with history_entry_id + new_balance
    6. Background task: SearchBug → two-level DB search → update status to 'done'/'nf'
    """
    # Parse fullname into firstname + lastname
    name_parts = request.fullname.strip().split()
    if len(name_parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Full name must contain at least first name and last name"
        )
    firstname = name_parts[0]
    lastname = name_parts[-1]

    logger.info(
        f"Unified search: user={current_user.username}, "
        f"name={firstname} {lastname}, address={request.address}"
    )

    # Step 0: Check ban
    check_user_ban(current_user)

    # Check maintenance
    is_maintenance, maintenance_message = await check_maintenance_mode(db, 'instant_ssn')
    if is_maintenance:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=maintenance_message or "Service is currently under maintenance."
        )

    # Get custom price
    from api.common.pricing import get_default_instant_ssn_price
    default_instant_price2 = await get_default_instant_ssn_price(db)
    instant_ssn_price = await get_user_price(
        db=db,
        access_code=current_user.access_code or '',
        service_name='instant_ssn',
        default_price=default_instant_price2
    )

    # Check balance
    if current_user.balance < instant_ssn_price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${instant_ssn_price}, Available: ${current_user.balance}"
        )

    # Determine source
    if request.source == "telegram_bot":
        source = RequestSource.telegram_bot
    elif request.source == "web":
        source = RequestSource.web
    else:
        source = RequestSource.other

    # Atomic balance deduction
    stmt = (
        update(User)
        .where(User.id == current_user.id, User.balance >= instant_ssn_price)
        .values(balance=User.balance - instant_ssn_price)
        .returning(User.balance)
    )
    result = await db.execute(stmt)
    new_balance_row = result.fetchone()

    if new_balance_row is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient balance. Required: ${instant_ssn_price}"
        )

    new_balance = float(new_balance_row[0])
    logger.info(f"Charged ${instant_ssn_price} from user {current_user.username}. New balance: ${new_balance}")

    # Create search log
    sanitized_params = sanitize_metadata({
        "fullname": request.fullname,
        "address": request.address
    }, max_depth=3, max_size=5000) or {}

    search_log = InstantSSNSearch(
        user_id=current_user.id,
        search_params=sanitized_params,
        success=False,
        ssn_found=False,
        api_cost=SEARCHBUG_API_COST,
        user_charged=instant_ssn_price,
        source=source
    )
    db.add(search_log)

    # Create history entry with status='processing'
    input_fullname = request.fullname.strip().title()
    input_address = request.address.strip().title()
    history_entry = TestSearchHistory(
        user_id=current_user.id,
        input_fullname=input_fullname,
        input_address=input_address,
        result_fullname='',
        result_address='',
        ssn='',
        dob=None,
        found=False,
        status='processing',
        search_source='unified_search'
    )
    db.add(history_entry)
    await db.commit()
    await db.refresh(search_log)
    await db.refresh(history_entry)

    # Launch background search task
    asyncio.create_task(_run_search_background(
        user_id=current_user.id,
        username=current_user.username,
        history_entry_id=history_entry.id,
        search_log_id=search_log.id,
        firstname=firstname,
        lastname=lastname,
        fullname=request.fullname,
        address=request.address,
        instant_ssn_price=instant_ssn_price,
        source=source,
    ))

    # Return immediately
    return UnifiedSearchResponse(
        success=True,
        found=False,
        charged_amount=float(instant_ssn_price),
        new_balance=new_balance,
        message="Search started. Results will appear shortly."
    )


@router.post("/search-db", response_model=SearchDBResponse)
async def search_db(
    request: SearchDBRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_postgres_session)
):
    """
    Direct database search by SSN (admin only).

    Searches ClickHouse database for fullz records matching the SSN.
    Supports full SSN (XXX-XX-XXXX) or last 4 digits.

    Args:
        request: SearchDBRequest with SSN to search
        current_user: Current authenticated user (must be admin)
        db: Database session

    Returns:
        SearchDBResponse with matching records
    """
    # Check admin access
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    logger.info(f"Search DB: user={current_user.username}, ssn={request.ssn[:4]}...")

    try:
        # Get search engine
        engine = get_search_engine()

        # Search by SSN
        results_json = engine.search_by_ssn(request.ssn, limit=100)
        results_data = json.loads(results_json)

        # Convert to response model
        records = []
        for record in results_data:
            records.append(SearchDBRecord(
                id=record.get('id'),
                ssn=record.get('ssn', ''),
                firstname=record.get('firstname'),
                lastname=record.get('lastname'),
                middlename=record.get('middlename'),
                dob=record.get('dob'),
                address=record.get('address'),
                city=record.get('city'),
                state=record.get('state'),
                zip=record.get('zip'),
                phone=record.get('phone'),
                email=record.get('email'),
                source_table=record.get('source_table')
            ))

        logger.info(f"Search DB completed: found {len(records)} records")

        return SearchDBResponse(
            query=request.ssn,
            results=records,
            count=len(records)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search DB error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )
