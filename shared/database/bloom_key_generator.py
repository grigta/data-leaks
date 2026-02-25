"""
Bloom Key Generator - генератор composite ключей для SearchBug matching

Создаёт два типа Bloom-ключей:
1. bloom_key_phone: {first_letter_firstname}:{first_letter_lastname}:{phone}
   Пример: John Wick, 5551234567 → j:w:5551234567

2. bloom_key_address: {first_letter_firstname}:{first_letter_lastname}:{addr#}:{street_name}:{state}
   Пример: John Wick, 123 Main St, FL → j:w:123:main:fl
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# =============================================================================
# Константы для парсинга имён
# =============================================================================

# Префиксы имени, которые нужно пропускать (Mr., Mrs., Ms., Miss, Dr., Jr., Sr.)
NAME_PREFIXES = {'MR', 'MRS', 'MS', 'MISS', 'DR', 'JR', 'SR'}

# Приставки фамилий, которые нужно пропускать
LASTNAME_PREFIXES = {'DE', 'LA', 'DEL', 'VAN', 'VON', 'DA', 'DI', 'DER'}
LASTNAME_PREFIXES_MULTI = {'DE LA', 'VAN DER'}

# Специальные приставки фамилий (O', Mc, Mac)
LASTNAME_PREFIXES_SPECIAL = {"O'", 'MC', 'MAC'}

# =============================================================================
# Константы для парсинга адресов
# =============================================================================

# Слова для пропуска между номером дома и названием улицы:
# Пропускаем ТОЛЬКО однобуквенные направления (N, S, E, W)
# Всё остальное (PO, HC, RR, NE, OLD, NEW, SAN, LOS, DEL, VIA и т.д.) — сохраняем
# Это соответствует формату bloom-ключей в БД

# Суффиксы улиц (для удаления при извлечении street_name)
STREET_SUFFIXES = {
    'ST', 'STREET', 'STR',
    'AVE', 'AVENUE', 'AV',
    'RD', 'ROAD',
    'DR', 'DRIVE',
    'LN', 'LANE',
    'CT', 'COURT',
    'PL', 'PLACE',
    'BLVD', 'BOULEVARD',
    'WAY', 'WY',
    'CIR', 'CIRCLE',
    'TER', 'TERRACE',
    'PKY', 'PKWY', 'PARKWAY',
    'HWY', 'HIGHWAY',
    'TRL', 'TRAIL',
    'LOOP',
    'PT', 'POINT',
    'SQ', 'SQUARE',
    'PASS',
    'PATH',
    'ALY', 'ALLEY',
    'WALK',
    'XING', 'CROSSING',
    'PIKE',
    'ROW',
    'RUN',
    'SPUR',
    'VIEW',
    'VISTA'
}


# =============================================================================
# Функции парсинга имён
# =============================================================================

def normalize_firstname_for_bloom(firstname: str) -> Optional[str]:
    """
    Нормализует имя для Bloom-ключа.

    Возвращает первую букву имени (lowercase), пропуская префиксы (Mr., Mrs., etc.)

    Args:
        firstname: Имя (может содержать префикс типа "Mr. John")

    Returns:
        Первая буква имени lowercase или None если невалидное

    Examples:
        >>> normalize_firstname_for_bloom("John")
        'j'
        >>> normalize_firstname_for_bloom("Mr. John")
        'j'
        >>> normalize_firstname_for_bloom("Dr. Jane")
        'j'
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
            return part[0].lower()

    return None


def normalize_lastname_for_bloom(lastname: str) -> Optional[str]:
    """
    Нормализует фамилию для Bloom-ключа.

    Возвращает первую букву фамилии as-is (lowercase).
    НЕ пропускаем приставки (Mc, Mac, O', De, Van) — bloom key это грубый фильтр,
    точная сверка происходит на Level 2. Данные в БД хранят первую букву без пропуска.

    Examples:
        >>> normalize_lastname_for_bloom("Wick")
        'w'
        >>> normalize_lastname_for_bloom("McDonald")
        'm'
        >>> normalize_lastname_for_bloom("O'Brien")
        'o'
        >>> normalize_lastname_for_bloom("Van Der Berg")
        'v'
    """
    if not lastname:
        return None

    lastname_stripped = lastname.strip()
    for ch in lastname_stripped:
        if ch.isalpha():
            return ch.lower()

    return None


