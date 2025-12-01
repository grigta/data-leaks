# SSN Management System

Full-stack application for SSN data management with search, e-commerce, and enrichment capabilities.

**Technology Stack:** FastAPI, SvelteKit, PostgreSQL, SQLite, Docker, Nginx

---

## Quick Start

Get the entire application running in 5 minutes.

### Prerequisites

- Docker and Docker Compose installed
- Git (for cloning)
- 8GB RAM minimum
- Ports available: 80 (nginx), 8000 (public API), 8001 (enrichment API)

### Setup Steps

#### Step 1: Clone and Configure

```bash
# Navigate to project directory
cd /root/soft

# Create environment file
cp .env.example .env

# Generate secure secrets
export JWT_SECRET=$(openssl rand -hex 32)
export WEBHOOK_SECRET=$(openssl rand -hex 32)
export API_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
export WHITEPAGES_API_KEY=your_real_whitepages_api_key

# Update .env file with generated secrets
sed -i "s/change_me_long_random_string_min_32_chars/$JWT_SECRET/" .env
sed -i "s/change_me_webhook_secret_min_32_chars/$WEBHOOK_SECRET/" .env
sed -i "s/key1_change_me/$API_KEY/" .env

# Set strong PostgreSQL password
sed -i "s/change_me_strong_password/$(openssl rand -base64 32)/" .env

# Set Whitepages API key (required for data enrichment feature)
sed -i "s/your_whitepages_api_key_here/$WHITEPAGES_API_KEY/" .env
```

#### Step 2: Start All Services

```bash
# Start PostgreSQL, APIs, frontend, and nginx
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
docker-compose ps
```

#### Step 3: Initialize Databases

```bash
# Run database initialization script
bash scripts/init_db.sh

# This will:
# - Wait for PostgreSQL to be ready
# - Apply Alembic migrations (create users, orders, cart_items, sessions tables)
# - Initialize SQLite database if not exists
```

#### Step 4: Create First User

```bash
# Option 1: Via API (recommended)
curl -X POST http://localhost/api/public/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "SecurePassword123!"
  }'

# Option 2: Via script (if available)
docker-compose exec public_api python scripts/create_admin.py
```

#### Step 5: Access the Application

- **Frontend:** http://localhost (nginx routes to SvelteKit)
- **Public API Docs:** http://localhost/api/public/docs (Swagger UI)
- **Enrichment API Docs:** http://localhost/api/enrichment/docs (Swagger UI)
- **Login:** Navigate to http://localhost/login and use credentials from Step 4

### Verify Everything Works

```bash
# Check all services are healthy
docker-compose ps

# Test Public API
curl http://localhost/api/public/health

# Test Enrichment API
curl http://localhost/api/enrichment/health

# Test Frontend
curl http://localhost/
```

---

## Services Overview

- **Frontend (SvelteKit):** Port 3000 (internal), accessible via nginx at http://localhost/
- **Public API (FastAPI):** Port 8000 (internal), accessible via nginx at http://localhost/api/public/
- **Enrichment API (FastAPI):** Port 8001 (internal), accessible via nginx at http://localhost/api/enrichment/
- **PostgreSQL:** Port 5432 (internal only), stores users/orders/cart
- **Nginx:** Port 80 (external), reverse proxy for all services
- **Whitepages API:** External service for data enrichment (requires API key)

---

## Overview

This project provides two FastAPI applications for managing and searching SSN (Social Security Number) data:

1. **Public API** - External-facing API for user authentication, SSN search, and e-commerce features
2. **Enrichment API** - Internal API for data enrichment and management

### Architecture

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────────┐
│   Public API    │─────▶│  PostgreSQL  │      │   SQLite DB     │
│   (Port 8000)   │      │  (Users/Cart │      │  (SSN Records)  │
│                 │      │   /Orders)   │      │                 │
└────────┬────────┘      └──────────────┘      └─────────────────┘
         │                                               ▲
         │                                               │
         │       ┌─────────────────┐                    │
         │       │ Enrichment API  │────────────────────┘
         │       │  (Port 8001)    │
         │       └─────────────────┘
         │
         │       ┌─────────────────┐
         └──────▶│ Whitepages API  │ (External)
                 │  (Enrichment)   │
                 └─────────────────┘
```

**Databases:**
- **PostgreSQL**: Stores user accounts, authentication sessions, cart items, and orders
- **SQLite**: Stores SSN records (read-only for Public API, read-write for Enrichment API)

**Common Modules:**
- `api/common/database.py` - Database connection management
- `api/common/models_postgres.py` - SQLAlchemy models for PostgreSQL
- `api/common/models_sqlite.py` - Pydantic models for SQLite data
- `api/common/auth.py` - JWT authentication utilities
- `api/common/security.py` - API key authentication

## Installation and Setup

### Prerequisites
- Docker
- Docker Compose

### Quick Start

1. **Clone the repository**
   ```bash
   cd /root/soft
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   nano .env
   ```

3. **Start services**
   ```bash
   docker-compose up -d
   ```

4. **Initialize databases**
   ```bash
   # Run database initialization script
   bash scripts/init_db.sh
   ```

5. **Verify services are running**
   ```bash
   # Through nginx (recommended)
   curl http://localhost/api/public/health
   curl http://localhost/api/enrichment/health

   # Or direct port access (development)
   curl http://localhost:8000/health
   curl http://localhost:8001/health
   ```

### Database Migrations (Alembic)

The project uses Alembic for managing PostgreSQL schema changes.

#### Initial Setup

1. **Ensure PostgreSQL is running:**
   ```bash
   docker-compose up -d postgres
   # Wait for PostgreSQL to be ready
   docker-compose exec postgres pg_isready -U ssn_user
   ```

2. **Create initial migration:**
   ```bash
   # Locally
   alembic revision --autogenerate -m "Initial schema"

   # Or in Docker
   docker-compose exec public_api alembic revision --autogenerate -m "Initial schema"
   ```

3. **Review the generated migration:**
   - Open the file in `alembic/versions/`
   - Verify all tables, indexes, and constraints are present
   - Check both `upgrade()` and `downgrade()` functions

4. **Apply the migration:**
   ```bash
   # Locally
   alembic upgrade head

   # Or in Docker
   docker-compose exec public_api alembic upgrade head

   # Or use the initialization script
   ./scripts/init_db.sh
   ```

5. **Verify the schema:**
   ```bash
   # Connect to PostgreSQL
   docker-compose exec postgres psql -U ssn_user -d ssn_users

   # Check tables
   \dt

   # Check structure
   \d users
   \d orders
   \d cart_items
   \d sessions
   ```

#### Working with Migrations

**Creating new migrations:**
```bash
# After modifying models in api/common/models_postgres.py
alembic revision --autogenerate -m "Add new field to users"
```

**Applying migrations:**
```bash
# Apply all pending migrations
alembic upgrade head

