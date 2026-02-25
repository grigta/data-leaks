"""
Search Key Generator - генератор ключей для точного поиска (Уровень 2)

Создаёт 16 типов ключей для точного matching с SearchBug данными:

Ключи 1-8: с полным именем (FN)
| # | Ключ                           | Пример                           |
|---|--------------------------------|----------------------------------|
| 1 | FN:MN:LN:DOB_YEAR:PHONE        | john:m:wick:1990:5551234567      |
| 2 | FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE | john:m:wick:1990:123:main:fl |
| 3 | FN:LN:DOB_YEAR:PHONE           | john:wick:1990:5551234567        |
| 4 | FN:LN:DOB_YEAR:ADDR#:STREET:STATE | john:wick:1990:123:main:fl     |
| 5 | FN:MN:LN:PHONE                 | john:m:wick:5551234567           |
| 6 | FN:MN:LN:ADDR#:STREET:STATE    | john:m:wick:123:main:fl          |
| 7 | FN:LN:ADDR#:STREET:STATE       | john:wick:123:main:fl            |
| 8 | FN:LN:PHONE                    | john:wick:5551234567             |

Ключи 9-16: с первой буквой имени (FN1) — для matching записей с инициалами
| 9  | FN1:MN:LN:DOB_YEAR:PHONE       | j:m:wick:1990:5551234567         |
| 10 | FN1:MN:LN:DOB_YEAR:ADDR#:STREET:STATE | j:m:wick:1990:123:main:fl |
| 11 | FN1:LN:DOB_YEAR:PHONE          | j:wick:1990:5551234567           |
| 12 | FN1:LN:DOB_YEAR:ADDR#:STREET:STATE | j:wick:1990:123:main:fl       |
| 13 | FN1:MN:LN:PHONE                | j:m:wick:5551234567              |
| 14 | FN1:MN:LN:ADDR#:STREET:STATE   | j:m:wick:123:main:fl             |
| 15 | FN1:LN:ADDR#:STREET:STATE      | j:wick:123:main:fl               |
| 16 | FN1:LN:PHONE                   | j:wick:5551234567                |

Правила парсинга:
- FN: полное имя (lowercase)
- FN1: первая буква имени (lowercase)
- LN: полное имя фамилии (lowercase, без приставок)
- MN: только первая буква middle name (lowercase)
- DOB: 4-значный год
- Phone: 10 цифр (без ведущей 1)
- Address: addr# + street name (без суффиксов) + state
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

from database.bloom_key_generator import (
    NAME_PREFIXES,
    LASTNAME_PREFIXES,
    LASTNAME_PREFIXES_MULTI,
    LASTNAME_PREFIXES_SPECIAL,
    parse_address_for_bloom,
    normalize_phone_for_bloom,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Константы
# =============================================================================

# Инициалы и короткие приставки, которые нужно игнорировать в lastname
LASTNAME_INITIALS_TO_SKIP = {'M', 'A', 'J', 'L', 'R'}


# =============================================================================
# Парсинг имён (FN, MN, LN)
# =============================================================================

def parse_fullname(
    firstname: str,
    middlename: Optional[str],
    lastname: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Парсит имена для search key.

    Правила:
    - FN, LN: полное имя (lowercase)
    - MN: только первая буква (lowercase) или None
    - Пропускаем префиксы: Mr., Mrs., Ms., Miss, Dr., Jr., Sr.
    - Пропускаем приставки фамилий: de, de la, del, van, von, da, di, O', Mc, Mac, M., A., J., L., R.

    Args:
        firstname: Имя (может содержать префикс типа "Mr. John")
        middlename: Среднее имя (может быть None, инициал "M" или полное "Mike")
        lastname: Фамилия (может содержать приставки типа "del Toro")

    Returns:
        Tuple (fn, mn, ln) где:
        - fn: полное имя lowercase
        - mn: первая буква среднего имени lowercase или None
        - ln: полное имя фамилии lowercase (без приставок)

    Examples:
        >>> parse_fullname("John", None, "Wick")
        ('john', None, 'wick')
        >>> parse_fullname("John", "Mike", "Wick")
        ('john', 'm', 'wick')
        >>> parse_fullname("John", "M", "Wick")
        ('john', 'm', 'wick')
        >>> parse_fullname("Mr. John", "M.", "del Toro")
        ('john', 'm', 'toro')
        >>> parse_fullname("John", "M", "O'Brien")
        ('john', 'm', 'brien')
        >>> parse_fullname("John", None, "McDonald")
        ('john', None, 'donald')
    """
    # Парсим firstname
    fn = _parse_firstname_full(firstname)
    if not fn:
        return (None, None, None)

    # Парсим middlename
    mn = _parse_middlename(middlename)

    # Парсим lastname
    ln = _parse_lastname_full(lastname)
    if not ln:
        return (None, None, None)

    return (fn, mn, ln)


def _parse_firstname_full(firstname: str) -> Optional[str]:
    """
    Парсит firstname, возвращая полное имя без префиксов.

    Args:
        firstname: Имя (может содержать префикс типа "Mr. John")

    Returns:
        Полное имя lowercase или None

    Examples:
        >>> _parse_firstname_full("John")
        'john'
        >>> _parse_firstname_full("Mr. John")
        'john'
        >>> _parse_firstname_full("Dr. Jane")
        'jane'
    """
    if not firstname:
        return None

    # Убираем точки и разбиваем на части
    parts = firstname.upper().replace('.', '').split()

    for part in parts:
        # Пропускаем префиксы (MR, MRS, DR, etc.)
        if part in NAME_PREFIXES:
            continue
        # Пропускаем инициалы (одиночные буквы)
        if len(part) == 1:
            continue
        # Нашли имя
        if part and part[0].isalpha():
            return part.lower()

    return None


