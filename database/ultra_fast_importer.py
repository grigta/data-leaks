"""
УЛЬТРА-БЫСТРЫЙ ИМПОРТЕР с комбинацией всех оптимизаций:

1. Memory-mapped файлы (mmap) - избегаем копирования данных
2. Параллельная обработка на всех CPU ядрах
3. Отдельные БД файлы для каждого воркера (избегаем lock contention)
4. Batch INSERT с максимальными батчами
5. Минимальная валидация (только SSN)
6. PRAGMA оптимизации для максимальной скорости

ОЖИДАЕМАЯ ПРОИЗВОДИТЕЛЬНОСТЬ:
- 500,000 - 2,000,000 записей/сек на современном CPU
- Файл 100GB может быть импортирован за 10-30 минут
"""

import mmap
import sqlite3
import multiprocessing as mp
from multiprocessing import Manager, Queue
import os
import time
import logging
from pathlib import Path
from database.db_schema import DEFAULT_DB_PATH

# Константы
CSV_DELIMITER = ','  # Изменено с '~' на ',' - файлы используют запятую
BATCH_SIZE = 150000
CHUNK_SIZE_BYTES = 100 * 1024 * 1024  # 100MB на чанк


class UltraFastImporter:
    """Ультра-быстрый импортер с memory-mapped IO и параллелизмом."""

    def __init__(self, db_path=None, num_workers=None, temp_dir=None):
        """
        Инициализация.

        Args:
            db_path: Путь к финальной БД
            num_workers: Количество воркеров
            temp_dir: Папка для временных файлов
        """
        self.db_path = db_path if db_path else DEFAULT_DB_PATH
        self.num_workers = num_workers if num_workers else mp.cpu_count()
        self.temp_dir = temp_dir if temp_dir else "/root/soft/temp_import"
        self.logger = logging.getLogger(self.__class__.__name__)

        # Создать папку для временных файлов
        os.makedirs(self.temp_dir, exist_ok=True)

    @staticmethod
    def normalize_ssn_ultra_fast(ssn_bytes):
        """
        Сверхбыстрая нормализация SSN работая с байтами напрямую.

        Args:
            ssn_bytes: SSN в байтах

        Returns:
            Нормализованный SSN или None
        """
        if not ssn_bytes or len(ssn_bytes) < 9:
            return None

        # Убрать пробелы и дефисы
        clean = ssn_bytes.replace(b' ', b'').replace(b'-', b'')

        if len(clean) == 9 and clean.isdigit():
            return f"{clean[0:3].decode()}-{clean[3:5].decode()}-{clean[5:9].decode()}"

        return None

    @staticmethod
    def process_chunk_mmap(args):
        """
        Обработка чанка используя memory-mapped файл.

        Args:
            args: (chunk_id, start_pos, end_pos, file_path, temp_db_path, table_name, delimiter)

        Returns:
            Статистика
        """
        chunk_id, start_pos, end_pos, file_path, temp_db_path, table_name, delimiter = args

        # Создать локальную БД
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        # PRAGMA для максимальной скорости
        cursor.execute("PRAGMA page_size = 32768")  # 32KB pages for better bulk operations
        cursor.execute("PRAGMA journal_mode = OFF")
        cursor.execute("PRAGMA synchronous = OFF")
        cursor.execute("PRAGMA cache_size = -4000000")  # 4GB
        cursor.execute("PRAGMA locking_mode = EXCLUSIVE")
        cursor.execute("PRAGMA temp_store = MEMORY")
        cursor.execute("PRAGMA mmap_size = 268435456")  # 256MB memory-mapped I/O

        # Создать таблицу (без индексов для максимальной скорости вставки)
        cursor.execute(f"""
            CREATE TABLE {table_name} (
                firstname TEXT,
                lastname TEXT,
                middlename TEXT,
                address TEXT,
                city TEXT,
                state TEXT,
                zip TEXT,
                phone TEXT,
                ssn TEXT,
                dob TEXT,
                email TEXT
            )
        """)

        cursor.execute("BEGIN TRANSACTION")

        sql = f"""INSERT OR IGNORE INTO {table_name}
                 (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

        successful = 0
        failed = 0
        batch = []

        # Открыть файл с memory-mapping
        with open(file_path, 'r+b') as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mmapped:
                # Найти начало строки (если не начало файла)
                if start_pos > 0:
                    # Откатиться назад до начала строки
                    pos = start_pos
                    while pos > 0 and mmapped[pos - 1:pos] != b'\n':
                        pos -= 1
                    start_pos = pos

                # Читать строки из чанка
                current_pos = start_pos
                while current_pos < end_pos:
                    # Найти конец строки
                    line_end = mmapped.find(b'\n', current_pos, end_pos + 10000)
                    if line_end == -1:
                        break

                    # Извлечь строку
                    line = mmapped[current_pos:line_end]
                    current_pos = line_end + 1

                    if not line or len(line) < 10:
                        continue

                    try:
                        # Разделить по delimiter
                        delimiter_byte = delimiter.encode()
                        parts = line.split(delimiter_byte)

                        if len(parts) < 12:
                            failed += 1
                            continue

                        # Быстро извлечь поля
                        ssn = parts[-1].strip()
                        ssn_normalized = UltraFastImporter.normalize_ssn_ultra_fast(ssn)

                        if not ssn_normalized:
                            failed += 1
                            continue

                        # Декодировать только нужные поля
                        record = (
                            parts[1].decode('utf-8', errors='ignore').strip() if len(parts) > 1 else '',
                            parts[2].decode('utf-8', errors='ignore').strip() if len(parts) > 2 else '',
                            parts[3].decode('utf-8', errors='ignore').strip() if len(parts) > 3 else '',
                            parts[6].decode('utf-8', errors='ignore').strip() if len(parts) > 6 else '',
                            parts[7].decode('utf-8', errors='ignore').strip() if len(parts) > 7 else '',
                            parts[9].decode('utf-8', errors='ignore').strip() if len(parts) > 9 else '',
                            parts[10].decode('utf-8', errors='ignore').strip() if len(parts) > 10 else '',
                            parts[11].decode('utf-8', errors='ignore').strip() if len(parts) > 11 else '',
                            ssn_normalized,
                            parts[5].decode('utf-8', errors='ignore').strip() if len(parts) > 5 else '',
                            ''
                        )

                        batch.append(record)

                        if len(batch) >= BATCH_SIZE:
                            cursor.executemany(sql, batch)
                            successful += len(batch)
                            batch = []

                    except Exception:
                        failed += 1
                        continue

        # Импортировать остаток
        if batch:
            try:
                cursor.executemany(sql, batch)
                successful += len(batch)
            except Exception:
                pass

        conn.commit()

        # Сделать WAL checkpoint перед закрытием
        try:
            cursor.execute("PRAGMA wal_checkpoint(FULL)")
        except:
            pass

        # Явно закрыть курсор
        cursor.close()

        # Закрыть соединение
        conn.close()

        # Небольшая пауза для освобождения файловых дескрипторов
        import time as t
        t.sleep(0.1)

        return {
            'chunk_id': chunk_id,
            'successful': successful,
            'failed': failed
        }

    def split_file_by_bytes(self, file_path):
        """
        Разделить файл на чанки по размеру в байтах.

        Args:
            file_path: Путь к файлу

        Returns:
            Список (start_pos, end_pos) для каждого чанка
        """
        file_size = os.path.getsize(file_path)
        chunk_positions = []

        # Вычислить количество чанков
        num_chunks = max(self.num_workers, (file_size // CHUNK_SIZE_BYTES) + 1)

        # Ограничить количество чанков
        num_chunks = min(num_chunks, self.num_workers * 8)

        chunk_size = file_size // num_chunks

        for i in range(num_chunks):
            start = i * chunk_size
            end = (i + 1) * chunk_size if i < num_chunks - 1 else file_size
            chunk_positions.append((start, end))

        return chunk_positions

    def merge_databases_fast(self, temp_db_paths, table_name):
        """
        Быстрое объединение БД используя ATTACH DATABASE (zero-copy).

        Args:
            temp_db_paths: Пути к временным БД
            table_name: Имя таблицы
        """
        import time as t

        self.logger.info(f"Объединение {len(temp_db_paths)} БД...")

        # Подождать немного, чтобы все процессы точно закрыли свои соединения
        t.sleep(2)

        main_conn = sqlite3.connect(self.db_path, timeout=120.0)
        cursor = main_conn.cursor()

        # PRAGMA для оптимизации
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
        cursor.execute("PRAGMA cache_size = -4000000")  # 4GB

        # Создать таблицу в главной БД
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                firstname TEXT,
                lastname TEXT,
                middlename TEXT,
                address TEXT,
                city TEXT,
                state TEXT,
                zip TEXT,
                phone TEXT,
                ssn TEXT UNIQUE NOT NULL,
                dob TEXT,
                email TEXT
            )
        """)

        # Объединить все БД используя ATTACH DATABASE
        for i, temp_db in enumerate(temp_db_paths):
            if not os.path.exists(temp_db):
                self.logger.warning(f"Временная БД не найдена: {temp_db}")
                continue

            self.logger.info(f"Копирование данных из БД {i+1}/{len(temp_db_paths)}")

            try:
                # ATTACH временной БД
                attach_name = f"temp_db_{i}"
                cursor.execute(f"ATTACH DATABASE '{temp_db}' AS {attach_name}")

                # Копировать данные напрямую через INSERT SELECT
                cursor.execute(f"""
                    INSERT OR IGNORE INTO {table_name}
                    (firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email)
                    SELECT firstname, lastname, middlename, address, city, state, zip, phone, ssn, dob, email
                    FROM {attach_name}.{table_name}
                """)

                main_conn.commit()

                # DETACH временной БД
                cursor.execute(f"DETACH DATABASE {attach_name}")

            except Exception as e:
                self.logger.error(f"Ошибка при объединении {temp_db}: {e}")
                try:
                    cursor.execute(f"DETACH DATABASE {attach_name}")
                except:
                    pass

        # Создать индексы ПОСЛЕ объединения всех данных
        self.logger.info("Создание индексов...")
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_name_zip ON {table_name}(firstname COLLATE NOCASE, lastname COLLATE NOCASE, zip)",
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_name_state ON {table_name}(firstname COLLATE NOCASE, lastname COLLATE NOCASE, state)",
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_name ON {table_name}(firstname COLLATE NOCASE, lastname COLLATE NOCASE)",
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_email ON {table_name}(email COLLATE NOCASE)",
        ]

        for idx_sql in indexes:
            cursor.execute(idx_sql)

        cursor.execute("ANALYZE")
        main_conn.commit()
        main_conn.close()

        # Подождать перед удалением
        t.sleep(1)

        # Удалить временные файлы
        self.logger.info("Удаление временных файлов...")
        for temp_db in temp_db_paths:
            retries = 3
            for attempt in range(retries):
                try:
                    if os.path.exists(temp_db):
                        os.remove(temp_db)
                    # Удалить также WAL и SHM файлы
                    for ext in ['-wal', '-shm', '-journal']:
                        wal_file = temp_db + ext
                        if os.path.exists(wal_file):
                            os.remove(wal_file)
                    break
                except Exception as e:
                    if attempt < retries - 1:
                        t.sleep(0.5)
                    else:
                        self.logger.warning(f"Не удалось удалить {temp_db}: {e}")

    def import_file_ultra_fast(self, csv_file_path, table_name):
        """
        Ультра-быстрый импорт.

        Args:
            csv_file_path: Путь к CSV
            table_name: Имя таблицы

        Returns:
            Статистика
        """
        if not Path(csv_file_path).exists():
            return {'total': 0, 'successful': 0, 'failed': 0}

        self.logger.info("="*80)
        self.logger.info(f"УЛЬТРА-БЫСТРЫЙ ИМПОРТ: {csv_file_path}")
        self.logger.info(f"Воркеры: {self.num_workers}")
        self.logger.info(f"Размер батча: {BATCH_SIZE:,}")
        self.logger.info("="*80)

        start_time = time.time()

        # Разделить файл
        self.logger.info("Разделение файла на чанки...")
        chunks = self.split_file_by_bytes(csv_file_path)
        self.logger.info(f"Создано {len(chunks)} чанков")

        # Подготовить задачи
        tasks = []
        temp_db_paths = []

        for i, (start, end) in enumerate(chunks):
            temp_db = os.path.join(self.temp_dir, f"ultra_temp_{i}_{table_name}.db")
            temp_db_paths.append(temp_db)
            tasks.append((i, start, end, csv_file_path, temp_db, table_name, CSV_DELIMITER))

        # Параллельная обработка
        self.logger.info(f"Запуск {self.num_workers} воркеров...")
        process_start = time.time()

        with mp.Pool(processes=self.num_workers) as pool:
            results = pool.map(self.process_chunk_mmap, tasks)

        process_time = time.time() - process_start

        # Статистика
        total_successful = sum(r['successful'] for r in results)
        total_failed = sum(r['failed'] for r in results)
        total_records = total_successful + total_failed

        self.logger.info(f"Обработка: {process_time:.2f} сек")
        self.logger.info(f"Скорость: {total_records/process_time:,.0f} записей/сек")

        # Объединение
        merge_start = time.time()
        self.merge_databases_fast(temp_db_paths, table_name)
        merge_time = time.time() - merge_start

        total_time = time.time() - start_time

        self.logger.info(f"Объединение: {merge_time:.2f} сек")
        self.logger.info(f"ИТОГО: {total_time:.2f} сек ({total_time/60:.2f} мин)")
        self.logger.info(f"ОБЩАЯ СКОРОСТЬ: {total_records/total_time:,.0f} записей/сек")

        return {
            'total': total_records,
            'successful': total_successful,
            'failed': total_failed,
            'process_time': process_time,
            'merge_time': merge_time,
            'total_time': total_time
        }

    def import_all_ultra_fast(self):
        """Импорт всех файлов."""
        from db_schema import initialize_database, close_connection
        conn = initialize_database(self.db_path)
        close_connection(conn)

        files = [
            ('/root/soft/ssn.txt', 'ssn_1'),
            ('/root/soft/ssn2.txt', 'ssn_2')
        ]

        all_stats = []
        for file_path, table_name in files:
            stats = self.import_file_ultra_fast(file_path, table_name)
            all_stats.append(stats)

        # Удалить временную папку в конце всех импортов
        try:
            if os.path.exists(self.temp_dir) and not os.listdir(self.temp_dir):
                os.rmdir(self.temp_dir)
                self.logger.info(f"Временная папка {self.temp_dir} удалена")
        except Exception as e:
            self.logger.warning(f"Не удалось удалить папку {self.temp_dir}: {e}")

        return {
            'total': sum(s['total'] for s in all_stats),
            'successful': sum(s['successful'] for s in all_stats),
            'failed': sum(s['failed'] for s in all_stats),
            'total_time': sum(s['total_time'] for s in all_stats),
            'files': all_stats
        }


