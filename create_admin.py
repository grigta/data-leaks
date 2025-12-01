#!/usr/bin/env python3
"""Создание админа с корректным хешем пароля."""
import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from api.common.models_postgres import User
from api.common.auth import hash_password

DATABASE_URL = "postgresql+asyncpg://crm_user:crm_password@localhost:5432/crm_database"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def create_admin():
    async with AsyncSessionLocal() as session:
        # Проверяем существует ли testadmin2
        query = select(User).where(User.username == "testadmin2")
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if user:
            # Обновляем пароль
            user.hashed_password = hash_password("admin123")
            print(f"✓ Обновлён пароль для admin: username='testadmin2'")
        else:
            # Создаём нового
            user = User(
                username="testadmin2",
                email="testadmin2@example.com",
                hashed_password=hash_password("admin123"),
                is_admin=True,
                worker_role=False,
                balance=0.00,
                invited_by=None,
                invitation_code=None,
                invitation_bonus_received=False
            )
            session.add(user)
            print(f"✓ Создан новый admin: username='testadmin2', password='admin123'")

        await session.commit()
        print("✓ Готово!")


if __name__ == "__main__":
    asyncio.run(create_admin())