# Apply specific migration
alembic upgrade abc123

# Apply next migration only
alembic upgrade +1
```

**Rolling back migrations:**
```bash
# Rollback last migration
alembic downgrade -1

# Rollback to specific version
alembic downgrade abc123

# Rollback all migrations
alembic downgrade base
```

**Checking migration status:**
```bash
# Show current version
alembic current

# Show migration history
alembic history

# Check for differences between models and database
alembic check

# Show SQL without executing
alembic upgrade head --sql
```

#### Troubleshooting

**Problem: "No module named 'api'"**
- Solution: Run commands from the project root directory `/root/soft/`
- Ensure `prepend_sys_path = .` is set in `alembic.ini`

**Problem: "Can't locate revision"**
- Solution: `alembic stamp head` to mark the current version

**Problem: "Target database is not up to date"**
- Solution: Check `alembic current` and apply pending migrations

**Problem: Migration doesn't detect changes**
- Solution: Ensure models are imported in `alembic/env.py`
- Verify `target_metadata = Base.metadata` is set

#### Best Practices

✅ Always review generated migrations before applying
✅ Backup database before applying migrations in production
✅ Test migrations in development environment first
✅ Commit migration files to version control
✅ Use descriptive migration names

❌ Don't edit already-applied migrations
❌ Don't delete migration files
❌ Don't apply migrations directly in production without testing
❌ Don't use `--sql` flag in production (only for verification)

#### SQLite Index Updates (Migration 2025_10_30_2000)

**Important:** The database indexes for `firstname` and `lastname` fields have been updated to support **case-insensitive searches**. This migration affects the SQLite database (`ssn_database.db`), not PostgreSQL.

**What changed:**
- Indexes `idx_ssn_1_name_zip`, `idx_ssn_1_name_state`, `idx_ssn_2_name_zip`, and `idx_ssn_2_name_state` now include `COLLATE NOCASE`
- Added new indexes `idx_ssn_1_name` and `idx_ssn_2_name` for name-only searches
- This ensures that searches for "John Smith" and "john smith" return the same results

**Applying the migration:**

```bash
# For existing deployments, run the Alembic migration
docker-compose exec public_api alembic upgrade head

# Or use the initialization script which runs migrations automatically
bash scripts/init_db.sh

# Verify the migration was applied
docker-compose exec public_api alembic current
```

**Restoring search performance after index updates:**

After applying the index migration (2025_10_30_2000), search performance may be slower than expected if the data was imported with old indexes. This happens because SQLite cannot efficiently use indexes with `COLLATE NOCASE` when data was inserted with indexes without this collation.

**Symptoms:**
- Search queries that were instant (< 100ms) now take 5-30 seconds
- No errors, but noticeable performance degradation
- Occurs after running the migration on existing data

**Solutions (choose one):**

**Option 1: Rebuild indexes (Recommended - fastest fix):**
```bash
# Run the index rebuild script
python scripts/rebuild_indexes.py

# With VACUUM optimization (takes longer but optimizes DB)
python scripts/rebuild_indexes.py --vacuum

# Verify indexes are correct
sqlite3 data/ssn_database.db "SELECT sql FROM sqlite_master WHERE type='index' AND name LIKE 'idx_ssn_%';"
```

**Option 2: Re-run migration:**
```bash
# Rollback and reapply the migration
docker-compose exec public_api alembic downgrade -1
docker-compose exec public_api alembic upgrade head
```

**Option 3: Re-import data:**
```bash
# Next data import will automatically create correct indexes
# The ultra_fast_importer.py has been updated to match db_schema.py
python database/ultra_fast_importer.py import data/
```

**What was fixed:**
- `database/ultra_fast_importer.py` now creates indexes with `COLLATE NOCASE` matching `database/db_schema.py`
- Added new `idx_{table}_name` index for name-only searches
- Email indexes now also use `COLLATE NOCASE`

**Recommendation:** After upgrading to the latest code version, run `python scripts/rebuild_indexes.py` once to immediately restore search performance. This takes only a few seconds and doesn't require re-importing data.

**What happens during migration:**
1. Drops existing name-based indexes without `COLLATE NOCASE`
2. Recreates indexes with `COLLATE NOCASE` for efficient case-insensitive search
3. Adds new composite indexes for name-only searches

**Rollback (if needed):**
```bash
# Rollback to previous version
docker-compose exec public_api alembic downgrade -1
```

**Note:** This is a SQLite-specific migration and will only run if the SQLite database exists at the configured path. If the database doesn't exist yet, it will be created with the correct indexes automatically during initialization.

**See also:**
- Full documentation: `docs/MIGRATION_GUIDE.md`
- Official Alembic documentation: https://alembic.sqlalchemy.org/

## Public API Documentation

### Base URLs

The Public API can be accessed in two ways:

**Option 1: Through Nginx (Recommended for production)**
- **Base URL:** `http://localhost/api/public`
- Uses nginx reverse proxy for routing
- Centralizes all services under single domain
- Better for SSL termination and load balancing

**Option 2: Direct Port Access (Development)**
- **Base URL:** `http://localhost:8000`
- Direct connection to Public API service
- Useful for local development and debugging

All examples below use **Option 1 (nginx)** format. To use direct port access, replace `http://localhost/api/public` with `http://localhost:8000`.

**Authentication:** JWT Bearer token (obtain via `/auth/login`)

### Authentication Endpoints

#### Register a New User
```bash
POST http://localhost/api/public/auth/register
Content-Type: application/json

{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "securepassword123"
}

# Example with curl:
curl -X POST http://localhost/api/public/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "password": "securepassword123"
  }'

Response (201 Created):
{
  "id": "uuid",
  "username": "john_doe",
  "email": "john@example.com",
  "balance": 0.00,
  "created_at": "2025-10-27T12:00:00"
}
```

