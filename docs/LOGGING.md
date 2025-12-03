# Logging System Documentation

## Overview

The logging system provides centralized, structured logging with JSON format support, correlation IDs for distributed tracing, security event monitoring, and performance metrics tracking.

### Key Features

- **Structured JSON Logging**: All logs in JSON format for easy parsing and aggregation
- **Correlation IDs**: Request tracing across services via X-Request-ID header
- **Performance Metrics**: Automatic tracking of response time, status codes, slow requests
- **Security Event Logging**: Specialized logging for failed logins, rate limits, suspicious activity
- **Environment-based Configuration**: Different log levels for dev/staging/production
- **Docker Log Rotation**: Automatic rotation (10MB, 5 files) configured in docker-compose

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `LOG_JSON_ENABLED` | `true` | Enable JSON format (`true`) or human-readable (`false`) |
| `LOG_SLOW_REQUEST_THRESHOLD_MS` | `1000` | Threshold for slow request warnings (ms) |
| `CORRELATION_ID_HEADER` | `X-Request-ID` | Header name for correlation ID |

### Environment Recommendations

| Environment | LOG_LEVEL | LOG_JSON_ENABLED |
|-------------|-----------|------------------|
| Development | DEBUG | false |
| Staging | INFO | true |
| Production | WARNING | true |

### Service-specific Setup

```python
# In main.py of each service
from api.common.logging_config import setup_logging, get_logger

log_level = os.getenv('LOG_LEVEL', 'INFO')
json_enabled = os.getenv('LOG_JSON_ENABLED', 'true').lower() in ('true', '1', 'yes')
setup_logging(service_name="public_api", log_level=log_level, json_enabled=json_enabled)
logger = get_logger(__name__)
```

## Log Format

### JSON Format (Production)

```json
{
  "timestamp": "2024-01-15T10:30:45.123456Z",
  "level": "INFO",
  "logger": "api.public.main",
  "message": "Request completed",
  "service": "public_api",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "method": "POST",
  "path": "/auth/login",
  "status_code": 200,
  "duration_ms": 45.2,
  "client_ip": "192.168.1.100"
}
```

### Text Format (Development)

```
2024-01-15 10:30:45.123 - INFO     - api.public.main - [550e8400-e29b-41d4-a716-446655440000] - Request completed
```

## Correlation IDs

### How It Works

1. Client sends request with `X-Request-ID` header (optional)
2. `CorrelationIdMiddleware` generates UUID if header is absent
3. Correlation ID is stored in context and added to all log entries
4. Response includes `X-Request-ID` header
5. Frontend/other services can use ID for distributed tracing

### Usage Example

```bash
# Send request with custom correlation ID
curl -H "X-Request-ID: my-trace-id-123" https://api.example.com/search

# Response will include the same ID
# X-Request-ID: my-trace-id-123
```

### Code Example

```python
from api.common.logging_config import get_correlation_id, set_correlation_id

# Get current correlation ID (set by middleware)
correlation_id = get_correlation_id()

# Manually set correlation ID (for background tasks)
set_correlation_id("custom-id-123")
```

## Security Event Logging

### Event Types

| Event | Level | Description |
|-------|-------|-------------|
| `failed_login` | WARNING | Failed authentication attempt |
| `rate_limit_exceeded` | WARNING | Rate limit hit |
| `suspicious_activity` | WARNING | Potential attack patterns detected |
| `db_connection_failure` | ERROR | Database connection issues |
| `service_startup` | INFO | Service started |
| `service_shutdown` | INFO | Service stopped |
| `high_error_rate` | ERROR | High percentage of errors detected |

### Usage Example

```python
from api.common.security_logger import SecurityEventLogger

security_logger = SecurityEventLogger("public_api")

# Log failed login
security_logger.log_failed_login(
    username="user123",
    ip="192.168.1.100",
    reason="invalid_password"
)

# Log rate limit exceeded
security_logger.log_rate_limit_exceeded(
    ip="192.168.1.100",
    endpoint="/api/search",
    limit="100/hour"
)

# Log suspicious activity
security_logger.log_suspicious_activity(
    ip="192.168.1.100",
    activity_type="sql_injection_attempt",
    details={"path": "/api/search", "pattern": "' OR 1=1"}
)
```

### Monitoring Alerts

Recommended alert thresholds:

| Event | Threshold | Action |
|-------|-----------|--------|
| Failed logins | >5/minute from same IP | Investigate potential brute-force |
| Rate limit exceeded | >100/minute | Check for abuse |
| High error rate | >10% over 5 minutes | Investigate service health |
| DB connection failures | Any occurrence | Immediate investigation |

### Error Rate Calculation