# =============================================================================
# Функции парсинга телефонов
# =============================================================================

def normalize_phone_for_bloom(phone: str) -> Optional[str]:
    """
    Нормализует телефон для Bloom-ключа.

    Оставляет только 10 цифр, убирая ведущую 1 если 11 цифр.

    Args:
        phone: Телефон в любом формате

    Returns:
        10 цифр или None если невалидный

    Examples:
        >>> normalize_phone_for_bloom("(555) 123-4567")
        '5551234567'
        >>> normalize_phone_for_bloom("1-555-123-4567")
        '5551234567'
        >>> normalize_phone_for_bloom("555.123.4567")
        '5551234567'
    """
    if not phone:
        return None

    # Оставляем только цифры
    digits = ''.join(c for c in str(phone) if c.isdigit())

    # Если 11 цифр и начинается с 1 → убираем 1
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]

    # Должно быть ровно 10 цифр
    if len(digits) == 10:
        return digits

    return None


# =============================================================================
# Функции парсинга адресов
# =============================================================================

def _parse_special_address(address_upper: str) -> Optional[Tuple[str, str]]:
    """
    Проверяет специальные форматы адресов (PO BOX, RR BOX, HC BOX).

    Args:
        address_upper: Адрес в uppercase

    Returns:
        Tuple (addr_key, box_number) или None если не специальный формат

    Examples:
        "PO BOX 123" → ("pb", "123")
        "RR 2 BOX 58" → ("rr2", "58")
        "HC 1 BOX 45" → ("hc1", "45")
        "BOX 99" → ("bx", "99")
    """
    # Удаляем лишние пробелы
    address_clean = ' '.join(address_upper.split())

    # PO BOX / P.O. BOX / POST OFFICE BOX
    po_match = re.match(r'^(?:P\.?O\.?\s*BOX|POST\s+OFFICE\s+BOX)\s+(\d+)', address_clean)
    if po_match:
        return ('pb', po_match.group(1))

    # RR X BOX Y (Rural Route) - Y может иметь суффикс (58th → 58)
    rr_match = re.match(r'^RR\s*(\d+)\s+BOX\s+(\d+)', address_clean)
    if rr_match:
        return (f'rr{rr_match.group(1)}', rr_match.group(2))

    # HC X BOX Y (Highway Contract) - Y может иметь суффикс (45th → 45)
    hc_match = re.match(r'^HC\s*(\d+)\s+BOX\s+(\d+)', address_clean)
    if hc_match:
        return (f'hc{hc_match.group(1)}', hc_match.group(2))

    # Просто BOX Y
    box_match = re.match(r'^BOX\s+(\d+)', address_clean)
    if box_match:
        return ('bx', box_match.group(1))

    return None


def _extract_house_number(token: str) -> Optional[str]:
    """
    Извлекает номер дома, убирая буквенные суффиксы (123A → 123, 123th → 123).

    Args:
        token: Первый токен адреса

    Returns:
        Только цифры или None
    """
    if not token:
        return None

    # Извлекаем цифры в начале
    match = re.match(r'^(\d+)', token)
    if match:
        return match.group(1)

    return None