#### Login
```bash
POST http://localhost/api/public/auth/login
Content-Type: application/x-www-form-urlencoded

username=john_doe&password=securepassword123

# Example with curl:
curl -X POST http://localhost/api/public/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john_doe&password=securepassword123"

Response (200 OK):
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### Get Current User
```bash
GET http://localhost/api/public/auth/me
Authorization: Bearer <token>

# Example with curl:
curl -X GET http://localhost/api/public/auth/me \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "id": "uuid",
  "username": "john_doe",
  "email": "john@example.com",
  "balance": 100.00,
  "created_at": "2025-10-27T12:00:00"
}
```

### Search Endpoints

All search endpoints require JWT authentication.

#### Search by SSN
```bash
POST http://localhost/api/public/search/ssn
Authorization: Bearer <token>
Content-Type: application/json

{
  "ssn": "123-45-6789",
  "limit": 10
}

# Example with curl:
curl -X POST http://localhost/api/public/search/ssn \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ssn": "123-45-6789", "limit": 10}'

Response (200 OK):
[
  {
    "id": 1,
    "firstname": "John",
    "lastname": "Doe",
    "ssn": "123-45-6789",
    "email": "john@example.com",
    ...
  }
]
```

#### Search by Email
```bash
POST http://localhost/api/public/search/email
Authorization: Bearer <token>
Content-Type: application/json

{
  "email": "john@example.com",
  "limit": 10
}

# Example with curl:
curl -X POST http://localhost/api/public/search/email \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "john@example.com", "limit": 10}'
```

#### Search by Name
```bash
POST http://localhost/api/public/search/name
Authorization: Bearer <token>
Content-Type: application/json

{
  "firstname": "John",
  "lastname": "Doe",
  "zip": "12345",
  "limit": 10
}

# Example with curl:
curl -X POST http://localhost/api/public/search/name \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"firstname": "John", "lastname": "Doe", "zip": "12345", "limit": 10}'
```

#### Get Single Record
```bash
GET http://localhost/api/public/search/record/123-45-6789
Authorization: Bearer <token>

# Example with curl:
curl -X GET http://localhost/api/public/search/record/123-45-6789 \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "id": 1,
  "firstname": "John",
  "lastname": "Doe",
  "ssn": "123-45-6789",
  "source_table": "ssn_1",
  ...
}
```

### E-commerce Endpoints

#### Get Cart
```bash
GET http://localhost/api/public/ecommerce/cart
Authorization: Bearer <token>

# Example with curl:
curl -X GET http://localhost/api/public/ecommerce/cart \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "items": [
    {
      "id": "uuid",
      "ssn": "123-45-6789",
      "price": 10.00,
      "added_at": "2025-10-27T12:00:00",
      "ssn_details": {...}
    }
  ],
  "total_price": 10.00
}
```

#### Add to Cart
```bash
POST http://localhost/api/public/ecommerce/cart/add
Authorization: Bearer <token>
Content-Type: application/json

{
  "ssn": "123-45-6789",
  "table_name": "ssn_1",
  "price": 10.00
}

# Example with curl:
curl -X POST http://localhost/api/public/ecommerce/cart/add \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ssn": "123-45-6789", "table_name": "ssn_1", "price": 10.00}'

Response (201 Created):
{
  "message": "Item added to cart",
  "item_id": "uuid"
}
```

#### Remove from Cart
```bash
DELETE http://localhost/api/public/ecommerce/cart/{item_id}
Authorization: Bearer <token>

# Example with curl:
curl -X DELETE http://localhost/api/public/ecommerce/cart/YOUR_ITEM_ID \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "message": "Item removed from cart"
}
```

#### Create Order
```bash
POST http://localhost/api/public/ecommerce/orders/create
Authorization: Bearer <token>

# Example with curl:
curl -X POST http://localhost/api/public/ecommerce/orders/create \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (201 Created):
{
  "id": "uuid",
  "total_price": 10.00,
  "status": "completed",
  "created_at": "2025-10-27T12:00:00",
  "items_count": 1
}
```

#### Get Orders
```bash
GET http://localhost/api/public/ecommerce/orders?status=completed&limit=50&offset=0
Authorization: Bearer <token>

# Example with curl:
curl -X GET "http://localhost/api/public/ecommerce/orders?status=completed&limit=50&offset=0" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
[
  {
    "id": "uuid",
    "total_price": 10.00,
    "status": "completed",
    "created_at": "2025-10-27T12:00:00",
    "items_count": 1
  }
]
```

#### Get Order Details
```bash
GET http://localhost/api/public/ecommerce/orders/{order_id}
Authorization: Bearer <token>

# Example with curl:
curl -X GET http://localhost/api/public/ecommerce/orders/YOUR_ORDER_ID \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "id": "uuid",
  "total_price": 10.00,
  "status": "completed",
  "created_at": "2025-10-27T12:00:00",
  "items": [
    {
      "ssn": "123-45-6789",
      "price": "10.00",
      "ssn_details": {...}
    }
  ]
}
```

### Data Enrichment Endpoints

The enrichment feature allows users to update/actualize SSN records with fresh data from Whitepages API. This is a paid feature that costs $1.00 per enrichment and requires a valid Whitepages API key configured in `.env`. When users search and find records, they can click a button to get the most current information available from Whitepages.

#### Whitepages API Configuration

To use the data enrichment feature, you need to obtain an API key from the Whitepages support team.

**Configuration variables in `.env`:**
- `WHITEPAGES_API_KEY` - API key from Whitepages (required)
- `WHITEPAGES_API_URL` - Base URL (default: https://api.whitepages.com)

Without a valid API key, enrichment requests will fail. Note that Whitepages has its own costs and billing - refer to their documentation for pricing details.

#### Enrich SSN Record

Update an SSN record with the latest data from Whitepages API.

**Endpoint:** `POST http://localhost/api/public/enrichment/enrich-record`

**Authentication:** JWT Bearer token (same as other Public API endpoints)

**Rate limiting:** 10 requests per hour per user (configurable)

