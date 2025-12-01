"""
Search router for Public API (integration with SearchEngine).
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from typing import List
import json
import logging
from decimal import Decimal
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from database.search_engine import SearchEngine
from database.data_manager import DataManager
from api.common.database import SQLITE_PATH, get_postgres_session
from api.common.models_sqlite import (
    SSNRecord, SearchBySSNRequest, SearchByNameRequest,
    InstantSSNRequest, InstantSSNResponse, InstantSSNResult
)
from api.public.dependencies import get_current_user, limiter
from api.common.models_postgres import User, Order, OrderStatus, OrderType, InstantSSNSearch, InstantSSNAbuseTracking
from api.common.searchbug_client import create_searchbug_client, SearchbugAPIError
from sqlalchemy import select, desc
from api.common.pricing import INSTANT_SSN_PRICE, MANUAL_SSN_PRICE, REVERSE_SSN_PRICE, SEARCHBUG_API_COST, check_maintenance_mode, get_user_price
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
    search_engine = SearchEngine(db_path=SQLITE_PATH)

    # Determine search type and perform search
    if request.zip:
        # Search by name + zip
        results_json = search_engine.search_by_name_zip(
            request.firstname,
            request.lastname,
            request.zip,
            limit=request.limit
        )
        search_params = {
            'firstname': request.firstname,
            'lastname': request.lastname,
            'zip': request.zip
        }
    elif request.address:
        # Search by name + address
        results_json = search_engine.search_by_name_address(
            request.firstname,
            request.lastname,
            request.address,
            limit=request.limit
        )
        search_params = {
            'firstname': request.firstname,
            'lastname': request.lastname,
            'address': request.address
        }
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
        HTTPException: If record not found
    """
    data_manager = DataManager(db_path=SQLITE_PATH)

    # Search in both tables
    for table_name in ['ssn_1', 'ssn_2']:
        record = data_manager.get_record(table_name, ssn)
        if record is not None:
            record['source_table'] = table_name
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

    # Not found in any table - log before raising
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

    # Get custom price for this user or use default
    instant_ssn_price = await get_user_price(
        db=db,
        access_code=current_user.access_code or '',
        service_name='instant_ssn',
        default_price=INSTANT_SSN_PRICE
    )

    # Determine source from request
    from api.common.models_postgres import RequestSource
    if request.source == "telegram_bot":
        source = RequestSource.telegram_bot
    elif request.source == "web":
        source = RequestSource.web
    else:
        source = RequestSource.other

    # Create initial search log entry
    search_log = InstantSSNSearch(
        user_id=current_user.id,
        search_params={
            "firstname": request.firstname,
            "lastname": request.lastname,
            "address": request.address
        },
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
        # Step 1: Search external API
        async with create_searchbug_client() as searchbug:
            searchbug_data = await searchbug.search_person_unified(
                firstname=request.firstname,
                lastname=request.lastname,
                address=request.address
            )

        # Check if external API returned data
        if not searchbug_data:
            logger.info("No data found - no charge")

            # Update search log - no data found
            search_log.error_message = "No data found"
            await db.commit()

            # No data found - don't charge, don't create order
            return InstantSSNResponse(
                success=True,
                results=[],
                data_found=False,
                ssn_matches_found=0,
                message="No data found for the given search criteria",
                new_balance=float(current_user.balance)
            )

        logger.info(f"External API returned data for {request.firstname} {request.lastname}")

        # Extract primary (current) data
        primary_address = searchbug_data.get('primary_address')
        primary_phone = searchbug_data.get('primary_phone')
        primary_email = searchbug_data.get('primary_email')
        names = searchbug_data.get('names', [])
        dob = searchbug_data.get('dob', '')
        report_token = searchbug_data.get('report_token', '')

        # For local DB search - still need aggregated data
        all_zips = searchbug_data.get('all_zips', [])
        all_phones = searchbug_data.get('all_phones', [])
        addresses = searchbug_data.get('addresses', [])

        # Get primary name
        firstname = request.firstname
        lastname = request.lastname
        middlename = None
        if names and len(names) > 0:
            firstname = names[0].get('first_name', request.firstname)
            lastname = names[0].get('last_name', request.lastname)
            middlename = names[0].get('middle_name')

        # Безопасное извлечение адреса для логирования
        primary_street = None
        if primary_address and isinstance(primary_address, dict):
            primary_street = primary_address.get('full_street')

        logger.info(
            f"Primary data: address={primary_street}, "
            f"phone={primary_phone}, email={primary_email}"
        )

        # Step 2: Search local SSN database using external API data
        # Extract full_street addresses and states
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

        # Extract phone numbers from all_phones (now List[dict])
        phone_numbers = []
        if all_phones and len(all_phones) > 0:
            for phone_obj in all_phones:
                if isinstance(phone_obj, dict):
                    phone_num = phone_obj.get('phone_number', '')
                    if phone_num:
                        phone_numbers.append(phone_num)
                elif isinstance(phone_obj, str):
                    # Fallback for backward compatibility
                    phone_numbers.append(phone_obj)

        search_engine = SearchEngine(db_path=SQLITE_PATH)
        ssn_matches = search_engine.search_by_searchbug_data(
            firstname=firstname,
            lastname=lastname,
            all_zips=all_zips,
            all_phones=phone_numbers,
            all_addresses=all_addresses,
            all_states=all_states
        )

        logger.info(f"Found {len(ssn_matches)} SSN match(es) in local database")

        # Step 2.5: Filter by DOB if multiple matches found
        if len(ssn_matches) > 1:
            ssn_matches = filter_by_dob(ssn_matches, dob)
            logger.info(f"After DOB filtering: {len(ssn_matches)} SSN match(es)")

        # Step 2.6: Remove duplicate SSNs
        ssn_matches = deduplicate_by_ssn(ssn_matches)

        # Step 2.7: Apply rules for multiple SSN matches
        # Collect unique SSNs (filter out None)
        unique_ssns = set(match.get('ssn') for match in ssn_matches if match.get('ssn'))

        # Rule: If there are 2+ different SSNs, try to filter by exact DOB match first
        if len(unique_ssns) >= 2:
            logger.info(f"Found {len(unique_ssns)} different SSNs, attempting DOB-based selection")

            # If we have DOB from external API, try to find exact match
            normalized_searchbug_dob = normalize_dob(dob) if dob else ''

            if normalized_searchbug_dob:
                exact_dob_matches = []
                for match in ssn_matches:
                    local_dob = normalize_dob(match.get('dob', ''))
                    if local_dob == normalized_searchbug_dob:
                        exact_dob_matches.append(match)

                if len(exact_dob_matches) == 1:
                    # Found exactly one record with matching DOB - use it
                    logger.info(f"Found 1 record with exact DOB match, using it instead of rejecting")
                    ssn_matches = exact_dob_matches
                elif len(exact_dob_matches) > 1:
                    # Multiple records with same DOB but different SSNs - still ambiguous
                    exact_ssns = set(m.get('ssn') for m in exact_dob_matches if m.get('ssn'))
                    if len(exact_ssns) == 1:
                        # All DOB matches have same SSN - use best one
                        best_record = max(
                            exact_dob_matches,
                            key=lambda r: sum(1 for v in r.values() if v and str(v).strip())
                        )
                        ssn_matches = [best_record]
                        logger.info(f"Multiple DOB matches with same SSN, using best record")
                    else:
                        # Multiple different SSNs even with DOB match - reject
                        logger.info(f"Found {len(exact_ssns)} different SSNs even with DOB match, rejecting")
                        ssn_matches = []
                else:
                    # No exact DOB matches - try fuzzy matching for incomplete dates
                    logger.info(f"No exact DOB matches, trying fuzzy matching for incomplete dates")
                    fuzzy_dob_matches = []

                    for match in ssn_matches:
                        local_dob = normalize_dob(match.get('dob', ''))

                        # Check if local DOB is incomplete (ends with 0000 or 00)
                        if local_dob and len(local_dob) == 8:
                            # Case 1: Only year is known (YYYY0000)
                            if local_dob.endswith('0000'):
                                # Compare only year (first 4 chars)
                                if normalized_searchbug_dob[:4] == local_dob[:4]:
                                    fuzzy_dob_matches.append(match)
                                    logger.info(f"Fuzzy match: Year matches ({local_dob[:4]}) - DB has incomplete DOB {local_dob}")
                            # Case 2: Year and month known (YYYYMM00)
                            elif local_dob.endswith('00'):
                                # Compare year and month (first 6 chars)
                                if normalized_searchbug_dob[:6] == local_dob[:6]:
                                    fuzzy_dob_matches.append(match)
                                    logger.info(f"Fuzzy match: Year+Month matches ({local_dob[:6]}) - DB has incomplete DOB {local_dob}")

                    if len(fuzzy_dob_matches) == 1:
                        # Found exactly one fuzzy match
                        logger.info(f"✓ Found 1 fuzzy DOB match (incomplete date in DB), using it")
                        ssn_matches = fuzzy_dob_matches
                    elif len(fuzzy_dob_matches) > 1:
                        # Multiple fuzzy matches - check if same SSN
                        fuzzy_ssns = set(m.get('ssn') for m in fuzzy_dob_matches if m.get('ssn'))
                        if len(fuzzy_ssns) == 1:
                            # All fuzzy matches have same SSN - use best one
                            best_record = max(
                                fuzzy_dob_matches,
                                key=lambda r: sum(1 for v in r.values() if v and str(v).strip())
                            )
                            ssn_matches = [best_record]
                            logger.info(f"✓ Multiple fuzzy matches with same SSN, using best record")
                        else:
                            # Multiple different SSNs with fuzzy match - reject
                            logger.info(f"✗ Found {len(fuzzy_ssns)} different SSNs with fuzzy DOB match, rejecting")
                            ssn_matches = []
                    else:
                        # No fuzzy matches either - reject all
                        logger.info(f"✗ No exact or fuzzy DOB matches among {len(unique_ssns)} SSNs, rejecting results")
                        ssn_matches = []
            else:
                # No external DOB to filter - reject all
                logger.info(f"Found {len(unique_ssns)} different SSNs without DOB for filtering, rejecting results")
                ssn_matches = []

        # Rule: If exactly 2 records with the same SSN (unique_ssns size is 1), merge them
        elif len(ssn_matches) == 2 and len(unique_ssns) == 1:
            logger.info(f"Found 2 records with same SSN, merging into one record")
            # Choose the record with more filled fields (same logic as deduplicate_by_ssn)
            best_record = max(
                ssn_matches,
                key=lambda r: sum(1 for v in r.values() if v and str(v).strip())
            )
            ssn_matches = [best_record]
            logger.info(f"Merged records: kept record with more filled fields (source_table: {best_record.get('source_table')})")

        # Rule: If no SSN found, don't show any data (already handled by ssn_matches being empty)

        # Step 2.7.5: FALLBACK - Try address+DOB+firstname search if no matches found
        # This handles cases where external API and local DB have different last names
        # (e.g., maiden name vs married name: Melendez vs Delbrey)
        if not ssn_matches and dob and all_addresses:
            logger.info(
                f"No matches with firstname+lastname, trying fallback: "
                f"address+DOB+firstname (handling potential name mismatch)"
            )
            try:
                fallback_matches = search_engine.search_by_address_dob_firstname(
                    addresses=all_addresses,
                    dob=dob,
                    firstname=firstname
                )
                if fallback_matches:
                    logger.info(
                        f"✓ Fallback successful: found {len(fallback_matches)} match(es) "
                        f"by address+DOB+firstname (different lastname in DB)"
                    )
                    ssn_matches = fallback_matches
                else:
                    logger.info("✗ Fallback: no matches by address+DOB+firstname")
            except Exception as e:
                logger.error(f"Error during fallback search: {e}", exc_info=True)

        # Step 2.8: Determine abuse type and prepare search parameters
        ssn_found = len(ssn_matches) > 0

        # Определяем abuse_type для текущего запроса
        is_full_dob_range = not dob or dob.strip() == ''
        abuse_type = 'full_dob_range' if is_full_dob_range else 'same_not_found'

        # Если SSN не найден и параметры fullname+address такие же, это может быть паттерн same_not_found
        if not ssn_found:
            abuse_type = 'same_not_found'

        # ВАЖНО: Проверяем паттерны злоупотреблений ДО записи текущего запроса
        # check_abuse_patterns сам учтет текущий запрос при подсчёте
        is_abuse, ban_reason = await check_abuse_patterns(
            db=db,
            user_id=current_user.id,
            firstname=request.firstname,
            lastname=request.lastname,
            address=request.address,
            dob=dob,
            ssn_found=ssn_found
        )

        # Записываем текущий запрос в InstantSSNAbuseTracking
        # consecutive_count всегда 1 для текущего запроса (источник истины - check_abuse_patterns)
        #
        # ВАЖНО: search_params содержит ПОЛЬЗОВАТЕЛЬСКИЙ ВВОД, а не нормализованные данные из внешнего API.
        # Это необходимо для корректного определения паттерна same_not_found:
        # - Пользователь может вводить одну и ту же фулку разными способами
        # - Сравнение идёт по тому, что пользователь ЗАПРОСИЛ, а не по тому, что вернул внешний API
        # - Внешний API может нормализовать "John" -> "Jonathan", но для abuse tracking это разные запросы
        await log_abuse_tracking(
            db=db,
            user_id=current_user.id,
            search_params={
                "firstname": request.firstname,  # Пользовательский ввод, НЕ из внешнего API
                "lastname": request.lastname,    # Пользовательский ввод, НЕ из внешнего API
                "address": request.address,      # Пользовательский ввод, НЕ из внешнего API
                "dob": dob,                      # DOB из внешнего API (для проверки full_dob_range)
                "ssn_found": ssn_found           # Флаг результата поиска
            },
            abuse_type=abuse_type,
            is_abuse=is_full_dob_range or (not ssn_found and abuse_type == 'same_not_found'),
            consecutive_count=1  # Всегда 1 - check_abuse_patterns считает последовательности
        )

        if is_abuse:
            # Ban user
            await ban_user(db, current_user, ban_reason)

            # Update search log
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
            # SSN found - create result for each match
            for ssn_record in ssn_matches:
                logger.info(f"SSN record from DB: {ssn_record}")
                result = InstantSSNResult(
                    firstname=firstname,
                    lastname=lastname,
                    middlename=middlename,
                    dob=dob,
                    # Primary (current) data from external API
                    address=primary_address.get('full_street') if (primary_address and isinstance(primary_address, dict)) else None,
                    city=primary_address.get('city') if (primary_address and isinstance(primary_address, dict)) else None,
                    state=primary_address.get('state') if (primary_address and isinstance(primary_address, dict)) else None,
                    zip_code=primary_address.get('zip_code') if (primary_address and isinstance(primary_address, dict)) else None,
                    phone=primary_phone,
                    email=primary_email,
                    # SSN from local database
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
            # No SSN found - return external API data without SSN
            result = InstantSSNResult(
                firstname=firstname,
                lastname=lastname,
                middlename=middlename,
                dob=dob,
                # Primary (current) data
                address=primary_address.get('full_street') if primary_address else None,
                city=primary_address.get('city') if primary_address else None,
                state=primary_address.get('state') if primary_address else None,
                zip_code=primary_address.get('zip_code') if primary_address else None,
                phone=primary_phone,
                email=primary_email,
                # No SSN found
                ssn=None,
                ssn_found=False,
                report_token=report_token
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

            # Create order for purchased Instant SSN search
            order_items = []
            for result in results:
                order_item = {
                    "ssn": result.ssn if result.ssn else "Not found",
                    "source_table": result.local_db_data.get('source_table') if result.local_db_data else "instant_ssn",
                    "ssn_record_id": f"{result.local_db_data.get('source_table', 'instant_ssn')}:{result.ssn}" if result.ssn else "instant_ssn:not_found",
                    "price": str(instant_ssn_price),
                    "source": "instant_ssn",
                    # Personal info
                    "firstname": result.firstname,
                    "lastname": result.lastname,
                    "middlename": result.middlename,
                    "dob": result.dob,
                    # Address info
                    "address": result.address,
                    "city": result.city,
                    "state": result.state,
                    "zip": result.zip_code,
                    # Contact info
                    "phone": result.phone,
                    "email": result.email,
                    # Metadata
                    "report_token": result.report_token,
                    "purchased_at": datetime.utcnow().isoformat(),
                    "ssn_found": result.ssn_found
                }
                order_items.append(order_item)

            # Create order in database
            new_order = Order(
                user_id=current_user.id,
                items=order_items,
                total_price=instant_ssn_price,
                status=OrderStatus.completed,
                order_type=OrderType.instant_ssn,  # Instant SSN via external API
                is_viewed=False
            )
            db.add(new_order)
            await db.commit()
            await db.refresh(new_order)

            logger.info(
                f"Created order {new_order.id} for Instant SSN search. "
                f"User: {current_user.username}, SSN matches: {len(ssn_matches)}"
            )

            # Update search log - success with SSN found
            search_log.success = True
            search_log.ssn_found = True
            search_log.order_id = new_order.id
            search_log.user_charged = instant_ssn_price
            await db.commit()
        else:
            logger.info(
                f"No SSN found for {request.firstname} {request.lastname} - user NOT charged"
            )

            # Update search log - external API returned data but no SSN match
            search_log.success = False
            search_log.ssn_found = False
            search_log.error_message = "No SSN matches found in local database"
            await db.commit()

        return InstantSSNResponse(
            success=True,
            results=results,
            data_found=True,
            ssn_matches_found=len(ssn_matches),
            message=f"Found {len(ssn_matches)} SSN match(es)" if ssn_matches else "No SSN matches found in database",
            new_balance=float(current_user.balance),
            order_id=str(new_order.id) if ssn_matches else None,
            charged_amount=float(instant_ssn_price) if ssn_matches else None
        )

    except SearchbugAPIError as e:
        logger.error(f"External API error: {e.message}")
        # Update search log with error
        search_log.error_message = f"External API error: {e.message}"
        await db.commit()
        # No refund needed - user was not charged yet
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service is temporarily unavailable: {e.message}"
        )
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        # Update search log with error
        search_log.error_message = f"Validation error: {str(e)}"
        await db.commit()
        # No refund needed - user was not charged yet
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in instant_ssn_search: {str(e)}", exc_info=True)
        # Update search log with error
        search_log.error_message = f"Unexpected error: {str(e)}"
        await db.commit()
        # No refund needed - user was not charged yet
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during Instant SSN search"
        )