**Important**: Error rate calculation is performed by the log aggregation system (Grafana/Loki, ELK, CloudWatch), not by the application itself. The `log_high_error_rate()` method in `SecurityEventLogger` is available for custom implementations if needed, but the recommended approach is:

1. **Collect metrics** - Each request logs `status_code` in JSON format
2. **Aggregate in external system** - Use Grafana/Loki or ELK to calculate error rate:
   ```
   error_rate = count(status_code >= 500) / count(all_requests) * 100
   ```
3. **Set up alerts** - Configure alerting rules in your monitoring system:
   - Grafana: Create alert rule with `rate(errors) / rate(requests) > 0.1`
   - CloudWatch: Create metric filter and alarm
   - ELK: Use Watcher or Kibana alerting

Example Loki query for error rate:
```logql
sum(rate({service="public_api"} | json | status_code >= 500 [5m]))
/
sum(rate({service="public_api"} | json | status_code > 0 [5m]))
* 100
```

## Performance Metrics

### Tracked Metrics

- Request duration (milliseconds)
- HTTP status code
- Slow request warnings (duration > threshold)
- Response time header (`X-Response-Time`)

### Slow Request Detection

Requests exceeding `LOG_SLOW_REQUEST_THRESHOLD_MS` (default 1000ms) are logged as warnings:

```json
{
  "level": "WARNING",
  "message": "Slow request detected",
  "path": "/api/search",
  "duration_ms": 2345.67,
  "threshold_ms": 1000
}
```

### Analyzing Performance

```bash
# Find slow requests (using jq)
docker-compose logs public_api | grep '"duration_ms"' | jq 'select(.duration_ms > 1000)'

# Calculate average response time
docker-compose logs public_api | grep '"duration_ms"' | jq -s 'map(.duration_ms) | add/length'

# Count requests by status code
docker-compose logs public_api | grep '"status_code"' | jq '.status_code' | sort | uniq -c
```

## Docker Log Rotation

### Configuration

Log rotation is configured in `docker-compose.production.yml`:

```yaml
x-logging: &default-logging
  driver: "json-file"
  options:
    max-size: "10m"    # Max 10MB per log file
    max-file: "5"      # Keep 5 rotated files
    compress: "true"   # Compress old logs
```

### Viewing Logs

```bash
# View logs for specific service
docker-compose logs -f public_api

# View logs with timestamps
docker-compose logs -t public_api

# View last 100 lines
docker-compose logs --tail=100 public_api

# Filter logs by level
docker-compose logs public_api | grep '"level":"ERROR"'
```

## Centralized Logging (Production)

### Grafana Loki Setup

1. Add Loki and Promtail to docker-compose:

```yaml
loki:
  image: grafana/loki:2.9.0
  ports:
    - "3100:3100"
  volumes:
    - ./loki-config.yaml:/etc/loki/local-config.yaml
  command: -config.file=/etc/loki/local-config.yaml

promtail:
  image: grafana/promtail:2.9.0
  volumes:
    - /var/lib/docker/containers:/var/lib/docker/containers:ro
    - ./promtail-config.yaml:/etc/promtail/config.yaml
  command: -config.file=/etc/promtail/config.yaml
```

2. Configure Promtail to collect Docker logs
3. Add Loki as data source in Grafana
4. Create dashboards for log visualization

### ELK Stack Setup

1. Deploy Elasticsearch, Logstash, Kibana
2. Configure Logstash to parse JSON logs
3. Create Elasticsearch index templates
4. Build Kibana dashboards

### AWS CloudWatch

For AWS deployments, use the `awslogs` driver:

```yaml
logging:
  driver: awslogs
  options:
    awslogs-group: "/ecs/ssn-api"
    awslogs-region: "us-east-1"
    awslogs-stream-prefix: "public_api"
```

## Best Practices

### DO

1. **Use structured logging** - Always include `extra` context in log calls
2. **Use appropriate levels** - DEBUG for development details, INFO for general events, WARNING for issues, ERROR for failures
3. **Include correlation IDs** - Always log with context for traceability
4. **Monitor security events** - Set up alerts for critical security logs
5. **Rotate logs** - Use Docker log rotation or centralized logging

### DON'T

1. **Log sensitive data** - Never log passwords, tokens, SSN, credit cards
2. **Log in hot paths** - Avoid DEBUG logging in high-frequency code paths
3. **Ignore errors** - Always log exceptions with full traceback
4. **Use print statements** - Use the logging system instead

### Code Examples

