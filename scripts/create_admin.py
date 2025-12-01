#!/usr/bin/env python3
"""
Script to create an admin user with admin privileges and initial balance.
Admin users require 2FA setup on first login.
"""
import asyncio
import sys
from getpass import getpass
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from api.common.models_postgres import User
from api.common.auth import hash_password
import os


async def create_admin_user():
    """Create an admin user interactively."""
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL environment variable not set")
        print("Please set DATABASE_URL or run this script inside the container:")
        print("  docker-compose exec public_api python scripts/create_admin.py")
        sys.exit(1)

    # Get admin credentials from user input
    print("=== Create Admin User ===\n")
    username = input("Enter admin username: ").strip()
    email = input("Enter admin email: ").strip()
    password = getpass("Enter admin password: ")
    confirm_password = getpass("Confirm admin password: ")

    if password != confirm_password:
        print("Error: Passwords do not match")
        sys.exit(1)

    if len(password) < 8:
        print("Error: Password must be at least 8 characters long")
        sys.exit(1)

    # Get initial balance
    balance_input = input("Enter initial balance (default: 1000.00): ").strip()
    try:
        balance = float(balance_input) if balance_input else 1000.00
    except ValueError:
        print("Error: Invalid balance amount")
        sys.exit(1)

    # Create async engine and session
    engine = create_async_engine(database_url, echo=False)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        try:
            # Check if user already exists
            result = await session.execute(select(User).where(User.username == username))
            existing_user = result.scalar_one_or_none()

            if existing_user:
                print(f"Error: User '{username}' already exists")
                sys.exit(1)

            # Check if email already exists
            result = await session.execute(select(User).where(User.email == email))
            existing_email = result.scalar_one_or_none()

            if existing_email:
                print(f"Error: Email '{email}' is already registered")
                sys.exit(1)

            # Create admin user
            hashed_password = hash_password(password)
            admin_user = User(
                username=username,
                email=email,
                hashed_password=hashed_password,
                balance=balance
            )
            admin_user.is_admin = True

            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)

            print("\n" + "="*50)
            print(f"✓ Admin user created successfully!")
            print("="*50)
            print(f"User ID:  {admin_user.id}")
            print(f"Username: {admin_user.username}")
            print(f"Email:    {admin_user.email}")
            print(f"Admin:    True")
            print(f"Balance:  ${admin_user.balance:.2f}")
            print(f"Created:  {admin_user.created_at}")
            print("="*50)
            print("\nIMPORTANT: Please set up 2FA on first login to access admin features.")
            print("="*50)

        except Exception as e:
            print(f"Error creating admin user: {str(e)}")
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == '__main__':
    asyncio.run(create_admin_user())
