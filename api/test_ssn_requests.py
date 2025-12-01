#!/usr/bin/env python3
"""
Тестирование Instant SSN запросов внутри контейнера
"""
import sys
import os
sys.path.insert(0, '/app')

import asyncio
from sqlalchemy import select
from api.common.database import get_postgres_session
from api.common.models_postgres import User
from api.common.auth import create_access_token
import requests

API_BASE = "http://localhost:8000"

# Данные для тестирования
test_requests = [
    {"firstname": "Patrick", "lastname": "Brown", "address": "10012 Church Rd"},
    {"firstname": "Maria", "lastname": "Rodriguez", "address": "1043 Kendalia Ave"},
    {"firstname": "Maria", "lastname": "Flores", "address": "2609 Allen Ridge Dr"},
    {"firstname": "Laurie", "lastname": "Schmidtke", "address": "137 Pleasant Ridge Dr"},
    {"firstname": "Scott", "lastname": "Tyler", "address": "2216 Lakeshore Dr"},
    {"firstname": "Kathleen", "lastname": "Rietzke", "address": "338 Evergreen Dr"},
    {"firstname": "Dennis", "lastname": "Lewis", "address": "4893 Fairway Rdg"},
]

async def main():
    # Получаем пользователя и создаём токен
    async for db in get_postgres_session():
        stmt = select(User).where(User.username == "user_b84a91db")
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            print("❌ Пользователь user_b84a91db не найден")
            return

        # Обновляем баланс и принимаем правила
        user.balance = 50.00
        user.instant_ssn_rules_accepted = True
        await db.commit()

        # Создаём токен
        token = create_access_token(data={"sub": str(user.id)})
        print(f"✅ Токен создан для пользователя: {user.username}")
        print(f"   Баланс: ${user.balance}")
        print()

        # Выполняем запросы
        print("="*70)
        print("=== ТЕСТИРОВАНИЕ 7 INSTANT SSN ЗАПРОСОВ (БЕЗ ПРАВИЛА 2+ SSN) ===")
        print("="*70)
        print()

        results_summary = []

        for i, req_data in enumerate(test_requests, 1):
            name = f"{req_data['firstname']} {req_data['lastname']}"
            print(f"[{i}/7] Поиск: {name}")

            try:
                response = requests.post(
                    f"{API_BASE}/search/instant-ssn",
                    json=req_data,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    ssn_count = data.get("ssn_matches_found", 0)
                    message = data.get("message", "")
                    new_balance = data.get("new_balance", 0)
                    charged = data.get("charged_amount")

                    print(f"      ✅ SSN найдено: {ssn_count}")
                    print(f"      💰 Списано: ${charged if charged else 0.00}")
                    print(f"      💵 Баланс: ${new_balance}")

                    # Показываем найденные SSN
                    if data.get("results"):
                        for j, result in enumerate(data["results"], 1):
                            if result.get("ssn"):
                                print(f"         [{j}] SSN: {result.get('ssn', 'N/A')}")
                                print(f"             DOB: {result.get('dob', 'N/A')}")

                    results_summary.append({
                        "name": name,
                        "ssn_count": ssn_count,
                        "charged": charged or 0
                    })
                else:
                    print(f"      ❌ Ошибка: {response.status_code}")
                    print(f"         {response.text[:150]}")
                    results_summary.append({
                        "name": name,
                        "ssn_count": 0,
                        "charged": 0
                    })

            except Exception as e:
                print(f"      ❌ Исключение: {e}")
                results_summary.append({
                    "name": name,
                    "ssn_count": 0,
                    "charged": 0
                })

            print()

        # Итоговая статистика
        print("="*70)
        print("=== ИТОГОВАЯ СТАТИСТИКА ===")
        print("="*70)
        print()

        total_ssn_found = sum(r["ssn_count"] for r in results_summary)
        total_charged = sum(r["charged"] for r in results_summary)

        print(f"Всего запросов:          {len(results_summary)}")
        print(f"Всего SSN найдено:       {total_ssn_found}")
        print(f"Всего списано:           ${total_charged:.2f}")
        print()

        print("Детали по каждому запросу:")
        print("-" * 70)
        for r in results_summary:
            print(f"  {r['name']:<30} SSN: {r['ssn_count']:<2}  Списано: ${r['charged']:.2f}")

        print("="*70)
        break

if __name__ == "__main__":
    asyncio.run(main())