**Request:**
```bash
POST http://localhost/api/public/enrichment/enrich-record
Authorization: Bearer <token>
Content-Type: application/json

{
  "ssn": "123-45-6789",
  "table_name": "ssn_1"
}

# Example with curl:
curl -X POST http://localhost/api/public/enrichment/enrich-record \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ssn": "123-45-6789", "table_name": "ssn_1"}'
```

**Response (200 OK):**
```json
{
  "id": 1,
  "firstname": "John",
  "lastname": "Doe",
  "ssn": "123-45-6789",
  "email": "updated@example.com",
  "phone": "555-0123",
  "address": "123 Updated St",
  "city": "New York",
  "state": "NY",
  "zip": "10001",
  "dob": "1990-01-15",
  "source_table": "ssn_1",
  "email_count": 1,
  "phone_count": 1
}
```

#### Enrichment Process

The enrichment process follows these steps:

1. User submits SSN and table_name
2. System validates user has sufficient balance ($1.00)
3. System retrieves current record from SQLite
4. System calls Whitepages API with all available data (phone, name, address, city, state, zip)
5. Whitepages returns candidates ordered by relevance
6. System uses first candidate with basic name verification (firstname and lastname match)
7. System updates the record in SQLite with enriched data
8. System deducts $1.00 from user balance
9. System returns updated record to user

#### Whitepages Search Strategy

The system uses a comprehensive search approach:

1. **Comprehensive search:** All available parameters (phone, name, address, city, state, zip) are sent in a single API request
2. **Ordered results:** Whitepages API returns candidates ordered by relevance
3. **First candidate selection:** The first candidate is selected if it passes basic name verification
4. **Name verification:** Firstname and lastname must match (case-insensitive) for security

This approach leverages Whitepages API's internal algorithms to find the best matches based on complete context.

#### Pricing

- **Cost per enrichment:** $1.00 (deducted from user balance)
- Cost is charged regardless of whether new data is found
- Whitepages API also has its own costs (refer to their pricing documentation)
- Users must have sufficient balance before enrichment

#### Rate Limits and Error Handling

**Rate Limits:**
- User rate limit: 10 enrichments per hour (configurable)
- Whitepages API rate limits: varies by plan (429 responses)
- Note: 429 errors from Whitepages are not charged to user balance

**Common Errors:**

**400 Bad Request (Insufficient Balance):**
```json
{
  "detail": "Insufficient balance. Required: $1.00, Available: $0.50"
}
```

**404 Not Found (SSN not in database):**
```json
{
  "detail": "SSN record not found in ssn_1"
}
```

**404 Not Found (No match in Whitepages):**
```json
{
  "detail": "No matching data found in Whitepages"
}
```

**429 Too Many Requests (Whitepages rate limit):**
```json
{
  "detail": "Whitepages API rate limit exceeded. Please try again later."
}
```

**502 Bad Gateway (Whitepages API error):**
```json
{
  "detail": "Failed to enrich data: [error message]"
}
```

#### Example curl Request

Complete example showing login and enrichment:

```bash
# First, login to get JWT token
TOKEN=$(curl -X POST http://localhost/api/public/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john_doe&password=securepassword123" \
  | jq -r '.access_token')

# Enrich a record
curl -X POST http://localhost/api/public/enrichment/enrich-record \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ssn": "123-45-6789",
    "table_name": "ssn_1"
  }'
```

#### Frontend Usage

The frontend provides an intuitive interface for data enrichment:

- A magnifying glass button appears next to each search result
- Tooltip shows "Актуализировать информацию ($1.00)"
- On click, the record is enriched and updated in real-time
- User balance is automatically updated after successful enrichment
- Loading state is shown during the enrichment process

#### Data Field Mapping

Whitepages fields are mapped to our database fields as follows:

- Whitepages `street` → Our `address`
- Whitepages `zipcode` → Our `zip`
- Whitepages `date_of_birth` → Our `dob`
- Other fields map directly: `firstname`, `lastname`, `city`, `state`, `phone`, `email`

**Note:** SSN is never overwritten - we always keep our original SSN value.

#### Best Practices

- Only enrich records when you need the most current data
- Check user balance before allowing enrichment
- Handle rate limits gracefully with user-friendly messages
- Log enrichment operations for audit purposes
- Monitor Whitepages API usage to avoid unexpected costs

### Statistics Endpoints

All statistics endpoints require JWT authentication and are rate-limited to 100 requests per hour.

#### Get Online Users Count

Returns the number of currently online users (active sessions).

```bash
GET http://localhost/api/public/stats/online
Authorization: Bearer <token>

# Example with curl:
curl -X GET http://localhost/api/public/stats/online \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "count": 42,
  "timestamp": "2024-01-15T10:30:00.123456"
}
```

**Implementation:** Queries PostgreSQL sessions table for non-expired sessions (`expires_at > NOW()`).

#### Get Unique IP Statistics

Returns unique IP statistics.

```bash
GET http://localhost/api/public/stats/ips
Authorization: Bearer <token>

# Example with curl:
curl -X GET http://localhost/api/public/stats/ips \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "unique_ips": 22521,
  "last_30_days": 18432
}
```

**Note:** Currently returns mock data. Real implementation pending analytics service integration.

#### Get Loyalty Program Info

Returns user's loyalty program information.

```bash
GET http://localhost/api/public/stats/loyalty
Authorization: Bearer <token>

# Example with curl:
curl -X GET http://localhost/api/public/stats/loyalty \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
{
  "percentage": "20% OFF",
  "tier": "Gold"
}
```

**Note:** Currently returns mock data. Real implementation will calculate based on user purchase history.

#### Get Proxy Data

Returns proxy data for dashboard table with optional filtering.

```bash
GET http://localhost/api/public/stats/data
Authorization: Bearer <token>

# Optional query parameters:
# - country: Filter by country code (e.g., "US", "UK")
# - state: Filter by state (e.g., "NY", "CA")
# - city: Filter by city name
# - zip: Filter by ZIP code
# - type: Filter by proxy type ("Residential", "Mobile", "Hosting")
# - speed: Filter by speed ("Fast", "Moderate")

# Example with curl:
curl -X GET http://localhost/api/public/stats/data \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Example with filters:
curl -X GET "http://localhost/api/public/stats/data?country=US&type=Residential&speed=Fast" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

Response (200 OK):
[
  {
    "proxy_ip": "192.168.1.100",
    "country": "US",
    "city": "New York",
    "region": "NY",
    "isp": "Verizon",
    "zip": "10001",
    "speed": "Fast",
    "type": "Residential",
    "price": 12.99
  },
  {
    "proxy_ip": "192.168.1.101",
    "country": "US",
    "city": "Los Angeles",
    "region": "CA",
    "isp": "Comcast",
    "zip": "90001",
    "speed": "Fast",
    "type": "Residential",
    "price": 11.99
  }
]
```

