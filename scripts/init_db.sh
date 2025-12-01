#!/bin/bash
set -e

echo "Initializing databases..."

# Parse command line arguments
DRY_RUN=false
if [ "$1" = "--dry-run" ]; then
  DRY_RUN=true
fi

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U ${POSTGRES_USER:-ssn_user}; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 1
done
echo "PostgreSQL is ready!"

# Wait for frontend to be ready (if nginx is running)
if docker-compose ps nginx | grep -q "Up"; then
  echo "Waiting for frontend..."
  until docker-compose ps frontend | grep -q "Up"; do
    echo "Frontend is not running yet - sleeping"
    sleep 2
  done
  echo "Frontend is running!"
fi

# Check if migration files exist
echo "Checking for migration files..."
if [ -z "$(ls -A alembic/versions/*.py 2>/dev/null | grep -v __pycache__)" ]; then
  echo "⚠️  Warning: No migration files found in alembic/versions/"
  echo "Please run: alembic revision --autogenerate -m 'Initial schema'"
  echo "Or in Docker: docker-compose exec public_api alembic revision --autogenerate -m 'Initial schema'"
  exit 1
fi
echo "✅ Migration files found"

# Check current migration version
echo "Checking current migration version..."
CURRENT_VERSION=$(docker-compose exec -T public_api alembic current 2>/dev/null | grep -oP '(?<=\()[a-f0-9]+(?=\))' || true)

if [ -z "$CURRENT_VERSION" ]; then
  echo "No migration version detected in database"
else
  echo "Current migration version: $CURRENT_VERSION"
fi

# Check for pending migrations
echo "Checking for pending migrations..."
PENDING=$(docker-compose exec -T public_api alembic check 2>&1 || true)

if echo "$PENDING" | grep -q "No new upgrade operations detected"; then
  echo "✅ Database is up to date"
else
  echo "Pending migrations detected"
fi

# Run migrations
if [ "$DRY_RUN" = true ]; then
  echo "Dry-run mode: showing SQL without executing..."
  docker-compose exec -T public_api alembic upgrade head --sql
  exit 0
fi

echo "Running Alembic migrations..."
if docker-compose exec -T public_api alembic upgrade head; then
  echo "✅ Migrations applied successfully!"
else
  echo "❌ Migration failed!"
  echo "To rollback, run: docker-compose exec public_api alembic downgrade -1"
  echo "To check status, run: docker-compose exec public_api alembic current"
  exit 1
fi

# Initialize SQLite database if not exists
if [ ! -f "./data/ssn_database.db" ]; then
  echo "Initializing SQLite database..."
  docker-compose exec -T public_api python -c "from database.db_schema import initialize_database; initialize_database()"
  echo "SQLite database initialized!"
else
  echo "SQLite database already exists, skipping initialization."
fi

echo ""
echo "============================================"
echo "All services initialized successfully!"
echo "============================================"
echo ""
echo "Access the application:"
echo "  Frontend:        http://localhost/"
echo "  Public API:      http://localhost/api/public/docs"
echo "  Enrichment API:  http://localhost/api/enrichment/docs"
echo ""
echo "Next steps:"
echo "  1. Create a user: curl -X POST http://localhost/api/public/auth/register \\"
echo "     -H \"Content-Type: application/json\" \\"
echo "     -d '{\"username\":\"admin\",\"email\":\"admin@example.com\",\"password\":\"SecurePassword123!\"}'"
echo "  2. Login at: http://localhost/login"
echo ""