def _parse_middlename(middlename: Optional[str]) -> Optional[str]:
    """
    Парсит middlename, возвращая только первую букву.

    Args:
        middlename: Среднее имя (может быть None, "M", "M." или "Mike")

    Returns:
        Первая буква lowercase или None

    Examples:
        >>> _parse_middlename(None)
        None
        >>> _parse_middlename("")
        None
        >>> _parse_middlename("M")
        'm'
        >>> _parse_middlename("M.")
        'm'
        >>> _parse_middlename("Mike")
        'm'
    """
    if not middlename:
        return None

    # Убираем точки и пробелы
    clean = middlename.strip().replace('.', '').strip()

    if not clean:
        return None

    # Берём первую букву
    first_char = clean[0]
    if first_char.isalpha():
        return first_char.lower()

    return None


def _parse_lastname_full(lastname: str) -> Optional[str]:
    """
    Парсит lastname, возвращая полное имя без приставок.

    Приставки для пропуска:
    - de, de la, del, van, von, da, di
    - O', Mc, Mac
    - M., A., J., L., R.

    Args:
        lastname: Фамилия

    Returns:
        Полное имя фамилии lowercase или None

    Examples:
        >>> _parse_lastname_full("Wick")
        'wick'
        >>> _parse_lastname_full("del Toro")
        'toro'
        >>> _parse_lastname_full("Van Der Berg")
        'berg'
        >>> _parse_lastname_full("O'Brien")
        'brien'
        >>> _parse_lastname_full("McDonald")
        'donald'
        >>> _parse_lastname_full("MacArthur")
        'arthur'
        >>> _parse_lastname_full("M. Smith")
        'smith'
    """
    if not lastname:
        return None

    # Нормализуем для проверки
    lastname_upper = lastname.upper().strip()

    # Проверяем специальные префиксы O', Mc, Mac
    for prefix in LASTNAME_PREFIXES_SPECIAL:
        prefix_upper = prefix.upper()
        if lastname_upper.startswith(prefix_upper):
            # Берём часть после префикса
            remaining = lastname[len(prefix_upper):]
            if remaining:
                # Если это O'Brien, remaining = Brien
                return remaining.lower()

    # Разбиваем на части (заменяем ' на пробел)
    parts = lastname_upper.replace("'", " ").replace(".", " ").split()

    # Проверяем многословные префиксы (DE LA, VAN DER)
    if len(parts) >= 2:
        two_word = f"{parts[0]} {parts[1]}"
        if two_word in LASTNAME_PREFIXES_MULTI:
            parts = parts[2:]

    # Пропускаем одиночные префиксы и инициалы
    for part in parts:
        # Пропускаем приставки (DE, VAN, VON, etc.)
        if part in LASTNAME_PREFIXES:
            continue
        # Пропускаем одиночные инициалы (M, A, J, L, R)
        if part in LASTNAME_INITIALS_TO_SKIP:
            continue
        # Нашли фамилию
        if part and part[0].isalpha():
            return part.lower()

    return None


# =============================================================================
# Парсинг DOB (год рождения)
# =============================================================================

def extract_dob_year(dob: str) -> Optional[str]:
    """
    Извлекает 4-значный год из DOB в любом формате.

    Поддерживаемые форматы:
    - MM/DD/YYYY (01/02/1990)
    - MMDDYYYY (01021990)
    - YYYY/MM/DD (1990/01/02)
    - YYYYMMDD (19900102)
    - YYYY-MM-DD (1990-01-02)
    - DD-MM-YYYY (02-01-1990)

    Args:
        dob: Дата рождения в любом формате

    Returns:
        4-значный год как строка или None

    Examples:
        >>> extract_dob_year("01/02/1990")
        '1990'
        >>> extract_dob_year("01021990")
        '1990'
        >>> extract_dob_year("1990/01/02")
        '1990'
        >>> extract_dob_year("19900102")
        '1990'
        >>> extract_dob_year("1990-01-02")
        '1990'
    """
    if not dob:
        return None

    dob_str = str(dob).strip()
    if not dob_str:
        return None

    # Ищем 4-значное число, которое может быть годом (1900-2100)
    # Сначала пробуем найти год в начале (YYYY-MM-DD или YYYYMMDD)
    match = re.match(r'^(19\d{2}|20\d{2})', dob_str)
    if match:
        return match.group(1)

    # Ищем год в конце (MM/DD/YYYY или MMDDYYYY)
    match = re.search(r'(19\d{2}|20\d{2})$', dob_str)
    if match:
        return match.group(1)

    # Ищем год в любом месте
    match = re.search(r'(19\d{2}|20\d{2})', dob_str)
    if match:
        return match.group(1)

    return None


# =============================================================================
# Генерация 8 ключей
# =============================================================================

