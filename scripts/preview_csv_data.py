#!/usr/bin/env python3
"""
Скрипт для предварительного просмотра CSV данных перед импортом.
Показывает примеры обработанных данных.
"""

import csv
import sys
from pathlib import Path

# Импортируем функции из скрипта импорта
sys.path.append(str(Path(__file__).parent))
from import_csv_data import parse_name, parse_address, normalize_ssn, normalize_phone

ATT_FINAL_CSV = '/root/soft/newdata/att_final.csv'


def preview_data(csv_path: str, num_rows: int = 20):
    """
    Показать предварительный просмотр обработанных данных.

    Args:
        csv_path: Путь к CSV файлу
        num_rows: Количество строк для просмотра
    """
    print(f"\n{'='*100}")
    print(f"ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР ДАННЫХ ИЗ {csv_path}")
    print(f"{'='*100}\n")

    print(f"{'№':<5} {'First':<12} {'Mid':<10} {'Last':<12} {'Address':<25} {'City':<15} {'ST':<3} {'ZIP':<6} {'Phone':<16} {'SSN':<13} {'DOB':<12} {'Email':<25}")
    print("-" * 170)

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, 1):
            if i > num_rows:
                break

            # Извлекаем данные
            full_name = row.get('Name', '').strip()
            phone1 = row.get('Phone1', '').strip()
            ssn = row.get('SSN', '').strip()
            dob = row.get('DOB', '').strip()
            email = row.get('Email', '').strip()
            address_full = row.get('Address', '').strip()

            # Парсим
            firstname, middlename, lastname = parse_name(full_name)
            address, city, state, zip_code = parse_address(address_full)
            phone = normalize_phone(phone1)
            ssn = normalize_ssn(ssn)

            # Ограничиваем длину для отображения
            firstname = firstname[:12]
            middlename = middlename[:10]
            lastname = lastname[:12]
            address = address[:25]
            city = city[:15]
            email = email[:25]

            print(f"{i:<5} {firstname:<12} {middlename:<10} {lastname:<12} {address:<25} {city:<15} {state:<3} {zip_code:<6} {phone:<16} {ssn:<13} {dob:<12} {email:<25}")

    print("\n" + "="*100)
    print(f"Показано {min(num_rows, i)} записей")
    print("="*100 + "\n")


def analyze_data(csv_path: str, sample_size: int = 10000):
    """
    Проанализировать данные и показать статистику.

    Args:
        csv_path: Путь к CSV файлу
        sample_size: Размер выборки для анализа
    """
    print(f"\n{'='*100}")
    print(f"АНАЛИЗ ДАННЫХ (выборка {sample_size} записей)")
    print(f"{'='*100}\n")

    total = 0
    has_ssn = 0
    has_dob = 0
    has_email = 0
    has_phone = 0
    has_address = 0
    encrypted_ssn = 0
    encrypted_dob = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for i, row in enumerate(reader, 1):
            if i > sample_size:
                break

            total += 1

            ssn = row.get('SSN', '').strip()
            dob = row.get('DOB', '').strip()
            email = row.get('Email', '').strip()
            phone1 = row.get('Phone1', '').strip()
            address = row.get('Address', '').strip()

            if ssn:
                has_ssn += 1
                if ssn.startswith('*'):
                    encrypted_ssn += 1

            if dob:
                has_dob += 1
                if dob.startswith('*'):
                    encrypted_dob += 1

            if email:
                has_email += 1

            if phone1:
                has_phone += 1

            if address:
                has_address += 1

    print(f"Обработано записей: {total:,}")
    print(f"\nСтатистика заполненности полей:")
    print(f"  SSN:     {has_ssn:,} ({has_ssn/total*100:.1f}%)  [Зашифрованных: {encrypted_ssn:,}]")
    print(f"  DOB:     {has_dob:,} ({has_dob/total*100:.1f}%)  [Зашифрованных: {encrypted_dob:,}]")
    print(f"  Email:   {has_email:,} ({has_email/total*100:.1f}%)")
    print(f"  Phone:   {has_phone:,} ({has_phone/total*100:.1f}%)")
    print(f"  Address: {has_address:,} ({has_address/total*100:.1f}%)")

    print("\n" + "="*100 + "\n")


def main():
    """Главная функция."""
    import argparse

    parser = argparse.ArgumentParser(description='Предварительный просмотр CSV данных')
    parser.add_argument(
        '--csv',
        default=ATT_FINAL_CSV,
        help=f'Путь к CSV файлу (по умолчанию: {ATT_FINAL_CSV})'
    )
    parser.add_argument(
        '--rows',
        type=int,
        default=20,
        help='Количество строк для просмотра (по умолчанию: 20)'
    )
    parser.add_argument(
        '--analyze',
        action='store_true',
        help='Показать статистику данных'
    )
    parser.add_argument(
        '--sample-size',
        type=int,
        default=10000,
        help='Размер выборки для анализа (по умолчанию: 10000)'
    )

    args = parser.parse_args()

    if not Path(args.csv).exists():
        print(f"Ошибка: CSV файл не найден: {args.csv}")
        sys.exit(1)

    # Показываем предварительный просмотр
    preview_data(args.csv, args.rows)

    # Показываем статистику если запрошено
    if args.analyze:
        analyze_data(args.csv, args.sample_size)


if __name__ == '__main__':
    main()
