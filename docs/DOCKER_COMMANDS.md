# Docker Commands Quick Reference

## Starting Services

```bash
# Start all services
docker-compose up -d

# Start specific service
docker-compose up -d frontend

# Start with logs visible
docker-compose up

# Rebuild and start
docker-compose up -d --build
```

## Stopping Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v

# Stop specific service
docker-compose stop frontend

# Pause services without stopping
docker-compose pause
docker-compose unpause
```

## Viewing Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs frontend

# Follow logs (real-time)
docker-compose logs -f frontend

# Last 100 lines
docker-compose logs --tail=100 public_api

# With timestamps
docker-compose logs -f --timestamps nginx

# Multiple services
docker-compose logs -f frontend public_api

# Save logs to file
docker-compose logs > logs_$(date +%Y%m%d).txt
```

## Service Status

```bash
# Check all services
docker-compose ps

# Check specific service
docker-compose ps frontend

# View resource usage
docker stats

# View detailed service info
docker-compose config

# List running containers
docker ps

# List all containers (including stopped)
docker ps -a
```

## Executing Commands

```bash
# Run command in service
docker-compose exec frontend sh

# Run command without TTY
docker-compose exec -T frontend ls

# Run Alembic migration
docker-compose exec public_api alembic upgrade head

# Access PostgreSQL
docker-compose exec postgres psql -U ssn_user -d ssn_users

# Create admin user
docker-compose exec public_api python scripts/create_admin.py

# Run Python shell
docker-compose exec public_api python

# Check Node.js version in frontend
docker-compose exec frontend node --version
```

## Rebuilding

```bash
# Rebuild specific service
docker-compose build frontend

# Rebuild without cache
docker-compose build --no-cache frontend

# Rebuild all services
docker-compose build

# Pull latest base images
docker-compose pull
```

## Restarting

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart frontend

# Restart with rebuild
docker-compose up -d --build frontend

# Force recreate containers
docker-compose up -d --force-recreate
```

## Scaling

```bash
# Scale specific service
docker-compose up -d --scale public_api=3

# Check scaled instances
docker-compose ps public_api

# Scale back to 1
docker-compose up -d --scale public_api=1
```

## Cleaning Up

```bash
# Remove stopped containers
docker-compose rm

# Remove stopped containers without confirmation
docker-compose rm -f

# Remove unused images
docker image prune

# Remove unused images (including tagged)
docker image prune -a

# Remove unused volumes
docker volume prune

# Remove all unused resources
docker system prune

# Remove everything (WARNING: deletes all Docker data)
docker system prune -a --volumes

# Remove specific volume
docker volume rm soft_postgres_data

# Remove all project containers
docker-compose down --rmi all
```

## Health Checks

```bash
# Check service health
docker-compose ps

# Test endpoints
curl http://localhost/health
curl http://localhost/api/public/health
curl http://localhost/api/enrichment/health

# Check PostgreSQL
docker-compose exec postgres pg_isready -U ssn_user

# Check frontend is responding
curl -I http://localhost/

# Check nginx configuration
docker-compose exec nginx nginx -t

# Reload nginx configuration
docker-compose exec nginx nginx -s reload
```

## Debugging

```bash
# Enter container shell
docker-compose exec frontend sh

# View container details
docker inspect soft-frontend-1

# View network details
docker network inspect soft_backend

# Check environment variables
docker-compose exec frontend env

# Check port mappings
docker port soft-nginx-1

# View container processes
docker-compose top frontend

# View container filesystem changes
docker diff soft-frontend-1

# Export container filesystem
docker export soft-frontend-1 > frontend.tar
```

## Database Operations

```bash
# Apply migrations
docker-compose exec public_api alembic upgrade head

# Rollback migration
docker-compose exec public_api alembic downgrade -1

# Check migration status
docker-compose exec public_api alembic current

# Show migration history
docker-compose exec public_api alembic history