def generate_search_keys(
    firstname: str,
    middlename: Optional[str],
    lastname: str,
    dob: Optional[str],
    phone: Optional[str],
    address: Optional[str],
    state: Optional[str]
) -> Dict[str, Optional[str]]:
    """
    Генерирует все 8 search keys для одной записи.

    8 типов ключей (все lowercase):
    1. FN:MN:LN:DOB_YEAR:PHONE
    2. FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
    3. FN:LN:DOB_YEAR:PHONE
    4. FN:LN:DOB_YEAR:ADDR#:STREET:STATE
    5. FN:MN:LN:PHONE
    6. FN:MN:LN:ADDR#:STREET:STATE
    7. FN:LN:ADDR#:STREET:STATE
    8. FN:LN:PHONE

    Args:
        firstname: Имя
        middlename: Среднее имя (может быть None)
        lastname: Фамилия
        dob: Дата рождения (может быть None)
        phone: Телефон (может быть None)
        address: Адрес (может быть None)
        state: Штат (может быть None)

    Returns:
        Dict с 8 ключами:
        {
            'search_key_1': '...' или None,
            'search_key_2': '...' или None,
            ...
            'search_key_8': '...' или None
        }

    Examples:
        >>> keys = generate_search_keys(
        ...     firstname="John",
        ...     middlename="Mike",
        ...     lastname="Wick",
        ...     dob="01/02/1990",
        ...     phone="5551234567",
        ...     address="123 Main St",
        ...     state="FL"
        ... )
        >>> keys['search_key_1']
        'john:m:wick:1990:5551234567'
        >>> keys['search_key_8']
        'john:wick:5551234567'
    """
    result = {
        'search_key_1': None,  # FN:MN:LN:DOB:PHONE
        'search_key_2': None,  # FN:MN:LN:DOB:ADDR
        'search_key_3': None,  # FN:LN:DOB:PHONE
        'search_key_4': None,  # FN:LN:DOB:ADDR
        'search_key_5': None,  # FN:MN:LN:PHONE
        'search_key_6': None,  # FN:MN:LN:ADDR
        'search_key_7': None,  # FN:LN:ADDR
        'search_key_8': None,  # FN:LN:PHONE
    }

    # Парсим имена
    fn, mn, ln = parse_fullname(firstname, middlename, lastname)
    if not fn or not ln:
        return result

    # Парсим DOB
    dob_year = extract_dob_year(dob) if dob else None

    # Парсим телефон
    phone_normalized = normalize_phone_for_bloom(phone) if phone else None

    # Парсим адрес
    addr_num = None
    street_name = None
    state_normalized = None

    if address and state:
        addr_num, street_name = parse_address_for_bloom(address)
        if state and isinstance(state, str):
            state_clean = state.upper().strip()
            if len(state_clean) == 2 and state_clean.isalpha():
                state_normalized = state_clean.lower()

    # Генерируем ключи

    # Ключ 1: FN:MN:LN:DOB:PHONE (требует mn, dob_year, phone)
    if mn and dob_year and phone_normalized:
        result['search_key_1'] = f"{fn}:{mn}:{ln}:{dob_year}:{phone_normalized}"

    # Ключ 2: FN:MN:LN:DOB:ADDR (требует mn, dob_year, addr, state)
    if mn and dob_year and addr_num and street_name and state_normalized:
        result['search_key_2'] = f"{fn}:{mn}:{ln}:{dob_year}:{addr_num}:{street_name}:{state_normalized}"

    # Ключ 3: FN:LN:DOB:PHONE (требует dob_year, phone)
    if dob_year and phone_normalized:
        result['search_key_3'] = f"{fn}:{ln}:{dob_year}:{phone_normalized}"

    # Ключ 4: FN:LN:DOB:ADDR (требует dob_year, addr, state)
    if dob_year and addr_num and street_name and state_normalized:
        result['search_key_4'] = f"{fn}:{ln}:{dob_year}:{addr_num}:{street_name}:{state_normalized}"

    # Ключ 5: FN:MN:LN:PHONE (требует mn, phone)
    if mn and phone_normalized:
        result['search_key_5'] = f"{fn}:{mn}:{ln}:{phone_normalized}"

    # Ключ 6: FN:MN:LN:ADDR (требует mn, addr, state)
    if mn and addr_num and street_name and state_normalized:
        result['search_key_6'] = f"{fn}:{mn}:{ln}:{addr_num}:{street_name}:{state_normalized}"

    # Ключ 7: FN:LN:ADDR (требует addr, state)
    if addr_num and street_name and state_normalized:
        result['search_key_7'] = f"{fn}:{ln}:{addr_num}:{street_name}:{state_normalized}"

    # Ключ 8: FN:LN:PHONE (требует phone)
    if phone_normalized:
        result['search_key_8'] = f"{fn}:{ln}:{phone_normalized}"

    return result