if __name__ == '__main__':
    mp.set_start_method('spawn', force=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    print("\n" + "="*80)
    print("УЛЬТРА-БЫСТРЫЙ ИМПОРТЕР (Memory-Mapped + Параллелизм)")
    print("="*80)

    cpu_count = mp.cpu_count()
    print(f"\nCPU ядер: {cpu_count}")
    print(f"Воркеров: {cpu_count}")
    print(f"Размер батча: {BATCH_SIZE:,}")

    input("\nНажмите Enter для старта...")

    try:
        importer = UltraFastImporter()
        stats = importer.import_all_ultra_fast()

        print("\n" + "="*80)
        print("ИТОГОВАЯ СТАТИСТИКА")
        print("="*80)
        print(f"Всего записей:    {stats['total']:,}")
        print(f"Успешно:          {stats['successful']:,}")
        print(f"Ошибок:           {stats['failed']:,}")
        print(f"Время:            {stats['total_time']:.2f} сек ({stats['total_time']/60:.2f} мин)")
        print(f"Скорость:         {stats['successful']/stats['total_time']:,.0f} записей/сек")
        print(f"База данных:      {DEFAULT_DB_PATH}")
        print("="*80)

    except Exception as e:
        print(f"\nОШИБКА: {e}")
        logging.error("Ошибка", exc_info=True)