**Note:** Currently returns mock data. Real implementation pending proxy service integration.

## Enrichment API Documentation

### Base URLs

The Enrichment API can be accessed in two ways:

**Option 1: Through Nginx (Recommended for production)**
- **Base URL:** `http://localhost/api/enrichment`
- Uses nginx reverse proxy for routing
- Better for IP whitelisting and SSL termination

**Option 2: Direct Port Access (Development)**
- **Base URL:** `http://localhost:8001`
- Direct connection to Enrichment API service
- Useful for local development and debugging

All examples below use **Option 1 (nginx)** format. To use direct port access, replace `http://localhost/api/enrichment` with `http://localhost:8001`.

**Authentication:** API Key in `X-API-Key` header

### Enrichment Endpoints

#### Add/Update Record
```bash
POST http://localhost/api/enrichment/records/add
X-API-Key: your_api_key_here
Content-Type: application/json

{
  "table_name": "ssn_1",
  "record": {
    "ssn": "123-45-6789",
    "firstname": "John",
    "lastname": "Doe",
    "email": "john@example.com",
    ...
  }
}

# Example with curl:
curl -X POST http://localhost/api/enrichment/records/add \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "ssn_1",
    "record": {
      "ssn": "123-45-6789",
      "firstname": "John",
      "lastname": "Doe",
      "email": "john@example.com"
    }
  }'

Response (200 OK):
{
  "success": true,
  "ssn": "123-45-6789",
  "message": "Record inserted successfully"
}
```

#### Update Record
```bash
PUT http://localhost/api/enrichment/records/update
X-API-Key: your_api_key_here
Content-Type: application/json

{
  "table_name": "ssn_1",
  "ssn": "123-45-6789",
  "update_data": {
    "email": "newemail@example.com",
    "phone": "555-1234"
  }
}

# Example with curl:
curl -X PUT http://localhost/api/enrichment/records/update \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "ssn_1",
    "ssn": "123-45-6789",
    "update_data": {
      "email": "newemail@example.com",
      "phone": "555-1234"
    }
  }'

Response (200 OK):
{
  "success": true,
  "updated": true,
  "ssn": "123-45-6789"
}
```

#### Bulk Add Records
```bash
POST http://localhost/api/enrichment/records/bulk
X-API-Key: your_api_key_here
Content-Type: application/json

{
  "table_name": "ssn_1",
  "records": [
    {
      "ssn": "123-45-6789",
      "firstname": "John",
      "lastname": "Doe"
    },
    {
      "ssn": "987-65-4321",
      "firstname": "Jane",
      "lastname": "Smith"
    }
  ]
}

# Example with curl:
curl -X POST http://localhost/api/enrichment/records/bulk \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "ssn_1",
    "records": [
      {"ssn": "123-45-6789", "firstname": "John", "lastname": "Doe"},
      {"ssn": "987-65-4321", "firstname": "Jane", "lastname": "Smith"}
    ]
  }'

Response (200 OK):
{
  "total": 2,
  "successful": 2,
  "failed": 0,
  "failed_records": []
}
```

#### Delete Record
```bash
DELETE http://localhost/api/enrichment/records/123-45-6789?table_name=ssn_1
X-API-Key: your_api_key_here

# Example with curl:
curl -X DELETE "http://localhost/api/enrichment/records/123-45-6789?table_name=ssn_1" \
  -H "X-API-Key: your_api_key_here"

Response (200 OK):
{
  "success": true,
  "deleted": true,
  "ssn": "123-45-6789"
}
```

#### Webhook Endpoint
```bash
POST http://localhost/api/enrichment/webhook
X-API-Key: your_api_key_here
X-Webhook-Signature: hmac_sha256_signature (optional but recommended)
X-Webhook-Source: generic (optional, default: generic)
Content-Type: application/json

{
  "operation": "add",
  "table_name": "ssn_1",
  "data": {
    "ssn": "123-45-6789",
    "firstname": "John",
    "lastname": "Doe",
    "email": "john@example.com",
    "phone": "555-1234",
    "address": "123 Main St",
    "city": "Springfield",
    "state": "IL",
    "zip": "62701",
    "dob": "1990-01-15"
  }
}

# Example with curl:
curl -X POST http://localhost/api/enrichment/webhook \
  -H "X-API-Key: your_api_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "add",
    "table_name": "ssn_1",
    "data": {
      "ssn": "123-45-6789",
      "firstname": "John",
      "lastname": "Doe",
      "email": "john@example.com"
    }
  }'

Response (200 OK):
{
  "status": "success",
  "message": "Operation 'add' completed successfully",
  "details": {
    "success": true,
    "ssn": "123-45-6789",
    "message": "Record inserted successfully"
  }
}
```

**Supported operations:**
- `add` - Add or update a single record (UPSERT)
- `update` - Update existing record (requires SSN in data)
- `delete` - Delete record (requires SSN in data)
- `bulk_add` - Add multiple records (data should be array)

**Signature verification:**
To verify webhook authenticity, compute HMAC-SHA256 of raw request body using webhook secret:

```python
import hmac
import hashlib
import json

signature = hmac.new(
    webhook_secret.encode(),
    request_body.encode(),
    hashlib.sha256
).hexdigest()
```

**Example curl request with signature:**
```bash
# Prepare payload
PAYLOAD='{"operation":"add","table_name":"ssn_1","data":{"ssn":"123-45-6789","firstname":"John","lastname":"Doe"}}'

# Compute signature (requires WEBHOOK_SECRET)
SECRET="your_webhook_secret"
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)

# Send request
curl -X POST http://localhost/api/enrichment/webhook \
  -H "X-API-Key: your_api_key" \
  -H "X-Webhook-Signature: $SIGNATURE" \
  -H "X-Webhook-Source: generic" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"
```

