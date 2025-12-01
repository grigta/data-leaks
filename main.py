#!/usr/bin/env python3
"""
SSN Database Management CLI

Модуль предоставляет интерфейс командной строки для управления базой данных SSN.
Поддерживает операции поиска, добавления и обновления записей.
"""

import argparse
import json
import logging
import sys
from typing import Dict, Any

from database.search_engine import SearchEngine
from database.data_manager import DataManager
from database.db_schema import DEFAULT_DB_PATH


# Константы для повторяющихся значений
TABLE_CHOICES = ['ssn_1', 'ssn_2']


def setup_logging(verbose: bool = False) -> None:
    """
    Настройка глобального логирования для приложения.

    Args:
        verbose: Если True, устанавливается уровень DEBUG, иначе WARNING
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        stream=sys.stderr
    )


def command_search(args: argparse.Namespace) -> int:
    """
    Обработчик команды search для поиска записей.

    Args:
        args: Объект с аргументами командной строки

    Returns:
        Exit код: 0 при успехе, 1 при ошибке
    """
    try:
        # Ранняя валидация входных данных
        # Проверка state: должен быть длиной 2 символа
        if args.state and len(args.state) != 2:
            result = {
                'status': 'error',
                'error': f'Код штата должен быть длиной 2 символа, получено: {len(args.state)}'
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

        # Проверка limit: должен быть положительным целым числом
        if args.limit is not None and args.limit <= 0:
            result = {
                'status': 'error',
                'error': f'Лимит должен быть положительным целым числом, получено: {args.limit}'
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

        # Сбор всех доступных полей для универсального поиска
        search_params = {}
        available_fields = ['firstname', 'lastname', 'middlename', 'address', 'city', 'state', 'zip', 'phone', 'ssn', 'dob', 'email']
        for field in available_fields:
            value = getattr(args, field, None)
            if value is not None:
                search_params[field] = value

        engine = SearchEngine(args.db_path)
        results = []

        # Определение типа поиска по приоритету: специализированные методы > универсальный поиск
        if len(search_params) == 1 and 'ssn' in search_params:
            # Использовать специализированный метод search_by_ssn()
            json_result = engine.search_by_ssn(search_params['ssn'], limit=args.limit)
        elif len(search_params) == 1 and 'email' in search_params:
            # Использовать специализированный метод search_by_email()
            json_result = engine.search_by_email(search_params['email'], limit=args.limit)
        elif set(search_params.keys()) == {'firstname', 'lastname', 'zip'}:
            # Использовать специализированный метод search_by_name_zip()
            json_result = engine.search_by_name_zip(
                search_params['firstname'], search_params['lastname'], search_params['zip'], limit=args.limit
            )
        elif set(search_params.keys()) == {'firstname', 'lastname', 'state'}:
            # Использовать специализированный метод search_by_name_state()
            json_result = engine.search_by_name_state(
                search_params['firstname'], search_params['lastname'], search_params['state'], limit=args.limit
            )
        elif len(search_params) > 0:
            # Использовать универсальный метод search_by_fields()
            json_result = engine.search_by_fields(**search_params, limit=args.limit)
        else:
            result = {
                'status': 'error',
                'error': 'Недостаточно параметров для поиска. Укажите любую комбинацию полей: '
                         '--firstname, --lastname, --middlename, --address, --city, --state, --zip, --phone, --ssn, --dob, --email. '
                         'Для оптимальной производительности используйте специализированные комбинации: '
                         '--ssn | --email | --firstname --lastname --zip | --firstname --lastname --state'
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

        # Парсинг результата для валидации
        results = json.loads(json_result)

        # Проверка типа результата: должен быть список
        if not isinstance(results, list):
            # Если результат - словарь с ошибкой
            if isinstance(results, dict):
                error_msg = results.get('error', 'SearchEngine returned non-list result')
            else:
                error_msg = 'SearchEngine returned non-list result'

            result = {
                'status': 'error',
                'error': error_msg
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

        # Формирование финального ответа
        result = {
            'status': 'success',
            'count': len(results),
            'results': results
        }

        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    except FileNotFoundError:
        result = {
            'status': 'error',
            'error': f'База данных не найдена: {args.db_path}. '
                     'Убедитесь, что файл БД существует или используйте --db-path для указания правильного пути.'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    except json.JSONDecodeError as e:
        result = {
            'status': 'error',
            'error': f'Ошибка парсинга результата поиска: {str(e)}'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    except Exception as e:
        result = {
            'status': 'error',
            'error': f'Ошибка при выполнении поиска: {str(e)}'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1


def command_add(args: argparse.Namespace) -> int:
    """
    Обработчик команды add для добавления новой записи.

    Args:
        args: Объект с аргументами командной строки

    Returns:
        Exit код: 0 при успехе, 1 при ошибке
    """
    try:
        # Валидация обязательных параметров
        if not args.table or not args.ssn:
            result = {
                'status': 'error',
                'error': 'Обязательные параметры --table и --ssn должны быть указаны'
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

        # Формирование словаря с данными записи (исключаем None значения)
        record_data = {
            'ssn': args.ssn
        }

        optional_fields = [
            'firstname', 'lastname', 'address', 'city',
            'state', 'zip', 'phone', 'dob', 'email'
        ]

        for field in optional_fields:
            value = getattr(args, field, None)
            if value is not None:
                record_data[field] = value

        # Выполнение операции добавления
        manager = DataManager(args.db_path)
        operation_result = manager.upsert_record(args.table, record_data)

        # Формирование ответа
        if operation_result['success']:
            result = {
                'status': 'success',
                'operation': 'add',
                'record': {
                    'record_id': operation_result['record_id'],
                    'ssn': operation_result['ssn'],
                    'message': operation_result['message']
                }
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        else:
            result = {
                'status': 'error',
                'error': operation_result['error']
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

    except FileNotFoundError:
        result = {
            'status': 'error',
            'error': f'База данных не найдена: {args.db_path}'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    except Exception as e:
        result = {
            'status': 'error',
            'error': f'Ошибка при добавлении записи: {str(e)}'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1


def command_update(args: argparse.Namespace) -> int:
    """
    Обработчик команды update для обновления существующей записи.

    Args:
        args: Объект с аргументами командной строки

    Returns:
        Exit код: 0 при успехе, 1 при ошибке
    """
    try:
        # Валидация обязательных параметров
        if not args.table or not args.ssn:
            result = {
                'status': 'error',
                'error': 'Обязательные параметры --table и --ssn должны быть указаны'
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

        # Сбор полей для обновления
        update_data = {}
        updatable_fields = [
            'firstname', 'lastname', 'address', 'city',
            'state', 'zip', 'phone', 'dob', 'email'
        ]

        for field in updatable_fields:
            value = getattr(args, field, None)
            if value is not None:
                update_data[field] = value

        # Проверка что есть хотя бы одно поле для обновления
        if not update_data:
            result = {
                'status': 'error',
                'error': 'Не указано ни одного поля для обновления. '
                         'Укажите хотя бы один параметр из: ' + ', '.join(f'--{f}' for f in updatable_fields)
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

        # Выполнение операции обновления
        manager = DataManager(args.db_path)
        operation_result = manager.update_record(args.table, args.ssn, update_data)

        # Формирование ответа
        if operation_result['success']:
            result = {
                'status': 'success',
                'operation': 'update',
                'record': {
                    'record_id': operation_result.get('record_id'),
                    'ssn': operation_result['ssn'],
                    'message': operation_result['message'],
                    'updated_fields': operation_result.get('updated_fields', list(update_data.keys()))
                }
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        else:
            result = {
                'status': 'error',
                'error': operation_result['error']
            }
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1

    except FileNotFoundError:
        result = {
            'status': 'error',
            'error': f'База данных не найдена: {args.db_path}'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1
    except Exception as e:
        result = {
            'status': 'error',
            'error': f'Ошибка при обновлении записи: {str(e)}'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1


def validate_search_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """
    Валидация аргументов для команды search.

    Проверяет взаимоисключающие комбинации и обязательные пары параметров.
    Вызывает parser.error() при обнаружении некорректных комбинаций.

    Args:
        parser: Парсер аргументов для вызова error()
        args: Распарсенные аргументы командной строки
    """
    if args.command != 'search':
        return

    # Проверка 1: SSN/Email не могут комбинироваться с name-based параметрами
    if args.ssn or args.email:
        name_based_params = []
        if args.firstname:
            name_based_params.append('--firstname')
        if args.lastname:
            name_based_params.append('--lastname')
        if args.zip:
            name_based_params.append('--zip')
        if args.state:
            name_based_params.append('--state')
        if getattr(args, 'middlename', None):
            name_based_params.append('--middlename')
        if getattr(args, 'address', None):
            name_based_params.append('--address')
        if getattr(args, 'city', None):
            name_based_params.append('--city')
        if getattr(args, 'phone', None):
            name_based_params.append('--phone')
        if getattr(args, 'dob', None):
            name_based_params.append('--dob')

        if name_based_params:
            parser.error("--ssn/--email cannot be combined with name-based parameters")

    # Проверка 2: firstname и lastname должны быть указаны вместе
    if args.firstname or args.lastname:
        if not (args.firstname and args.lastname):
            parser.error("--firstname and --lastname must be provided together")

    # Проверка 3: Для name-based поиска требуется --zip или --state, если не указаны дополнительные поля
    if args.firstname and args.lastname:
        has_additional_fields = any([
            getattr(args, 'middlename', None),
            getattr(args, 'address', None),
            getattr(args, 'city', None),
            getattr(args, 'phone', None),
            getattr(args, 'dob', None)
        ])
        if not has_additional_fields and not args.zip and not args.state:
            parser.error("For name-based search specify either --zip or --state, or provide additional fields for universal search")


def create_parser() -> argparse.ArgumentParser:
    """
    Создание главного парсера аргументов командной строки.

    Returns:
        Настроенный ArgumentParser с subparsers для всех команд
    """
    # Главный parser
    parser = argparse.ArgumentParser(
        description='SSN Database Management CLI - интерфейс командной строки для управления базой данных SSN',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Глобальные аргументы
    parser.add_argument(
        '--db-path',
        default=DEFAULT_DB_PATH,
        help=f'Путь к файлу базы данных (по умолчанию: {DEFAULT_DB_PATH})'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Включить детальное логирование (DEBUG уровень)'
    )

    # Создание subparsers для команд
    subparsers = parser.add_subparsers(
        dest='command',
        required=True,
        help='Доступные команды'
    )

    # Subparser для команды search
    parser_search = subparsers.add_parser(
        'search',
        help='Поиск записей в базе данных по различным критериям (поддерживается любая комбинация полей)',
        description='Поиск записей по различным критериям. '
                    'Поддерживаются стандартные комбинации (оптимизированные): '
                    '--ssn | --email | --firstname --lastname --zip | --firstname --lastname --state. '
                    'Также поддерживается универсальный поиск по любой комбинации полей: '
                    '--middlename, --address, --city, --phone, --dob в комбинации с другими параметрами поиска.'
    )

    # Группа взаимоисключающих аргументов для основных методов поиска
    main_search_group = parser_search.add_mutually_exclusive_group()
    main_search_group.add_argument('--ssn', help='Поиск по номеру Social Security Number')
    main_search_group.add_argument('--email', help='Поиск по email адресу')

    # Аргументы для поиска по имени
    parser_search.add_argument('--firstname', help='Имя (используется с --lastname и --zip или --state)')
    parser_search.add_argument('--lastname', help='Фамилия (используется с --firstname и --zip или --state)')

    # Группа взаимоисключающих аргументов для локации
    location_group = parser_search.add_mutually_exclusive_group()
    location_group.add_argument('--zip', help='ZIP код (используется с --firstname и --lastname)')
    location_group.add_argument('--state', help='Код штата (используется с --firstname и --lastname)')

    # Дополнительные поля для универсального поиска
    parser_search.add_argument('--middlename', help='Отчество (может использоваться с другими полями для универсального поиска)')
    parser_search.add_argument('--address', help='Адрес (может использоваться с другими полями для универсального поиска)')
    parser_search.add_argument('--city', help='Город (может использоваться с другими полями для универсального поиска)')
    parser_search.add_argument('--phone', help='Номер телефона (может использоваться с другими полями для универсального поиска)')
    parser_search.add_argument('--dob', help='Дата рождения в формате YYYY-MM-DD (может использоваться с другими полями для универсального поиска)')

    parser_search.add_argument(
        '--limit',
        type=int,
        help='Максимальное количество результатов'
    )
    parser_search.set_defaults(func=command_search)

    # Subparser для команды add
    parser_add = subparsers.add_parser(
        'add',
        help='Добавление новой записи в базу данных',
        description='Добавление новой записи. Если SSN уже существует, выполняется обновление (UPSERT).'
    )
    parser_add.add_argument(
        '--table',
        required=True,
        choices=TABLE_CHOICES,
        help='Имя таблицы для добавления записи'
    )
    parser_add.add_argument(
        '--ssn',
        required=True,
        help='Social Security Number (обязательно)'
    )
    parser_add.add_argument('--firstname', help='Имя')
    parser_add.add_argument('--lastname', help='Фамилия')
    parser_add.add_argument('--address', help='Адрес')
    parser_add.add_argument('--city', help='Город')
    parser_add.add_argument('--state', help='Код штата (2 символа)')
    parser_add.add_argument('--zip', help='ZIP код')
    parser_add.add_argument('--phone', help='Номер телефона')
    parser_add.add_argument('--dob', help='Дата рождения (формат YYYY-MM-DD)')
    parser_add.add_argument('--email', help='Email адрес')
    parser_add.set_defaults(func=command_add)

    # Subparser для команды update
    parser_update = subparsers.add_parser(
        'update',
        help='Обновление существующей записи',
        description='Обновление существующей записи по SSN. '
                    'Указываются только те поля, которые нужно обновить.'
    )
    parser_update.add_argument(
        '--table',
        required=True,
        choices=TABLE_CHOICES,
        help='Имя таблицы с записью для обновления'
    )
    parser_update.add_argument(
        '--ssn',
        required=True,
        help='SSN записи для обновления (обязательно)'
    )
    parser_update.add_argument('--firstname', help='Новое имя')
    parser_update.add_argument('--lastname', help='Новая фамилия')
    parser_update.add_argument('--address', help='Новый адрес')
    parser_update.add_argument('--city', help='Новый город')
    parser_update.add_argument('--state', help='Новый код штата (2 символа)')
    parser_update.add_argument('--zip', help='Новый ZIP код')
    parser_update.add_argument('--phone', help='Новый номер телефона')
    parser_update.add_argument('--dob', help='Новая дата рождения (формат YYYY-MM-DD)')
    parser_update.add_argument('--email', help='Новый email адрес')
    parser_update.set_defaults(func=command_update)

    return parser


def main() -> None:
    """
    Главная функция запуска CLI приложения.

    Обрабатывает аргументы командной строки, настраивает логирование
    и вызывает соответствующую функцию-обработчик команды.
    """
    try:
        # Создание и парсинг аргументов
        parser = create_parser()
        args = parser.parse_args()

        # Валидация аргументов команды search
        validate_search_args(parser, args)

        # Настройка логирования
        setup_logging(args.verbose)

        # Вызов функции-обработчика команды
        exit_code = args.func(args)
        sys.exit(exit_code)

    except KeyboardInterrupt:
        result = {
            'status': 'interrupted',
            'error': 'Операция прервана пользователем'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(130)
    except Exception as e:
        result = {
            'status': 'error',
            'error': f'Неожиданная ошибка: {str(e)}'
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