```python
from api.common.logging_config import get_logger

logger = get_logger(__name__)

# Good: Structured logging with context
logger.info(
    "Order created",
    extra={
        "user_id": user.id,
        "order_id": order.id,
        "amount": order.total
    }
)

# Good: Error logging with exception info
try:
    process_payment()
except Exception as e:
    logger.error(
        "Payment processing failed",
        exc_info=True,
        extra={
            "user_id": user.id,
            "error_type": type(e).__name__
        }
    )

# Bad: Logging sensitive data
# logger.info(f"User {username} logged in with password {password}")  # NEVER DO THIS

# Bad: Using print
# print(f"Processing order {order_id}")  # Use logger instead
```

## Troubleshooting

### Logs Not Appearing

1. Check `LOG_LEVEL` in `.env` - set to DEBUG for verbose output
2. Verify service is running: `docker-compose ps`
3. Check Docker logs: `docker-compose logs service_name`
4. Ensure logging is configured before any log calls

### JSON Parsing Errors

1. Verify `LOG_JSON_ENABLED=true`
2. Check for multiline log entries
3. Validate JSON: `docker-compose logs public_api | head -1 | jq .`

### Missing Correlation IDs

1. Ensure middleware is added to FastAPI app in correct order
2. Verify `CorrelationIdMiddleware` is the last middleware added
3. Check that logging context is properly imported

### High Disk Usage

1. Check log rotation settings in `docker-compose.production.yml`
2. Reduce `max-size` or `max-file` values
3. Consider centralized logging to offload storage
4. Lower `LOG_LEVEL` to reduce log volume

## Telegram Alerting

### Overview

Critical events are automatically sent to a Telegram channel for immediate notification of operations team. This feature provides real-time alerts without requiring external monitoring infrastructure.

### Configuration

1. **Create Alert Bot:**
   ```bash
   # Talk to @BotFather in Telegram
   /newbot
   # Follow instructions, copy token
   ```

2. **Get Channel ID:**
   ```bash
   # Add bot to your channel as administrator
   # Send test message to channel
   # Call Telegram API:
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   # Find chat.id in response (negative number for channels)
   ```

3. **Set Environment Variables:**
   ```bash
   TELEGRAM_ALERT_BOT_TOKEN=your_bot_token_here
   TELEGRAM_ALERT_CHANNEL_ID=-1001234567890
   ```

### Alert Types

| Severity | Emoji | Events |
|----------|-------|--------|
| Critical | 🚨 | Database connection failures, high error rate (>10%) |
| Warning | ⚠️ | Multiple 500 errors (>5/min), rate limit abuse (>100 requests) |
| Info | ℹ️ | Service startup, service shutdown |

### Rate Limiting

Alerts are automatically rate-limited to prevent spam:
- Maximum 1 alert per minute per event type
- Duplicate alerts within 60 seconds are suppressed
- Alert throttling is tracked in-memory per service

### Message Format

Alerts are formatted with HTML for readability:

```
🚨 CRITICAL
Service: public_api
Event: db_failure

Database Connection Failure
ConnectionError: connection timeout

2025-12-02 10:30:45 UTC
```

### Troubleshooting

**Alerts not received:**
1. Check bot token is valid: `curl https://api.telegram.org/bot<TOKEN>/getMe`
2. Verify bot is admin in channel
3. Check channel ID is correct (negative for channels)
4. Review service logs for notifier errors:
   ```bash
   docker-compose logs public_api | grep "Telegram"
   ```

**Too many alerts:**
- Rate limiting is automatic (1/min per type)
- Check for underlying issues causing repeated errors
- Adjust thresholds in `api/common/security_logger.py` if needed

**Alerts delayed:**
- Alerts are sent asynchronously (non-blocking)
- Network issues may cause delays
- Check Telegram API status: https://status.telegram.org/

### Disabling Alerting

To disable Telegram alerting:
```bash
# Leave variables empty or unset
TELEGRAM_ALERT_BOT_TOKEN=
TELEGRAM_ALERT_CHANNEL_ID=
```

Services will continue logging normally without sending alerts.

### Best Practices

1. **Use separate bot for alerts** (not user-facing bot)
2. **Create dedicated admin channel** for alerts only
3. **Set up multiple admins** in channel for redundancy
4. **Test alerting** after deployment (restart service to trigger startup alert)
5. **Monitor alert volume** to detect issues early
6. **Document escalation procedures** for critical alerts

### Security Considerations

- Bot token is sensitive (treat like password)
- Store in secrets manager in production
- Rotate token if compromised
- Limit channel access to operations team only
- Never log bot token or channel ID
- Use HTTPS for all Telegram API calls (enforced by aiohttp)

## References

- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)
- [Docker Logging Drivers](https://docs.docker.com/config/containers/logging/configure/)
- [Grafana Loki](https://grafana.com/oss/loki/)
- [ELK Stack](https://www.elastic.co/elastic-stack)
- [Telegram Bot API](https://core.telegram.org/bots/api)