**Custom payload formats:**
Set `X-Webhook-Source` header to identify your external service. For example, `service_a` will transform field names automatically:

```bash
# External service format
{
  "operation": "add",
  "table_name": "ssn_1",
  "data": {
    "social_security_number": "123456789",
    "first_name": "John",
    "last_name": "Doe",
    "email_address": "john@example.com"
  }
}
```

**Best practices:**
- Always use signature verification in production (set `WEBHOOK_SECRET` in `.env`)
- The endpoint always returns 200 OK, check `status` field in response
- Implement retry logic with exponential backoff for network errors
- Don't retry on validation errors (status: "error")

**See also:** Full webhook integration guide in `docs/WEBHOOK_INTEGRATION.md`

## Admin API Documentation

### Base URLs

The Admin API can be accessed in two ways:

**Option 1: Through Nginx (Recommended for production)**
- **Base URL:** `http://localhost/api/admin`
- Uses nginx reverse proxy for routing
- Better for SSL termination and load balancing

**Option 2: Direct Port Access (Development)**
- **Base URL:** `http://localhost:8002`
- Direct connection to Admin API service
- Useful for local development and debugging

All examples below use **Option 1 (nginx)** format. To use direct port access, replace `http://localhost/api/admin` with `http://localhost:8002`.

**Authentication:** JWT Bearer token with `is_admin=true` and 2FA enabled

### Admin Analytics Endpoints

All analytics endpoints require admin authentication (JWT token with `is_admin=true` and 2FA enabled).

#### User Statistics

Get user growth statistics (total users, new users in last 1 day, 30 days).

```bash
GET /api/admin/analytics/stats/users
Authorization: Bearer {admin_jwt_token}
```

**Response (200 OK):**
```json
{
  "total_users": 1250,
  "new_users_1_day": 15,
  "new_users_30_days": 342,
  "new_users_all_time": 1250
}
```

#### Financial Statistics

Get financial overview (total deposited, total spent, usage percentage).

```bash
GET /api/admin/analytics/stats/financial
Authorization: Bearer {admin_jwt_token}
```

**Response (200 OK):**
```json
{
  "total_deposited": "125000.00",
  "total_spent": "87500.00",
  "usage_percentage": 70.0,
  "usage_amount": "87500.00"
}
```

**Calculation details:**
- `total_deposited`: Sum of all paid transactions
- `total_spent`: Sum of all completed orders
- `usage_percentage`: (total_spent / total_deposited) * 100
- `usage_amount`: Same as total_spent (shown separately for clarity)

#### Transaction Statistics

Get transaction counts by status.

```bash
GET /api/admin/analytics/stats/transactions
Authorization: Bearer {admin_jwt_token}
```

**Response (200 OK):**
```json
{
  "total_transactions": 5420,
  "pending": 125,
  "paid": 4890,
  "expired": 320,
  "failed": 85
}
```

#### Product Statistics

Get order statistics by product type.

```bash
GET /api/admin/analytics/stats/products
Authorization: Bearer {admin_jwt_token}
```

**Response (200 OK):**
```json
{
  "total_orders": 3250,
  "instant_ssn_purchases": 2100,
  "cart_purchases": 1150,
  "enrichment_operations": 0,
  "note": "Enrichment operations are not tracked in orders - they deduct balance directly"
}
```

**Product types:**
- `instant_ssn_purchases`: Single-item orders (instant purchases)
- `cart_purchases`: Multi-item orders (cart purchases)
- `enrichment_operations`: Currently untracked - enrichment deducts balance without creating Order records

#### Coupon Usage Statistics

Get coupon usage statistics.

```bash
GET /api/admin/analytics/stats/coupons
Authorization: Bearer {admin_jwt_token}
```

**Response (200 OK):**
```json
[
  {
    "coupon_code": "WELCOME10",
    "bonus_percent": 10,
    "times_used": 245,
    "total_bonus_given": "12250.00"
  },
  {
    "coupon_code": "PROMO20",
    "bonus_percent": 20,
    "times_used": 89,
    "total_bonus_given": "8900.00"
  }
]
```

#### User Table with Aggregations

Get paginated user table with comprehensive aggregations.

```bash
GET /api/admin/analytics/users/table?limit=50&offset=0&search=john&sort_by=total_spent&sort_order=desc
Authorization: Bearer {admin_jwt_token}
```

**Query Parameters:**
- `limit` (int, default: 50, max: 100) - Items per page
- `offset` (int, default: 0) - Offset for pagination
- `search` (string, optional) - Search by username or email
- `sort_by` (string, optional) - Sort field: `username`, `balance`, `total_spent`, `created_at`
- `sort_order` (string, optional) - Sort order: `asc`, `desc` (default: `desc`)

**Response (200 OK):**
```json
{
  "users": [
    {
      "id": "3cce59d2-fc8e-4405-a21c-1d56d7f08e90",
      "username": "john_doe",
      "email": "john@example.com",
      "balance": "150.00",
      "total_spent": "850.00",
      "total_deposited": "1000.00",
      "applied_coupons": ["WELCOME10", "PROMO20"],
      "created_at": "2025-09-15T10:30:00Z"
    }
  ],
  "total_count": 1250,
  "page": 0,
  "page_size": 50
}
```

**Performance notes:**
- Uses efficient subqueries and JOINs for aggregations
- Leverages database indexes on `created_at`, `status`, `user_id` fields
- Recommended page size: 50-100 items

#### Detailed User Analytics

Get detailed analytics for a specific user.

```bash
GET /api/admin/analytics/users/{user_id}/details
Authorization: Bearer {admin_jwt_token}
```

**Response (200 OK):**
```json
{
  "user_id": "3cce59d2-fc8e-4405-a21c-1d56d7f08e90",
  "username": "john_doe",
  "email": "john@example.com",
  "balance": "150.00",
  "created_at": "2025-09-15T10:30:00Z",
  "total_orders": 45,
  "total_spent": "850.00",
  "total_deposited": "1000.00",
  "applied_coupons": [
    {
      "code": "WELCOME10",
      "applied_at": "2025-09-15T11:00:00Z"
    }
  ],
  "recent_orders": [
    {
      "order_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
      "total_price": "50.00",
      "status": "completed",
      "items_count": 2,
      "created_at": "2025-10-30T15:30:00Z"
    }
  ],
  "recent_transactions": [
    {
      "transaction_id": "f1e2d3c4-b5a6-4978-8c6d-0a1b2c3d4e5f",
      "amount": "100.00",
      "status": "paid",
      "created_at": "2025-10-25T12:00:00Z"
    }
  ]
}
```