def generate_search_keys_from_searchbug(searchbug_data: Dict) -> Dict[str, List[str]]:
    """
    Генерирует все возможные search keys из данных SearchBug API.

    SearchBug возвращает массивы телефонов, адресов, DOB И ИМЁН для одного человека.
    Для каждой комбинации (имя × DOB × телефон/адрес) генерируем отдельный ключ.

    ВАЖНО: SearchBug может вернуть несколько вариаций имён (aliases, maiden names).
    Мы генерируем ключи для ВСЕХ имён, чтобы найти записи с любой вариацией.

    Args:
        searchbug_data: Данные от SearchBug API с полями:
            - names: List[Dict] с полями first_name, middle_name, last_name (приоритет)
            - firstname: str (fallback если нет names)
            - middlename: str (fallback если нет names)
            - lastname: str (fallback если нет names)
            - dob: str (опционально) - может быть список или строка
            - phones: List[str] (опционально)
            - addresses: List[Dict] с полями address, state (опционально)

    Returns:
        Dict с ключами search_keys_1 .. search_keys_8, каждый - список уникальных ключей

    Examples:
        >>> data = {
        ...     "names": [
        ...         {"first_name": "Mary", "middle_name": "A", "last_name": "Johnson"},
        ...         {"first_name": "Mary", "middle_name": "A", "last_name": "Smith"}
        ...     ],
        ...     "dob": "01/02/1990",
        ...     "phones": ["5551234567"],
        ...     "addresses": [{"address": "123 Main St", "state": "FL"}]
        ... }
        >>> result = generate_search_keys_from_searchbug(data)
        >>> # Ключи генерируются для обоих имён
    """
    result = {
        'search_keys_1': [],
        'search_keys_2': [],
        'search_keys_3': [],
        'search_keys_4': [],
        'search_keys_5': [],
        'search_keys_6': [],
        'search_keys_7': [],
        'search_keys_8': [],
    }

    # Собираем все вариации имён (firstname, middlename, lastname)
    name_variations = []

    # Проверяем массив names (приоритет)
    names_list = searchbug_data.get('names', []) or []
    for name_item in names_list:
        if isinstance(name_item, dict):
            fn = name_item.get('first_name', '') or name_item.get('firstName', '')
            mn = name_item.get('middle_name', '') or name_item.get('middleName', '') or None
            ln = name_item.get('last_name', '') or name_item.get('lastName', '')
            if fn and ln:
                name_variations.append((fn, mn, ln))

    # Fallback на одиночные поля
    if not name_variations:
        firstname = searchbug_data.get('firstname', '')
        middlename = searchbug_data.get('middlename')
        lastname = searchbug_data.get('lastname', '')
        if firstname and lastname:
            name_variations.append((firstname, middlename, lastname))

    if not name_variations:
        return result

    # Получаем DOB (может быть строка или список)
    dob_raw = searchbug_data.get('dob')
    dobs = []
    if dob_raw:
        if isinstance(dob_raw, list):
            dobs = [d for d in dob_raw if d]
        else:
            dobs = [dob_raw]

    # Получаем телефоны
    phones = searchbug_data.get('phones', []) or []

    # Получаем адреса
    addresses = searchbug_data.get('addresses', []) or []

    # Если нет DOB - используем None
    dobs_to_iterate = dobs if dobs else [None]

    # Генерируем ключи для КАЖДОЙ комбинации имени × DOB × телефон/адрес
    for firstname, middlename, lastname in name_variations:
        for dob in dobs_to_iterate:
            # Для телефонов
            for phone in phones:
                keys = generate_search_keys(
                    firstname=firstname,
                    middlename=middlename,
                    lastname=lastname,
                    dob=dob,
                    phone=phone,
                    address=None,
                    state=None
                )

                for i in range(1, 9):
                    key = keys[f'search_key_{i}']
                    if key and key not in result[f'search_keys_{i}']:
                        result[f'search_keys_{i}'].append(key)

            # Для адресов
            for addr_data in addresses:
                if isinstance(addr_data, dict):
                    address = addr_data.get('address', '')
                    state = addr_data.get('state', '')

                    keys = generate_search_keys(
                        firstname=firstname,
                        middlename=middlename,
                        lastname=lastname,
                        dob=dob,
                        phone=None,
                        address=address,
                        state=state
                    )

                    for i in range(1, 9):
                        key = keys[f'search_key_{i}']
                        if key and key not in result[f'search_keys_{i}']:
                            result[f'search_keys_{i}'].append(key)

    return result


def generate_search_keys_for_record(record: Dict) -> Dict[str, Optional[str]]:
    """
    Генерирует search keys для одной записи из базы данных.

    Использует поля: firstname, middlename, lastname, dob, phone, address, state

    Args:
        record: Словарь с данными записи

    Returns:
        Dict с 8 ключами search_key_1..search_key_8
    """
    return generate_search_keys(
        firstname=record.get('firstname', ''),
        middlename=record.get('middlename'),
        lastname=record.get('lastname', ''),
        dob=record.get('dob'),
        phone=record.get('phone'),
        address=record.get('address'),
        state=record.get('state')
    )


def generate_search_keys_batch(
    records: List[Dict],
    id_field: str = 'id'
) -> List[Tuple[int, Dict[str, Optional[str]]]]:
    """
    Генерирует search keys для пакета записей.

    Используется для миграции существующих данных в ClickHouse.

    Args:
        records: Список записей с полями id, firstname, middlename, lastname, dob, phone, address, state
        id_field: Имя поля с ID записи

    Returns:
        Список кортежей (id, {search_key_1: ..., search_key_8: ...})
    """
    results = []

    for record in records:
        record_id = record.get(id_field)
        keys = generate_search_keys_for_record(record)
        results.append((record_id, keys))

    return results


# =============================================================================
# Level 2 Runtime Matching - генерация ключей для сравнения
# =============================================================================