# Create new migration
docker-compose exec public_api alembic revision --autogenerate -m "Add new table"

# Backup PostgreSQL
docker-compose exec postgres pg_dump -U ssn_user ssn_users > backup.sql

# Restore PostgreSQL
docker-compose exec -T postgres psql -U ssn_user ssn_users < backup.sql

# Backup SQLite
docker-compose exec public_api cp /app/data/ssn_database.db /app/data/backup.db

# Access PostgreSQL CLI
docker-compose exec postgres psql -U ssn_user -d ssn_users

# Run SQL query
docker-compose exec postgres psql -U ssn_user -d ssn_users -c "SELECT COUNT(*) FROM users;"
```

## Network Operations

```bash
# List networks
docker network ls

# Inspect network
docker network inspect soft_backend

# Create custom network
docker network create my_network

# Connect container to network
docker network connect soft_backend my_container

# Disconnect container from network
docker network disconnect soft_backend my_container
```

## Volume Operations

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect soft_postgres_data

# Create volume
docker volume create my_volume

# Remove volume
docker volume rm my_volume

# Backup volume
docker run --rm -v soft_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data

# Restore volume
docker run --rm -v soft_postgres_data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres_backup.tar.gz -C /
```

## Image Operations

```bash
# List images
docker images

# Remove image
docker rmi soft-frontend

# Tag image
docker tag soft-frontend:latest soft-frontend:v1.0

# Save image to file
docker save soft-frontend > frontend.tar

# Load image from file
docker load < frontend.tar

# Push to registry
docker push myregistry.com/soft-frontend:latest

# Pull from registry
docker pull myregistry.com/soft-frontend:latest
```

## Production Commands

```bash
# Start with production profile
docker-compose --profile production up -d

# View production logs
docker-compose logs -f nginx

# Backup before update
./scripts/backup_postgres.sh
./scripts/backup_sqlite.sh

# Update application
git pull
docker-compose build
docker-compose exec public_api alembic upgrade head
docker-compose up -d

# Zero-downtime update (with scaling)
docker-compose up -d --scale public_api=2 --no-recreate
docker-compose build public_api
docker-compose up -d --scale public_api=2
docker-compose up -d --scale public_api=1

# Monitor resource usage
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# Export logs for analysis
docker-compose logs --since 24h > logs_24h.txt
```

## Troubleshooting Commands

```bash
# Check service dependencies
docker-compose config --services

# Validate docker-compose.yml
docker-compose config

# View service events
docker events --filter container=soft-frontend-1

# Check disk usage
docker system df

# View detailed disk usage
docker system df -v

# Kill hung container
docker kill soft-frontend-1

# Force remove container
docker rm -f soft-frontend-1

# Restart Docker daemon
sudo systemctl restart docker

# Check Docker daemon status
sudo systemctl status docker

# View Docker daemon logs
sudo journalctl -u docker -f
```

## Development Commands

```bash
# Run frontend in development mode
cd frontend && pnpm dev

# Start only backend services
docker-compose up -d postgres public_api enrichment_api

# Mount code for hot-reload (modify docker-compose.yml first)
docker-compose up -d --build public_api

# Watch logs in development
docker-compose logs -f --tail=100 frontend public_api

# Run tests
docker-compose exec public_api pytest

# Run type checking
docker-compose exec frontend pnpm run check

# Format code
docker-compose exec frontend pnpm run format

# Lint code
docker-compose exec frontend pnpm run lint
```

## Useful Aliases

Add these to your `~/.bashrc` or `~/.zshrc`:

```bash
alias dc='docker-compose'
alias dcu='docker-compose up -d'
alias dcd='docker-compose down'
alias dcl='docker-compose logs -f'
alias dcp='docker-compose ps'
alias dcr='docker-compose restart'
alias dcb='docker-compose build'
alias dce='docker-compose exec'
```

Then use:

```bash
dc up -d
dcl frontend
dce public_api alembic upgrade head
```