**Included data:**
- User profile information
- Financial summary (balance, spent, deposited)
- Applied coupons with application dates
- Last 10 orders with details
- Last 10 transactions with details

### Response Caching

Statistics endpoints include `Cache-Control` headers (60 seconds by default) to reduce database load. Configure cache duration via `ANALYTICS_CACHE_DURATION` environment variable.

### Known Limitations

**Enrichment Operations Tracking:**
Enrichment operations (data actualization via Whitepages API) are not tracked in the Order or Transaction tables. They deduct balance directly. To track enrichment statistics, consider adding an `EnrichmentLog` table in future updates.

### Interactive Documentation

- **Swagger UI:** http://localhost/api/admin/docs
- **ReDoc:** http://localhost/api/admin/redoc

## Integration with Existing CLI

The existing CLI (`main.py`) continues to work alongside the APIs. Both systems share the same SQLite database.

**Example CLI Usage:**
```bash
# Search by SSN using CLI
python main.py search ssn 123-45-6789

# Add record using CLI
python main.py add ssn_1 --ssn 123-45-6789 --firstname John --lastname Doe
```


## Development

### Running with Hot-Reload
For development, you can mount the code directory and enable auto-reload:

```yaml
# Add to docker-compose.yml under public_api or enrichment_api service
volumes:
  - .:/app
command: ["uvicorn", "api.public.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

### Running Tests
```bash
# Run existing tests
docker-compose exec public_api python -m pytest tests/
```

## Production Deployment

### Security Recommendations

1. **Use strong secrets**
   - Generate secure JWT_SECRET: `openssl rand -hex 32`
   - Use strong PostgreSQL passwords
   - Rotate API keys regularly

2. **Enable HTTPS**
   - Use Let's Encrypt for SSL certificates
   - Configure nginx with SSL termination

3. **Restrict Enrichment API access**
   - Uncomment IP whitelist in `nginx.conf`
   - Use VPN or private network

4. **Enable monitoring**
   - Set up logging aggregation
   - Monitor API performance
   - Set up alerts for errors

### Running with Nginx (Production)
```bash
docker-compose --profile production up -d
```

### Backup Strategy

**PostgreSQL:**
```bash
docker-compose exec postgres pg_dump -U ssn_user ssn_users > backup.sql
```

**SQLite:**
```bash
cp data/ssn_database.db data/ssn_database.db.backup
```

## Troubleshooting

### Services fail to start

```bash
# Check logs for specific service
docker-compose logs frontend
docker-compose logs public_api
docker-compose logs postgres

# Check all service statuses
docker-compose ps

# Restart all services
docker-compose restart

# Rebuild and restart
docker-compose up -d --build
```

### Port already in use

```bash
# Check what's using port 80
sudo lsof -i :80

# Stop conflicting service or change nginx port in docker-compose.yml
# Change: "80:80" to "8080:80" and access via http://localhost:8080
```

### Frontend shows "Cannot connect to API"

```bash
# Verify Public API is running
curl http://localhost/api/public/health

# Check nginx is routing correctly
docker-compose logs nginx

# Verify CORS settings in .env
# ALLOWED_ORIGINS should include frontend origin
```

### Database migration failed

```bash
# Check PostgreSQL is ready
docker-compose exec postgres pg_isready -U ssn_user

# Check current migration version
docker-compose exec public_api alembic current

# Try manual migration
docker-compose exec public_api alembic upgrade head

# If fails, check logs
docker-compose logs public_api
```

### JWT token invalid or 401 Unauthorized

- Verify JWT_SECRET is set in .env
- Ensure JWT_SECRET is the same across all Public API instances
- Check token hasn't expired (default 24 hours)
- Try logging in again to get fresh token

### Frontend build fails in Docker

```bash
# Check build logs
docker-compose logs frontend

# Try building locally first
cd frontend
pnpm install
pnpm build

# If local build works, rebuild Docker image
docker-compose build frontend --no-cache
```

### Cannot find module errors in frontend

- Ensure all shadcn-svelte components are installed
- Check package.json has all dependencies
- Rebuild Docker image: `docker-compose build frontend --no-cache`

### Nginx shows 502 Bad Gateway

```bash
# Check if backend services are running
docker-compose ps

# Check nginx can reach services
docker-compose exec nginx ping public_api
docker-compose exec nginx ping frontend

# Check nginx error logs
docker-compose logs nginx | grep error
```

### High memory usage

- PostgreSQL and Node.js services can use significant memory
- Recommended: 8GB RAM minimum
- Adjust Docker memory limits if needed
- Monitor with: `docker stats`

### Database connection errors

```bash
# Verify PostgreSQL is ready
docker-compose exec postgres pg_isready -U ssn_user

# Check DATABASE_URL in .env
# Ensure it matches postgres service name in docker-compose.yml
```

### API key authentication fails

- Verify ENRICHMENT_API_KEYS in .env
- Ensure API key is sent in X-API-Key header
- Check enrichment_api logs for details

### Enrichment feature not working

```bash
# Verify Whitepages API key is set
docker-compose exec public_api env | grep WHITEPAGES

# Check if key is valid by testing manually
curl -X GET "https://api.whitepages.com/v1/person/?name=John+Doe&state_code=NY" \
  -H "X-Api-Key: your_api_key_here"