def generate_query_keys_from_searchbug(searchbug_data: Dict) -> Dict[str, str]:
    """
    Генерирует ВСЕ возможные ключи запроса из SearchBug данных.

    Комбинирует все ИМЕНА, телефоны и адреса с MN и DOB_YEAR.
    Используется для Level 2 runtime matching.

    ВАЖНО: SearchBug может вернуть несколько вариаций имён (aliases, maiden names).
    Мы генерируем ключи для ВСЕХ имён, чтобы найти записи с любой вариацией.

    Args:
        searchbug_data: Данные от SearchBug API с полями:
            - names: List[Dict] с полями first_name, middle_name, last_name (приоритет)
            - firstname: str (fallback)
            - middlename: str (fallback)
            - lastname: str (fallback)
            - dob: str (опционально)
            - phones: List[str] или List[Dict] (опционально)
            - addresses: List[Dict] с полями address, state (опционально)

    Returns:
        Dict[str, str] - {key_value: method_name}

    Examples:
        >>> data = {
        ...     "names": [
        ...         {"first_name": "Mary", "middle_name": "A", "last_name": "Johnson"},
        ...         {"first_name": "Mary", "middle_name": "A", "last_name": "Smith"}
        ...     ],
        ...     "dob": "01/02/1990",
        ...     "phones": ["5551234567"],
        ...     "addresses": [{"address": "123 Main St", "state": "FL"}]
        ... }
        >>> keys = generate_query_keys_from_searchbug(data)
        >>> # keys = {"mary:a:johnson:1990:5551234567": "FN+MN+LN+DOB+PHONE", ...}
    """
    query_keys = {}

    # Собираем все вариации имён (firstname, middlename, lastname)
    name_variations = []

    # Проверяем массив names (приоритет)
    names_list = searchbug_data.get('names', []) or []
    for name_item in names_list:
        if isinstance(name_item, dict):
            fn = name_item.get('first_name', '') or name_item.get('firstName', '')
            mn = name_item.get('middle_name', '') or name_item.get('middleName', '') or None
            ln = name_item.get('last_name', '') or name_item.get('lastName', '')
            if fn and ln:
                name_variations.append((fn, mn, ln))

    # Fallback на одиночные поля
    if not name_variations:
        firstname = searchbug_data.get('firstname', '')
        middlename = searchbug_data.get('middlename')
        lastname = searchbug_data.get('lastname', '')
        if firstname and lastname:
            name_variations.append((firstname, middlename, lastname))

    if not name_variations:
        return query_keys

    # Получаем DOB
    dob = searchbug_data.get('dob')
    dob_year = extract_dob_year(dob) if dob else None

    # Извлекаем телефоны
    phones_raw = searchbug_data.get('phones', []) or []
    phones = []
    for p in phones_raw:
        if isinstance(p, dict):
            phone_num = p.get('phone_number', '')
        else:
            phone_num = str(p) if p else ''
        if phone_num:
            normalized = normalize_phone_for_bloom(phone_num)
            if normalized and normalized not in phones:
                phones.append(normalized)

    # Извлекаем адреса
    addresses_raw = searchbug_data.get('addresses', []) or []

    # Генерируем ключи для КАЖДОЙ вариации имени
    for firstname, middlename, lastname in name_variations:
        # Парсим имена
        fn, mn, ln = parse_fullname(firstname, middlename, lastname)
        if not fn or not ln:
            continue

        # fn1 — первая буква имени для ключей 9-16
        fn1 = fn[0]

        # Генерируем ключи для телефонов
        for phone in phones:
            # key1: FN:MN:LN:DOB_YEAR:PHONE
            if mn and dob_year:
                query_keys[f"{fn}:{mn}:{ln}:{dob_year}:{phone}"] = "FN+MN+LN+DOB+PHONE"
            # key3: FN:LN:DOB_YEAR:PHONE
            if dob_year:
                query_keys[f"{fn}:{ln}:{dob_year}:{phone}"] = "FN+LN+DOB+PHONE"
            # key5: FN:MN:LN:PHONE
            if mn:
                query_keys[f"{fn}:{mn}:{ln}:{phone}"] = "FN+MN+LN+PHONE"
            # key8: FN:LN:PHONE
            query_keys[f"{fn}:{ln}:{phone}"] = "FN+LN+PHONE"

            # --- Ключи 9-16 с первой буквой имени ---
            # key9: FN1:MN:LN:DOB_YEAR:PHONE
            if mn and dob_year:
                query_keys[f"{fn1}:{mn}:{ln}:{dob_year}:{phone}"] = "FN1+MN+LN+DOB+PHONE"
            # key11: FN1:LN:DOB_YEAR:PHONE
            if dob_year:
                query_keys[f"{fn1}:{ln}:{dob_year}:{phone}"] = "FN1+LN+DOB+PHONE"
            # key13: FN1:MN:LN:PHONE
            if mn:
                query_keys[f"{fn1}:{mn}:{ln}:{phone}"] = "FN1+MN+LN+PHONE"
            # key16: FN1:LN:PHONE
            query_keys[f"{fn1}:{ln}:{phone}"] = "FN1+LN+PHONE"

        # Генерируем ключи для адресов
        for addr_data in addresses_raw:
            if not isinstance(addr_data, dict):
                continue

            address = addr_data.get('address') or addr_data.get('full_street', '')
            state = addr_data.get('state', '')

            if not address or not state:
                continue

            addr_num, street = parse_address_for_bloom(address)
            if not addr_num or not street:
                continue

            state_normalized = state.upper().strip()
            if len(state_normalized) != 2 or not state_normalized.isalpha():
                continue
            state_normalized = state_normalized.lower()

            # key2: FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
            if mn and dob_year:
                query_keys[f"{fn}:{mn}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN+MN+LN+DOB+ADDR"
            # key4: FN:LN:DOB_YEAR:ADDR#:STREET:STATE
            if dob_year:
                query_keys[f"{fn}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN+LN+DOB+ADDR"
            # key6: FN:MN:LN:ADDR#:STREET:STATE
            if mn:
                query_keys[f"{fn}:{mn}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN+MN+LN+ADDR"
            # key7: FN:LN:ADDR#:STREET:STATE
            query_keys[f"{fn}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN+LN+ADDR"

            # --- Ключи 9-16 с первой буквой имени ---
            # key10: FN1:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
            if mn and dob_year:
                query_keys[f"{fn1}:{mn}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN1+MN+LN+DOB+ADDR"
            # key12: FN1:LN:DOB_YEAR:ADDR#:STREET:STATE
            if dob_year:
                query_keys[f"{fn1}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN1+LN+DOB+ADDR"
            # key14: FN1:MN:LN:ADDR#:STREET:STATE
            if mn:
                query_keys[f"{fn1}:{mn}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN1+MN+LN+ADDR"
            # key15: FN1:LN:ADDR#:STREET:STATE
            query_keys[f"{fn1}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN1+LN+ADDR"

    return query_keys


def generate_candidate_keys(
    candidate: Dict,
) -> Dict[str, str]:
    """
    Генерирует ключи кандидата для runtime matching.

    ВСЕ данные берутся из самой записи кандидата (ClickHouse).
    Никакого обмена данными с SearchBug — стороны сравниваются независимо.

    Args:
        candidate: Запись-кандидат из ClickHouse с полями:
            - firstname, lastname, middlename, dob, phone, address, state

    Returns:
        Dict[str, str] - {key_value: method_name}

    Examples:
        >>> candidate = {
        ...     'firstname': 'JOHN',
        ...     'middlename': 'M',
        ...     'lastname': 'WICK',
        ...     'dob': '19900115',
        ...     'phone': '5551234567',
        ...     'address': '123 Main St',
        ...     'state': 'FL'
        ... }
        >>> keys = generate_candidate_keys(candidate)
        >>> keys['john:m:wick:1990:5551234567']
        'FN+MN+LN+DOB+PHONE'
    """
    candidate_keys = {}

    # Извлекаем данные кандидата
    c_firstname = candidate.get('firstname', '')
    c_lastname = candidate.get('lastname', '')
    c_middlename = candidate.get('middlename', '')
    c_dob = candidate.get('dob', '')
    c_phone = candidate.get('phone')
    c_address = candidate.get('address')
    c_state = candidate.get('state')

    if not c_firstname or not c_lastname:
        return candidate_keys

    # MN и DOB из самой записи кандидата
    mn = _parse_middlename(c_middlename)
    dob_year = extract_dob_year(c_dob) if c_dob else None

    # Парсим имена кандидата
    fn, _, ln = parse_fullname(c_firstname, None, c_lastname)

    # Если fn = None (однобуквенное имя пропущено parse_fullname),
    # берём первую букву напрямую и парсим ln отдельно
    if not fn:
        fn_raw = c_firstname.strip()
        if fn_raw and fn_raw[0].isalpha():
            fn = fn_raw[0].lower()
        else:
            return candidate_keys
        # parse_fullname вернул ln=None из-за раннего return, парсим заново
        if not ln:
            ln = _parse_lastname_full(c_lastname)

    if not ln:
        return candidate_keys

    # fn1 — первая буква имени для ключей 9-16
    fn1 = fn[0]

    # Нормализуем телефон
    phone_normalized = None
    if c_phone:
        phone_normalized = normalize_phone_for_bloom(c_phone)

    # Парсим адрес
    addr_num = None
    street = None
    state_normalized = None

    if c_address and c_state:
        addr_num, street = parse_address_for_bloom(c_address)
        if c_state and isinstance(c_state, str):
            state_clean = c_state.upper().strip()
            if len(state_clean) == 2 and state_clean.isalpha():
                state_normalized = state_clean.lower()

    # Генерируем ключи с телефоном
    if phone_normalized:
        # key1: FN:MN:LN:DOB_YEAR:PHONE
        if mn and dob_year:
            candidate_keys[f"{fn}:{mn}:{ln}:{dob_year}:{phone_normalized}"] = "FN+MN+LN+DOB+PHONE"
        # key3: FN:LN:DOB_YEAR:PHONE
        if dob_year:
            candidate_keys[f"{fn}:{ln}:{dob_year}:{phone_normalized}"] = "FN+LN+DOB+PHONE"
        # key5: FN:MN:LN:PHONE
        if mn:
            candidate_keys[f"{fn}:{mn}:{ln}:{phone_normalized}"] = "FN+MN+LN+PHONE"
        # key8: FN:LN:PHONE
        candidate_keys[f"{fn}:{ln}:{phone_normalized}"] = "FN+LN+PHONE"

        # --- Ключи 9-16 с первой буквой имени ---
        # key9: FN1:MN:LN:DOB_YEAR:PHONE
        if mn and dob_year:
            candidate_keys[f"{fn1}:{mn}:{ln}:{dob_year}:{phone_normalized}"] = "FN1+MN+LN+DOB+PHONE"
        # key11: FN1:LN:DOB_YEAR:PHONE
        if dob_year:
            candidate_keys[f"{fn1}:{ln}:{dob_year}:{phone_normalized}"] = "FN1+LN+DOB+PHONE"
        # key13: FN1:MN:LN:PHONE
        if mn:
            candidate_keys[f"{fn1}:{mn}:{ln}:{phone_normalized}"] = "FN1+MN+LN+PHONE"
        # key16: FN1:LN:PHONE
        candidate_keys[f"{fn1}:{ln}:{phone_normalized}"] = "FN1+LN+PHONE"

    # Генерируем ключи с адресом
    if addr_num and street and state_normalized:
        # key2: FN:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
        if mn and dob_year:
            candidate_keys[f"{fn}:{mn}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN+MN+LN+DOB+ADDR"
        # key4: FN:LN:DOB_YEAR:ADDR#:STREET:STATE
        if dob_year:
            candidate_keys[f"{fn}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN+LN+DOB+ADDR"
        # key6: FN:MN:LN:ADDR#:STREET:STATE
        if mn:
            candidate_keys[f"{fn}:{mn}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN+MN+LN+ADDR"
        # key7: FN:LN:ADDR#:STREET:STATE
        candidate_keys[f"{fn}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN+LN+ADDR"

        # --- Ключи 9-16 с первой буквой имени ---
        # key10: FN1:MN:LN:DOB_YEAR:ADDR#:STREET:STATE
        if mn and dob_year:
            candidate_keys[f"{fn1}:{mn}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN1+MN+LN+DOB+ADDR"
        # key12: FN1:LN:DOB_YEAR:ADDR#:STREET:STATE
        if dob_year:
            candidate_keys[f"{fn1}:{ln}:{dob_year}:{addr_num}:{street}:{state_normalized}"] = "FN1+LN+DOB+ADDR"
        # key14: FN1:MN:LN:ADDR#:STREET:STATE
        if mn:
            candidate_keys[f"{fn1}:{mn}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN1+MN+LN+ADDR"
        # key15: FN1:LN:ADDR#:STREET:STATE
        candidate_keys[f"{fn1}:{ln}:{addr_num}:{street}:{state_normalized}"] = "FN1+LN+ADDR"

    return candidate_keys


def extract_all_searchbug_mn(searchbug_data: Dict) -> List[Optional[str]]:
    """
    Извлекает ВСЕ уникальные MN (middle initials) из SearchBug данных.

    ВАЖНО: SearchBug может вернуть несколько имён с разными middlename.
    Эта функция возвращает список всех уникальных mn.

    Args:
        searchbug_data: Данные от SearchBug API

    Returns:
        List[Optional[str]] - список уникальных mn (включая None если есть имена без mn)
    """
    mn_set = set()

    # Проверяем массив names
    names_list = searchbug_data.get('names', []) or []
    for name_item in names_list:
        if isinstance(name_item, dict):
            middlename = name_item.get('middle_name', '') or name_item.get('middleName', '')
            mn = _parse_middlename(middlename)
            mn_set.add(mn)  # может быть None

    # Fallback на одиночное поле middlename
    if not names_list:
        middlename = searchbug_data.get('middlename')
        mn = _parse_middlename(middlename)
        mn_set.add(mn)

    return list(mn_set)


def extract_searchbug_mn_and_dob(searchbug_data: Dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Извлекает MN (middle initial) и DOB_YEAR из SearchBug данных.

    ПРИМЕЧАНИЕ: Возвращает ПЕРВЫЙ найденный mn. Для всех mn используйте
    extract_all_searchbug_mn().

    Args:
        searchbug_data: Данные от SearchBug API

    Returns:
        Tuple (mn, dob_year) где:
        - mn: первая буква middlename (lowercase) или None
        - dob_year: 4-значный год или None
    """
    # Получаем все mn и берём первый не-None (если есть)
    all_mn = extract_all_searchbug_mn(searchbug_data)
    mn = None
    for m in all_mn:
        if m is not None:
            mn = m
            break

    dob = searchbug_data.get('dob')
    dob_year = extract_dob_year(dob) if dob else None

    return mn, dob_year


# =============================================================================
# Тестирование
# =============================================================================

if __name__ == '__main__':
    # Тестирование
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("SEARCH KEY GENERATOR - TESTS")
    print("=" * 60)

    # Тесты парсинга имён
    print("\n[1] FULLNAME PARSING")
    test_names = [
        (("John", None, "Wick"), ("john", None, "wick")),
        (("John", "Mike", "Wick"), ("john", "m", "wick")),
        (("John", "M", "Wick"), ("john", "m", "wick")),
        (("John", "M.", "Wick"), ("john", "m", "wick")),
        (("Mr. John", None, "Wick"), ("john", None, "wick")),
        (("Mr. John", "M.", "del Toro"), ("john", "m", "toro")),
        (("John", "M", "O'Brien"), ("john", "m", "brien")),
        (("John", None, "McDonald"), ("john", None, "donald")),
        (("John", None, "MacArthur"), ("john", None, "arthur")),
        (("John", None, "Van Der Berg"), ("john", None, "berg")),
        (("John", "M", "M. Smith"), ("john", "m", "smith")),
    ]
    for (fn, mn, ln), expected in test_names:
        result = parse_fullname(fn, mn, ln)
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: ({fn!r}, {mn!r}, {ln!r}) → {result} (expected: {expected})")

    # Тесты DOB
    print("\n[2] DOB YEAR EXTRACTION")
    test_dobs = [
        ("01/02/1990", "1990"),
        ("01021990", "1990"),
        ("1990/01/02", "1990"),
        ("19900102", "1990"),
        ("1990-01-02", "1990"),
        ("02-01-1990", "1990"),
        ("1985", "1985"),
        ("", None),
        (None, None),
    ]
    for dob, expected in test_dobs:
        result = extract_dob_year(dob)
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: {dob!r} → {result!r} (expected: {expected!r})")

    # Тесты генерации ключей
    print("\n[3] SEARCH KEY GENERATION")
    keys = generate_search_keys(
        firstname="John",
        middlename="Mike",
        lastname="Wick",
        dob="01/02/1990",
        phone="5551234567",
        address="123 Main St",
        state="FL"
    )

    expected_keys = {
        'search_key_1': 'john:m:wick:1990:5551234567',
        'search_key_2': 'john:m:wick:1990:123:main:fl',
        'search_key_3': 'john:wick:1990:5551234567',
        'search_key_4': 'john:wick:1990:123:main:fl',
        'search_key_5': 'john:m:wick:5551234567',
        'search_key_6': 'john:m:wick:123:main:fl',
        'search_key_7': 'john:wick:123:main:fl',
        'search_key_8': 'john:wick:5551234567',
    }

    for key_name, expected in expected_keys.items():
        result = keys[key_name]
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: {key_name} = {result!r} (expected: {expected!r})")

    # Тест без middlename
    print("\n[4] SEARCH KEY GENERATION (no middlename)")
    keys_no_mn = generate_search_keys(
        firstname="John",
        middlename=None,
        lastname="Wick",
        dob="01/02/1990",
        phone="5551234567",
        address="123 Main St",
        state="FL"
    )

    print(f"  search_key_1 (with MN): {keys_no_mn['search_key_1']} (expected: None)")
    print(f"  search_key_3 (no MN): {keys_no_mn['search_key_3']} (expected: john:wick:1990:5551234567)")
    print(f"  search_key_7 (no MN): {keys_no_mn['search_key_7']} (expected: john:wick:123:main:fl)")
    print(f"  search_key_8 (no MN): {keys_no_mn['search_key_8']} (expected: john:wick:5551234567)")

    # Тест SearchBug формата
    print("\n[5] SEARCHBUG DATA FORMAT")
    searchbug_data = {
        "firstname": "John",
        "middlename": "Mike",
        "lastname": "Wick",
        "dob": "01/02/1990",
        "phones": ["5551234567", "5559876543"],
        "addresses": [
            {"address": "123 Main St", "state": "FL"},
            {"address": "456 Oak Ave", "state": "CA"}
        ]
    }

    sb_keys = generate_search_keys_from_searchbug(searchbug_data)
    print(f"  search_keys_1 count: {len(sb_keys['search_keys_1'])} (expected: 2 phones)")
    print(f"  search_keys_2 count: {len(sb_keys['search_keys_2'])} (expected: 2 addresses)")
    print(f"  search_keys_8 count: {len(sb_keys['search_keys_8'])} (expected: 2 phones)")

    if sb_keys['search_keys_1']:
        print(f"  search_keys_1[0]: {sb_keys['search_keys_1'][0]}")
    if sb_keys['search_keys_8']:
        print(f"  search_keys_8[0]: {sb_keys['search_keys_8'][0]}")

    # Тесты Level 2 Runtime Matching
    print("\n[6] LEVEL 2 RUNTIME MATCHING - Query Keys")

    searchbug_data_l2 = {
        "firstname": "Thomas",
        "middlename": None,
        "lastname": "Trapp",
        "dob": "07/25/1941",
        "phones": ["9167831819"],
        "addresses": [{"address": "3080 Demartini Rd", "state": "CA"}]
    }

    query_keys = generate_query_keys_from_searchbug(searchbug_data_l2)
    print(f"  Generated {len(query_keys)} query keys for Thomas Trapp")
    print(f"  Sample keys: {list(query_keys)[:5]}")

    # Тест - key8 (FN:LN:PHONE) должен быть сгенерирован
    expected_key8 = 'thomas:trapp:9167831819'
    print(f"  Key8 present: {'OK' if expected_key8 in query_keys else 'FAIL'} ({expected_key8})")

    # Тест - key7 (FN:LN:ADDR:STREET:STATE) должен быть сгенерирован
    expected_key7 = 'thomas:trapp:3080:demartini:ca'
    print(f"  Key7 present: {'OK' if expected_key7 in query_keys else 'FAIL'} ({expected_key7})")

    print("\n[7] LEVEL 2 RUNTIME MATCHING - Candidate Keys")

    candidate = {
        'firstname': 'THOMAS',
        'lastname': 'TRAPP',
        'middlename': 'L',
        'dob': '19410725',
        'phone': '9167831819',
        'address': '3080 DEMARTINI RD',
        'state': 'CA'
    }

    candidate_keys = generate_candidate_keys(candidate)
    print(f"  Generated {len(candidate_keys)} candidate keys")
    print(f"  Sample keys: {list(candidate_keys)[:5]}")

    # Проверяем пересечение
    matched = query_keys.keys() & candidate_keys.keys()
    print(f"  Matched keys: {len(matched)}")
    if matched:
        print(f"  Matched: {list(matched)[:3]}")

    print("\n[8] LEVEL 2 - Full Test Case (Thomas Trapp)")

    # Симулируем полный flow
    # 1. Query keys из SearchBug
    query_keys_full = generate_query_keys_from_searchbug({
        "firstname": "Thomas",
        "lastname": "Trapp",
        "dob": "07/25/1941",
        "phones": ["9167831819"],
        "addresses": [{"address": "3080 Demartini Rd", "state": "CA"}]
    })

    # 2. Candidate keys (только данные из ClickHouse)
    candidate_from_ch = {
        'firstname': 'THOMAS',
        'lastname': 'TRAPP',
        'middlename': None,
        'dob': '19410725',
        'phone': '9167831819',
        'address': '3080 DEMARTINI RD',
        'state': 'CA'
    }

    candidate_keys_full = generate_candidate_keys(candidate_from_ch)

    # 3. Проверяем совпадение
    matched_full = query_keys_full.keys() & candidate_keys_full.keys()
    status = "OK" if len(matched_full) > 0 else "FAIL"
    print(f"  Thomas Trapp match: {status}")
    print(f"  Query keys: {len(query_keys_full)}, Candidate keys: {len(candidate_keys_full)}")
    print(f"  Matched: {len(matched_full)} keys")
    if matched_full:
        print(f"  Example: {list(matched_full)[0]}")

    print("\n" + "=" * 60)
    print("TESTS COMPLETED")
    print("=" * 60)