def parse_address_for_bloom(address: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Парсит адрес для Bloom-ключа.

    Args:
        address: Полный адрес

    Returns:
        Tuple (addr_number, street_name) в lowercase

    Examples:
        >>> parse_address_for_bloom("123 Main St")
        ('123', 'main')
        >>> parse_address_for_bloom("123 E Main St")
        ('123', 'main')
        >>> parse_address_for_bloom("123A Main St")
        ('123', 'main')
        >>> parse_address_for_bloom("123 Old Main St")
        ('123', 'main')
        >>> parse_address_for_bloom("100 1st Street")
        ('100', '1st')
        >>> parse_address_for_bloom("PO BOX 123")
        ('pb', '123')
        >>> parse_address_for_bloom("RR 2 BOX 58")
        ('rr2', '58')
    """
    if not address:
        return (None, None)

    # Нормализуем
    address_upper = address.upper().strip()

    # Шаг 1: Проверяем специальные форматы (PO BOX, RR BOX, etc.)
    special = _parse_special_address(address_upper)
    if special:
        return special

    # Разбиваем на токены
    # Заменяем . и , на пробелы
    address_clean = re.sub(r'[.,]', ' ', address_upper)
    tokens = address_clean.split()

    if not tokens:
        return (None, None)

    # Шаг 2: Извлекаем номер дома
    house_number = _extract_house_number(tokens[0])
    if not house_number:
        return (None, None)

    # Убираем первый токен (номер дома)
    remaining_tokens = tokens[1:]

    if not remaining_tokens:
        return (None, None)

    # Шаг 3: Пропускаем ТОЛЬКО однобуквенные направления (N, S, E, W)
    # Всё остальное сохраняем (PO, HC, RR, OLD, NEW, SAN, числа и т.д.)
    def should_skip_word(word: str) -> bool:
        return len(word) == 1 and word.isalpha()

    while remaining_tokens and should_skip_word(remaining_tokens[0]):
        remaining_tokens = remaining_tokens[1:]

    if not remaining_tokens:
        return (None, None)

    # Шаг 5: Первый оставшийся токен - название улицы
    street_idx = 0
    street_name = remaining_tokens[street_idx]

    # Если это суффикс улицы, берём следующий токен (если есть)
    if street_name in STREET_SUFFIXES and len(remaining_tokens) > 1:
        street_idx = 1
        street_name = remaining_tokens[street_idx]

    # Шаг 5.5: Склеиваем число + порядковый суффикс если они раздельные
    # В БД бывает "1 ST AVE" (раздельно), а SearchBug отдаёт "1ST AVE" (слитно)
    # Склеиваем: "1" + "ST" → "1ST", "2" + "ND" → "2ND", "3" + "RD" → "3RD", "10" + "TH" → "10TH"
    next_idx = street_idx + 1
    if (street_name.isdigit() and
            next_idx < len(remaining_tokens) and
            remaining_tokens[next_idx] in ('ST', 'ND', 'RD', 'TH')):
        street_name = street_name + remaining_tokens[next_idx]

    # Нормализуем название улицы
    # Если это числовая улица (1ST, 2ND, 3RD, 42ND) — сохраняем суффикс
    # Если просто число (425) — оставляем как есть
    numeric_street_match = re.match(r'^(\d+)(ST|ND|RD|TH)?$', street_name)
    if numeric_street_match:
        num = numeric_street_match.group(1)
        suffix = numeric_street_match.group(2) or ''
        street_name = f"{num}{suffix.lower()}"
    else:
        street_name = street_name.lower()

    return (house_number, street_name)


# =============================================================================
# Генерация Bloom-ключей
# =============================================================================

def generate_bloom_key_phone(
    firstname: str,
    lastname: str,
    phone: str
) -> Optional[str]:
    """
    Генерирует Bloom-ключ для поиска по телефону.

    Формат: {first_letter_firstname}:{first_letter_lastname}:{phone}

    Args:
        firstname: Имя
        lastname: Фамилия
        phone: Телефон

    Returns:
        Bloom-ключ или None если данные невалидные

    Examples:
        >>> generate_bloom_key_phone("John", "Wick", "(555) 123-4567")
        'j:w:5551234567'
        >>> generate_bloom_key_phone("Mr. John", "O'Brien", "1-555-123-4567")
        'j:b:5551234567'
    """
    fn = normalize_firstname_for_bloom(firstname)
    ln = normalize_lastname_for_bloom(lastname)
    ph = normalize_phone_for_bloom(phone)

    if not fn or not ln or not ph:
        return None

    return f"{fn}:{ln}:{ph}"


def generate_bloom_key_address(
    firstname: str,
    lastname: str,
    address: str,
    state: str
) -> Optional[str]:
    """
    Генерирует Bloom-ключ для поиска по адресу.

    Формат: {first_letter_firstname}:{first_letter_lastname}:{addr#}:{street_name}:{state}

    Args:
        firstname: Имя
        lastname: Фамилия
        address: Адрес (с номером дома и улицей)
        state: Штат (2 буквы)

    Returns:
        Bloom-ключ или None если данные невалидные

    Examples:
        >>> generate_bloom_key_address("John", "Wick", "123 Main St", "FL")
        'j:w:123:main:fl'
        >>> generate_bloom_key_address("Mr. John", "del Toro", "456 E Oak Ave", "CA")
        'j:t:456:oak:ca'
    """
    fn = normalize_firstname_for_bloom(firstname)
    ln = normalize_lastname_for_bloom(lastname)
    addr_num, street_name = parse_address_for_bloom(address)

    if not fn or not ln or not addr_num or not street_name:
        return None

    # Нормализуем state
    if not state or not isinstance(state, str):
        return None

    state_clean = state.upper().strip()
    if len(state_clean) != 2 or not state_clean.isalpha():
        return None

    return f"{fn}:{ln}:{addr_num}:{street_name}:{state_clean.lower()}"


def generate_all_bloom_keys_from_record(
    firstname: str,
    lastname: str,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    state: Optional[str] = None
) -> Dict[str, Optional[str]]:
    """
    Генерирует все Bloom-ключи для одной записи SSN.

    Args:
        firstname: Имя
        lastname: Фамилия
        phone: Телефон (опционально)
        address: Адрес (опционально)
        state: Штат (опционально)

    Returns:
        Dict с ключами bloom_key_phone и bloom_key_address

    Examples:
        >>> generate_all_bloom_keys_from_record("John", "Wick", "5551234567", "123 Main St", "FL")
        {'bloom_key_phone': 'j:w:5551234567', 'bloom_key_address': 'j:w:123:main:fl'}
    """
    result = {
        'bloom_key_phone': None,
        'bloom_key_address': None
    }

    if phone:
        result['bloom_key_phone'] = generate_bloom_key_phone(firstname, lastname, phone)

    if address and state:
        result['bloom_key_address'] = generate_bloom_key_address(firstname, lastname, address, state)

    return result


def generate_all_bloom_keys_from_searchbug(searchbug_data: Dict) -> Dict[str, List[str]]:
    """
    Генерирует все возможные Bloom-ключи из данных SearchBug API.

    SearchBug возвращает массивы телефонов, адресов И ИМЁН для одного человека.
    Для каждой комбинации (имя × телефон, имя × адрес) генерируем отдельный ключ.

    ВАЖНО: SearchBug может вернуть несколько вариаций имён (aliases, maiden names).
    Мы генерируем ключи для ВСЕХ имён, чтобы найти записи с любой вариацией.

    Args:
        searchbug_data: Данные от SearchBug API с полями:
            - names: List[Dict] с полями first_name, middle_name, last_name (приоритет)
            - firstname: str (fallback если нет names)
            - lastname: str (fallback если нет names)
            - phones: List[str] (опционально)
            - addresses: List[Dict] с полями address, state (опционально)

    Returns:
        Dict с ключами:
            - bloom_keys_phone: List[str] - все ключи для телефонов
            - bloom_keys_address: List[str] - все ключи для адресов

    Examples:
        >>> data = {
        ...     "names": [
        ...         {"first_name": "Mary", "last_name": "Johnson"},
        ...         {"first_name": "Mary", "last_name": "Smith"}
        ...     ],
        ...     "phones": ["5551234567"],
        ...     "addresses": [{"address": "123 Main St", "state": "FL"}]
        ... }
        >>> result = generate_all_bloom_keys_from_searchbug(data)
        >>> # Ключи генерируются для обоих имён: Mary Johnson И Mary Smith
    """
    result = {
        'bloom_keys_phone': [],
        'bloom_keys_address': []
    }

    # Собираем все вариации имён
    name_variations = []

    # Проверяем массив names (приоритет)
    names_list = searchbug_data.get('names', []) or []
    for name_item in names_list:
        if isinstance(name_item, dict):
            fn = name_item.get('first_name', '') or name_item.get('firstName', '')
            ln = name_item.get('last_name', '') or name_item.get('lastName', '')
            if fn and ln:
                name_variations.append((fn, ln))

    # Fallback на одиночные поля firstname/lastname
    if not name_variations:
        firstname = searchbug_data.get('firstname', '')
        lastname = searchbug_data.get('lastname', '')
        if firstname and lastname:
            name_variations.append((firstname, lastname))

    if not name_variations:
        return result

    # Получаем телефоны и адреса
    phones = searchbug_data.get('phones', []) or []
    addresses = searchbug_data.get('addresses', []) or []

    # Генерируем ключи для КАЖДОЙ комбинации имени
    for firstname, lastname in name_variations:
        # Ключи для телефонов
        for phone in phones:
            key = generate_bloom_key_phone(firstname, lastname, phone)
            if key and key not in result['bloom_keys_phone']:
                result['bloom_keys_phone'].append(key)

        # Ключи для адресов
        for addr_data in addresses:
            if isinstance(addr_data, dict):
                address = addr_data.get('address', '')
                state = addr_data.get('state', '')
                key = generate_bloom_key_address(firstname, lastname, address, state)
                if key and key not in result['bloom_keys_address']:
                    result['bloom_keys_address'].append(key)

    return result


# =============================================================================
# Batch generation для миграции существующих данных
# =============================================================================

def generate_bloom_keys_batch(
    records: List[Dict],
    id_field: str = 'id'
) -> List[Tuple[int, Optional[str], Optional[str]]]:
    """
    Генерирует Bloom-ключи для пакета записей.

    Используется для миграции существующих данных в ClickHouse.

    Args:
        records: Список записей с полями id, firstname, lastname, phone, address, state
        id_field: Имя поля с ID записи

    Returns:
        Список кортежей (id, bloom_key_phone, bloom_key_address)
    """
    results = []

    for record in records:
        record_id = record.get(id_field)
        firstname = record.get('firstname', '')
        lastname = record.get('lastname', '')
        phone = record.get('phone')
        address = record.get('address')
        state = record.get('state')

        bloom_phone = None
        bloom_address = None

        if phone:
            bloom_phone = generate_bloom_key_phone(firstname, lastname, phone)

        if address and state:
            bloom_address = generate_bloom_key_address(firstname, lastname, address, state)

        results.append((record_id, bloom_phone, bloom_address))

    return results


if __name__ == '__main__':
    # Тестирование
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("BLOOM KEY GENERATOR - TESTS")
    print("=" * 60)

    # Тесты имён
    print("\n[1] FIRSTNAME NORMALIZATION")
    test_firstnames = [
        ("John", "j"),
        ("Mr. John", "j"),
        ("Mrs. Jane", "j"),
        ("Dr. Jane", "j"),
        ("Miss Mary", "m"),
        ("John M.", "j"),
    ]
    for input_val, expected in test_firstnames:
        result = normalize_firstname_for_bloom(input_val)
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: '{input_val}' → '{result}' (expected: '{expected}')")

    # Тесты фамилий
    print("\n[2] LASTNAME NORMALIZATION")
    test_lastnames = [
        ("Wick", "w"),
        ("del Toro", "t"),
        ("Van Der Berg", "b"),
        ("O'Brien", "b"),
        ("McDonald", "d"),
        ("MacArthur", "a"),
        ("de la Cruz", "c"),
    ]
    for input_val, expected in test_lastnames:
        result = normalize_lastname_for_bloom(input_val)
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: '{input_val}' → '{result}' (expected: '{expected}')")

    # Тесты телефонов
    print("\n[3] PHONE NORMALIZATION")
    test_phones = [
        ("(555) 123-4567", "5551234567"),
        ("1-555-123-4567", "5551234567"),
        ("555.123.4567", "5551234567"),
        ("5551234567", "5551234567"),
    ]
    for input_val, expected in test_phones:
        result = normalize_phone_for_bloom(input_val)
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: '{input_val}' → '{result}' (expected: '{expected}')")

    # Тесты адресов
    print("\n[4] ADDRESS PARSING")
    test_addresses = [
        ("123 Main St", ("123", "main")),
        ("456 Oak Ave", ("456", "oak")),
        ("123 E Main St", ("123", "main")),
        ("456 NW Oak Ave", ("456", "oak")),
        ("123 Old Main St", ("123", "main")),
        ("456 West Oak Ave", ("456", "oak")),
        ("123A Main St", ("123", "main")),
        ("123th Main St", ("123", "main")),
        ("100 1st St", ("100", "1st")),
        ("200 42nd Ave", ("200", "42nd")),
        ("PO BOX 123", ("pb", "123")),
        ("RR 2 BOX 58", ("rr2", "58")),
        ("HC 1 BOX 45", ("hc1", "45")),
        ("BOX 99", ("bx", "99")),
    ]
    for input_val, expected in test_addresses:
        result = parse_address_for_bloom(input_val)
        status = "OK" if result == expected else "FAIL"
        print(f"  {status}: '{input_val}' → {result} (expected: {expected})")

    # Тесты полных ключей
    print("\n[5] FULL BLOOM KEYS")
    print(f"  Phone key: {generate_bloom_key_phone('John', 'Wick', '5551234567')}")
    print(f"  Address key: {generate_bloom_key_address('John', 'Wick', '123 Main St', 'FL')}")

    print("\n" + "=" * 60)
    print("TESTS COMPLETED")
    print("=" * 60)
