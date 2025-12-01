# Deployment Guide

## Overview

This guide covers deploying the SSN Management System using Docker Compose.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx (Port 80)                      │
│                      Reverse Proxy                           │
└───────┬─────────────────┬─────────────────┬─────────────────┘
        │                 │                 │
        ▼                 ▼                 ▼
  ┌──────────┐    ┌──────────────┐  ┌──────────────┐
  │ Frontend │    │  Public API  │  │ Enrichment   │
  │ SvelteKit│    │   FastAPI    │  │     API      │
  │ Port 3000│    │  Port 8000   │  │  Port 8001   │
  └──────────┘    └───────┬──────┘  └──────┬───────┘
                          │                 │
                          ▼                 ▼
                  ┌──────────────┐  ┌──────────────┐
                  │  PostgreSQL  │  │   SQLite     │
                  │  Port 5432   │  │   (File)     │
                  │ Users/Orders │  │ SSN Records  │
                  └──────────────┘  └──────────────┘
```

## Services

### 1. PostgreSQL (postgres)

- **Image:** postgres:16-alpine
- **Purpose:** Stores user accounts, sessions, cart items, orders
- **Volume:** postgres_data (persistent storage)
- **Health check:** pg_isready every 5 seconds
- **Network:** backend (internal only)

### 2. Public API (public_api)

- **Build:** Dockerfile.public (Python 3.11-slim)
- **Purpose:** User authentication, SSN search, e-commerce
- **Databases:** PostgreSQL (read-write), SQLite (read-only)
- **Authentication:** JWT tokens
- **Rate limiting:** 100 requests/hour per user
- **Network:** backend (internal only)

### 3. Enrichment API (enrichment_api)

- **Build:** Dockerfile.enrichment (Python 3.11-slim)
- **Purpose:** Data enrichment, bulk operations, webhooks
- **Database:** SQLite (read-write)
- **Authentication:** API keys
- **Security:** Can be IP-whitelisted in nginx.conf
- **Network:** backend (internal only)

### 4. Frontend (frontend)

- **Build:** frontend/Dockerfile (Node.js 20-alpine)
- **Purpose:** Web UI for users (search, cart, orders, dashboard)
- **Framework:** SvelteKit with Svelte 5
- **SSR:** Server-side rendering enabled
- **Port:** 3000 (internal only)
- **Network:** frontend (for nginx communication)

### 5. Nginx (nginx)

- **Image:** nginx:alpine
- **Purpose:** Reverse proxy, load balancing, SSL termination
- **Routes:**
  - `/` → frontend:3000
  - `/api/public/*` → public_api:8000
  - `/api/enrichment/*` → enrichment_api:8001
- **Features:** Rate limiting, gzip compression, security headers
- **Networks:** backend, frontend (bridges both networks)

## Deployment Steps

### Development Deployment

#### 1. Start Services

```bash
docker-compose up -d
```

#### 2. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f frontend
```

#### 3. Stop Services

```bash
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v
```

### Production Deployment

#### 1. Update .env for Production

- Set strong passwords and secrets
- Configure ALLOWED_ORIGINS with your domain
- Set ORIGIN to your domain (https://yourdomain.com)
- Update PUBLIC_API_URL if using different domain

**Example production .env:**

```bash
# PostgreSQL
POSTGRES_USER=ssn_user
POSTGRES_PASSWORD=STRONG_PASSWORD_HERE
POSTGRES_DB=ssn_users
DATABASE_URL=postgresql+asyncpg://ssn_user:STRONG_PASSWORD_HERE@postgres:5432/ssn_users

# SQLite
SQLITE_PATH=/app/data/ssn_database.db

# JWT
JWT_SECRET=GENERATED_SECRET_HERE
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# Enrichment API
ENRICHMENT_API_KEYS=GENERATED_KEY_1,GENERATED_KEY_2,GENERATED_KEY_3
WEBHOOK_SECRET=GENERATED_WEBHOOK_SECRET_HERE

# CORS
ALLOWED_ORIGINS=https://yourdomain.com

# Frontend
PUBLIC_API_URL=/api/public
ORIGIN=https://yourdomain.com

# Logging
LOG_LEVEL=WARNING
```

#### 2. Enable HTTPS (Recommended)

Add SSL certificates to nginx configuration:

**Option 1: Let's Encrypt (Certbot)**

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d yourdomain.com

# Auto-renewal
sudo certbot renew --dry-run
```

**Option 2: Manual SSL Certificates**

Update nginx.conf:

```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # ... rest of configuration
}
```

Mount certificates in docker-compose.yml:

```yaml
nginx:
  volumes:
    - ./nginx.conf:/etc/nginx/nginx.conf:ro
    - ./ssl:/etc/nginx/ssl:ro
```

#### 3. Enable IP Whitelist for Enrichment API

Uncomment lines 70-73 in nginx.conf:

```nginx
location /api/enrichment/ {
    # Restrict to internal network only
    allow 10.0.0.0/8;
    allow 172.16.0.0/12;
    allow 192.168.0.0/16;
    deny all;

    # ... rest of configuration
}
```

Restart nginx:

```bash
docker-compose restart nginx
```

#### 4. Configure Backups

**PostgreSQL Backups:**

```bash
# Create backup script
cat > /root/soft/scripts/backup_postgres.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/root/soft/backups/postgres
mkdir -p $BACKUP_DIR
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
docker-compose exec -T postgres pg_dump -U ssn_user ssn_users | gzip > $BACKUP_DIR/backup_$TIMESTAMP.sql.gz
# Keep only last 30 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +30 -delete
EOF

chmod +x /root/soft/scripts/backup_postgres.sh

# Add to crontab (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * /root/soft/scripts/backup_postgres.sh") | crontab -
```

**SQLite Backups:**

```bash
# Create backup script
cat > /root/soft/scripts/backup_sqlite.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/root/soft/backups/sqlite
mkdir -p $BACKUP_DIR
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp /root/soft/data/ssn_database.db $BACKUP_DIR/backup_$TIMESTAMP.db
gzip $BACKUP_DIR/backup_$TIMESTAMP.db
# Keep only last 30 days
find $BACKUP_DIR -name "backup_*.db.gz" -mtime +30 -delete
EOF

chmod +x /root/soft/scripts/backup_sqlite.sh

# Add to crontab (daily at 3 AM)
(crontab -l 2>/dev/null; echo "0 3 * * * /root/soft/scripts/backup_sqlite.sh") | crontab -
```

#### 5. Monitor Services

**Set up health check monitoring:**

```bash
# Create monitoring script
cat > /root/soft/scripts/healthcheck.sh << 'EOF'
#!/bin/bash
ENDPOINTS=(
    "http://localhost/health"
    "http://localhost/api/public/health"
    "http://localhost/api/enrichment/health"
)

for endpoint in "${ENDPOINTS[@]}"; do
    if ! curl -f -s "$endpoint" > /dev/null; then
        echo "ALERT: $endpoint is down!" | mail -s "Service Down Alert" admin@yourdomain.com
    fi
done
EOF

chmod +x /root/soft/scripts/healthcheck.sh

# Add to crontab (every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * /root/soft/scripts/healthcheck.sh") | crontab -
```

## Scaling

### Horizontal Scaling

Public API and Enrichment API can be scaled:

```bash
docker-compose up -d --scale public_api=3
```

- Nginx will load balance across instances
- PostgreSQL connection pooling handles multiple API instances

### Vertical Scaling

Adjust Docker resource limits in docker-compose.yml:

```yaml
public_api:
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '1.0'
        memory: 1G
```

Increase PostgreSQL settings:

```yaml
postgres:
  environment:
    POSTGRES_SHARED_BUFFERS: 256MB
    POSTGRES_WORK_MEM: 16MB
    POSTGRES_MAX_CONNECTIONS: 200
```

Increase Node.js heap size for frontend:

```yaml
frontend:
  environment:
    NODE_OPTIONS: --max-old-space-size=2048
```

## Maintenance

### Updating the Application

```bash
# Pull latest code
git pull

# Rebuild images
docker-compose build

# Apply database migrations
docker-compose exec public_api alembic upgrade head

# Restart services
docker-compose up -d
```

### Database Backups

**Backup PostgreSQL:**

```bash
docker-compose exec postgres pg_dump -U ssn_user ssn_users > backup_$(date +%Y%m%d).sql
```

**Backup SQLite:**

```bash
cp data/ssn_database.db data/backups/ssn_database_$(date +%Y%m%d).db
```

**Restore PostgreSQL:**

```bash
docker-compose exec -T postgres psql -U ssn_user ssn_users < backup_20241027.sql
```

**Restore SQLite:**

```bash
cp data/backups/ssn_database_20241027.db data/ssn_database.db
docker-compose restart enrichment_api public_api
```

### Viewing Logs

```bash
# All services
docker-compose logs

# Specific service with timestamps
docker-compose logs -f --timestamps frontend

# Last 100 lines
docker-compose logs --tail=100 public_api

# Save logs to file
docker-compose logs > logs_$(date +%Y%m%d).txt
```

### Health Checks

```bash
# Check all services
docker-compose ps

# Test endpoints
curl http://localhost/health
curl http://localhost/api/public/health
curl http://localhost/api/enrichment/health

# Check PostgreSQL
docker-compose exec postgres pg_isready -U ssn_user

# Check database connections
docker-compose exec public_api python -c "from api.common.database import get_postgres_db; next(get_postgres_db())"
```

## Security Checklist

Before production deployment:

- [ ] Change all default passwords in .env
- [ ] Generate secure JWT_SECRET (32+ characters): `openssl rand -hex 32`
- [ ] Generate secure ENRICHMENT_API_KEYS: `python -c 'import secrets; print(secrets.token_hex(32))'`
- [ ] Generate secure WEBHOOK_SECRET: `python -c 'import secrets; print(secrets.token_hex(32))'`
- [ ] Set ALLOWED_ORIGINS to specific domain (not *)
- [ ] Enable HTTPS with valid SSL certificate
- [ ] Enable IP whitelist for Enrichment API
- [ ] Review and restrict PostgreSQL access
- [ ] Set up automated backups
- [ ] Configure log rotation
- [ ] Enable monitoring and alerts
- [ ] Review nginx security headers
- [ ] Disable debug logging (set LOG_LEVEL=WARNING)
- [ ] Test disaster recovery procedures
- [ ] Set up firewall rules (allow only 80, 443)
- [ ] Configure fail2ban for SSH protection
- [ ] Enable Docker security scanning
- [ ] Review and minimize exposed ports

## Performance Tuning

### PostgreSQL Optimization

```bash
# Edit docker-compose.yml
postgres:
  command: postgres -c shared_buffers=256MB -c max_connections=200 -c work_mem=16MB
```

### Nginx Caching

Add to nginx.conf:

```nginx
# Cache zone
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=100m inactive=60m;

location /api/public/ {
    proxy_cache api_cache;
    proxy_cache_valid 200 5m;
    proxy_cache_key "$scheme$request_method$host$request_uri";
    add_header X-Cache-Status $upstream_cache_status;

    # ... rest of configuration
}
```

### Frontend Optimization

Already configured with:

- Gzip compression (precompress: true in svelte.config.js)
- Code splitting (automatic in SvelteKit)
- Static asset optimization

## Troubleshooting

See README_API.md for comprehensive troubleshooting guide.

## Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