# Check public_api logs for Whitepages errors
docker-compose logs public_api | grep -i whitepages
```

### Enrichment returns 404 "No matching data found"

- This means Whitepages couldn't find a match for the provided data
- Try enriching a different record with more complete information
- Verify the record has at least phone OR (name + address/zip)
- Check Whitepages API logs for search details

### Enrichment returns 429 rate limit

- Whitepages API has rate limits based on your plan
- Wait and retry after the specified time
- Contact Whitepages support to increase rate limits
- Consider implementing a queue system for bulk enrichments

---

## Billing API

The system supports balance management through cryptocurrency payments using [cryptocurrencyapi.net](https://new.cryptocurrencyapi.net/).

### Supported Cryptocurrencies

- **USDT** (Tether) - TRC20, ERC20
- **BTC** (Bitcoin)
- **LTC** (Litecoin)
- **XMR** (Monero)
- And more (check cryptocurrencyapi.net for full list)

### Balance Top-up Process

1. **User creates deposit** via `POST /billing/deposit`
   - System generates unique payment address
   - Returns address and QR code for easy payment

2. **User sends cryptocurrency** to provided address
   - Any amount between $5.00 and $5,000.00

3. **Automatic balance credit**
   - cryptocurrencyapi.net monitors blockchain
   - Sends IPN webhook when transaction is confirmed (1+ confirmations)
   - System automatically credits user balance

### API Endpoints

#### Create Deposit

```bash
POST /api/public/billing/deposit
Authorization: Bearer {jwt_token}
Content-Type: application/json

{
  "amount": 50.00,
  "payment_method": "crypto"
}
```

**Response (201 Created):**
```json
{
  "id": "3cce59d2-fc8e-4405-a21c-1d56d7f08e90",
  "amount": 50.00,
  "payment_method": "crypto",
  "status": "pending",
  "payment_provider": "cryptocurrencyapi",
  "payment_address": "TXYZabc123...",
  "metadata": {
    "qr_code": "https://api.qrserver.com/v1/create-qr-code/?data=TXYZabc123..."
  },
  "created_at": "2025-10-30T15:30:00Z",
  "updated_at": "2025-10-30T15:30:00Z"
}
```

**Validation:**
- Minimum amount: $5.00
- Maximum amount: $5,000.00
- Only `crypto` payment method currently supported

#### Get Transactions

```bash
GET /api/public/billing/transactions?status=pending&limit=50
Authorization: Bearer {jwt_token}
```

**Query Parameters:**
- `status` (optional) - Filter by status: `pending`, `paid`, `expired`, `failed`
- `limit` (optional, default: 50) - Maximum number of transactions
- `offset` (optional, default: 0) - Pagination offset

**Response (200 OK):**
```json
{
  "transactions": [
    {
      "id": "3cce59d2-fc8e-4405-a21c-1d56d7f08e90",
      "amount": 50.00,
      "payment_method": "crypto",
      "status": "paid",
      "payment_provider": "cryptocurrencyapi",
      "external_transaction_id": "abc123def456...",
      "payment_address": "TXYZabc123...",
      "metadata": {
        "qr_code": "https://...",
        "txid": "abc123...",
        "confirmation": 3
      },
      "created_at": "2025-10-30T15:30:00Z",
      "updated_at": "2025-10-30T15:35:00Z"
    }
  ],
  "total_count": 1
}
```

#### Get Transaction Details

```bash
GET /api/public/billing/transactions/{transaction_id}
Authorization: Bearer {jwt_token}
```

**Response (200 OK):**
```json
{
  "id": "3cce59d2-fc8e-4405-a21c-1d56d7f08e90",
  "amount": 50.00,
  "payment_method": "crypto",
  "status": "paid",
  "payment_address": "TXYZabc123...",
  "external_transaction_id": "abc123...",
  "created_at": "2025-10-30T15:30:00Z",
  "updated_at": "2025-10-30T15:35:00Z"
}
```

#### IPN Webhook (Internal)

```
POST /api/public/billing/ipn/cryptocurrencyapi
```

**Public endpoint** (no authentication) used by cryptocurrencyapi.net to notify about payment confirmations. Do not call this endpoint manually.

### Transaction Statuses

| Status | Description |
|--------|-------------|
| `pending` | Payment address created, waiting for cryptocurrency |
| `paid` | Payment confirmed and balance credited |
| `expired` | Payment not received within timeout period |
| `failed` | Payment processing failed |

### Security Features

1. **SHA-1 Signature Verification** - All IPN webhooks are verified with cryptographic signatures
2. **Idempotent Processing** - Duplicate IPNs are handled safely (no double-crediting)
3. **Atomic Balance Updates** - Uses PostgreSQL row-level locking to prevent race conditions
4. **Minimum Confirmations** - Requires 1+ blockchain confirmations before crediting

### Configuration

Required environment variables (see `.env.example`):

```bash
# CryptoCurrencyAPI API key
CRYPTOCURRENCYAPI_KEY=your_api_key_here

# CryptoCurrencyAPI base URL
CRYPTOCURRENCYAPI_URL=https://new.cryptocurrencyapi.net

# IPN webhook URL (must be publicly accessible)
IPN_WEBHOOK_URL=https://yourdomain.com/api/public/billing/ipn/cryptocurrencyapi

# Default cryptocurrency for deposits
DEFAULT_CRYPTO_CURRENCY=USDT
```

### Testing

For local development, use [ngrok](https://ngrok.com/) to expose IPN endpoint:

```bash
# Start ngrok tunnel
ngrok http 8000

# Update .env with ngrok URL
IPN_WEBHOOK_URL=https://abc123.ngrok.io/api/public/billing/ipn/cryptocurrencyapi

# Restart API
docker-compose restart public_api
```

### Detailed Documentation

For complete technical documentation including:
- IPN payload format and signature verification
- Transaction processing logic
- Troubleshooting guide
- Security best practices

See: **[docs/CRYPTOCURRENCYAPI_IPN.md](docs/CRYPTOCURRENCYAPI_IPN.md)**

---

## Development Mode

### Running frontend in development mode

```bash
# Start backend services only
docker-compose up -d postgres public_api enrichment_api

# Run frontend locally with hot-reload
cd frontend
pnpm install
pnpm dev

# Access at http://localhost:5173 (Vite dev server)
```

### Running backend with hot-reload

```bash
# Modify docker-compose.yml to mount code and enable reload
# Add under public_api service:
volumes:
  - .:/app
command: ["uvicorn", "api.public.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

---

## Interactive API Documentation

FastAPI provides automatic interactive documentation (Swagger UI):

**Through Nginx (Recommended):**
- **Public API:** http://localhost/api/public/docs
- **Enrichment API:** http://localhost/api/enrichment/docs

**Direct Port Access (Development):**
- **Public API:** http://localhost:8000/docs
- **Enrichment API:** http://localhost:8001/docs

These Swagger UI interfaces allow you to test all endpoints directly from your browser with interactive forms and response previews.
