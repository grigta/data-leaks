# Security Documentation

This document describes the security measures implemented in the SSN Management System and provides guidelines for maintaining security.

## Table of Contents

1. [Overview](#overview)
2. [SQL Injection Protection](#sql-injection-protection)
3. [Input Validation](#input-validation)
4. [Data Sanitization](#data-sanitization)
5. [Authentication & Authorization](#authentication--authorization)
6. [Rate Limiting](#rate-limiting)
7. [Logging & Monitoring](#logging--monitoring)
8. [Testing](#testing)
9. [Deployment Security](#deployment-security)
10. [Incident Response](#incident-response)
11. [Security Checklist](#security-checklist)

## Overview

The application implements multiple layers of security protection following the defense-in-depth principle:

1. **Input Validation** - Centralized validators reject malicious input
2. **Data Sanitization** - Sanitizers clean data before processing
3. **Parameterized Queries** - All SQL queries use parameters, not string concatenation
4. **Authentication** - JWT-based authentication with secure token handling
5. **Rate Limiting** - Protection against brute force and DoS attacks
6. **Logging** - Security events are logged for monitoring

### Security Standards

This implementation follows:
- OWASP Top 10 Web Application Security Risks
- CWE/SANS Top 25 Most Dangerous Software Errors
- SQLite and PostgreSQL security best practices

## SQL Injection Protection

### Parameterized Queries

All database queries use parameterized statements. **Never** use string formatting or concatenation for SQL queries.

**Safe Example:**
```python
# Correct - using parameterized query
cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
```

**Unsafe Example (NEVER DO THIS):**
```python
# WRONG - vulnerable to SQL injection
cursor.execute(f"SELECT * FROM users WHERE username = '{username}'")
```

### LIMIT Parameter Protection

The `LIMIT` clause is also parameterized using the `_safe_limit()` method in `SearchEngine`:

```python
# Safe LIMIT handling
limit_clause, limit_params = self._safe_limit(limit)
query = f"SELECT * FROM ssn_1{limit_clause}"
results = self._execute_search(query, base_params, limit_params)
```

### Validation Before Query

All public search methods validate input before executing queries:

```python
# Validation in search_by_ssn
is_valid, error = validate_ssn(str(ssn))
if not is_valid:
    self.logger.warning(f"SSN validation failed: {error}")
    return self._format_results_to_json([])
```

### Relevant Files

- [database/search_engine.py](../database/search_engine.py) - Search engine with parameterized queries
- [api/common/validators.py](../api/common/validators.py) - Input validators
- [api/common/sanitizers.py](../api/common/sanitizers.py) - Data sanitizers

## Input Validation

### Centralized Validators

All input validation is centralized in `api/common/validators.py`:

| Validator | Purpose | Max Length |
|-----------|---------|------------|
| `validate_ssn()` | SSN format (9 digits or XXX-XX-XXXX) | 11 chars |
| `validate_name()` | Names (letters, spaces, hyphens, apostrophes) | 100 chars |
| `validate_email()` | Email format | 254 chars |
| `validate_phone()` | Phone format (10-20 digits) | 20 chars |
| `validate_address()` | Address (printable characters) | 500 chars |
| `validate_zip()` | ZIP code (5 or 9 digits) | 10 chars |
| `validate_state()` | State code (2 uppercase letters) | 2 chars |
| `validate_dob()` | Date of birth (multiple formats) | 10 chars |
| `validate_limit()` | LIMIT parameter (1-1000) | - |
| `validate_coupon_code()` | Coupon codes (alphanumeric + dash) | 20 chars |

### Validator Usage

```python
from api.common.validators import validate_name, validate_email

# Validate name
is_valid, error = validate_name(firstname, "firstname")
if not is_valid:
    raise HTTPException(status_code=400, detail=error)

# Validate email
is_valid, error = validate_email(email)
if not is_valid:
    raise HTTPException(status_code=400, detail=error)
```

### Pydantic Model Validation

Pydantic models in `api/common/models_sqlite.py` enforce:

1. **Maximum lengths** via `Field(max_length=...)`
2. **Minimum lengths** via `Field(min_length=...)`
3. **Format validation** via `@field_validator` decorators
4. **Range validation** via `Field(ge=..., le=...)`

Example:
```python
class SearchByNameRequest(BaseModel):
    firstname: str = Field(..., min_length=2, max_length=100)
    lastname: str = Field(..., min_length=2, max_length=100)
    limit: Optional[int] = Field(default=None, ge=1, le=100)

    @field_validator('firstname', 'lastname')
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z\s\-'\.]+$", v):
            raise ValueError('Invalid characters in name')
        return v.strip()
```

## Data Sanitization

### Centralized Sanitizers

All data sanitization is centralized in `api/common/sanitizers.py`:

| Sanitizer | Purpose |
|-----------|---------|
| `sanitize_string()` | Remove control chars, normalize whitespace, truncate |
| `sanitize_name()` | Clean and normalize names |
| `sanitize_address()` | Clean and uppercase addresses |
| `sanitize_email()` | Lowercase and clean emails |
| `sanitize_phone()` | Extract digits only |
| `sanitize_ssn()` | Format as XXX-XX-XXXX |
| `sanitize_metadata()` | Limit depth and size of JSON metadata |
| `sanitize_html()` | Escape HTML special characters |
| `sanitize_sql_like_pattern()` | Escape LIKE wildcards (%, _) |

### Sanitizer Usage

```python
from api.common.sanitizers import sanitize_name, sanitize_metadata

# Sanitize name before use
firstname = sanitize_name(request.firstname) or ""

# Sanitize metadata before database storage
search_params = sanitize_metadata({
    'firstname': firstname,
    'lastname': lastname
}, max_depth=5, max_size=10000)
```

### Control Character Removal

The `remove_control_chars()` function removes potentially dangerous control characters while preserving safe ones:

```python
# Removed: \x00-\x08, \x0b, \x0c, \x0e-\x1f
# Preserved: \t (tab), \n (newline), \r (carriage return)
```

## Authentication & Authorization

### JWT Tokens

- Tokens are signed with `JWT_SECRET` (minimum 32 characters)
- Default expiration: 24 hours
- Tokens contain: `sub` (username), `user_id`, `exp` (expiration)

### Password Security

- Passwords are hashed using bcrypt via passlib
- Minimum password length: 8 characters (recommended: 12+)
- Maximum password length: 128 characters

### Access Codes

- Access codes control feature access and pricing
- Validated on each request to protected endpoints

### Recommendations

1. **Rotate JWT_SECRET** every 90 days
2. **Use HTTPS** for all API endpoints
3. **Implement password complexity requirements** in registration
4. **Add account lockout** after failed login attempts

## Rate Limiting

### Application Level

FastAPI endpoints use SlowAPI for rate limiting:

```python
from api.public.dependencies import limiter

@router.post("/search")
@limiter.limit("100/hour")
async def search(request: Request):
    ...
```

### Nginx Level

Configure rate limiting in `nginx.conf`:

```nginx
# Limit requests per IP
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
    }
}
```

### Recommended Limits

| Endpoint | Limit |
|----------|-------|
| `/auth/login` | 5/minute |
| `/auth/register` | 3/minute |
| `/search/*` | 100/hour |
| `/instant-ssn` | 10/hour |
| `/billing/*` | 30/minute |

## Logging & Monitoring

### Security Event Logging

The application logs security-relevant events:

```python
# Logged events:
# - Failed login attempts
# - Invalid input attempts (potential injection)
# - Rate limit violations
# - Banned user access attempts
# - Abuse pattern detection

logger.warning(f"Invalid LIMIT value rejected: {limit}")
logger.warning(f"Potential SQL injection detected in {field_name}: {value[:100]}...")
logger.warning(f"User {username} banned: {reason}")
```

### Log Analysis

Monitor logs for:

1. **Repeated validation failures** from same IP (potential attack)
2. **SQL injection patterns** in input
3. **Rate limit violations**
4. **Failed authentication attempts**

### Example Log Grep

```bash
# Find SQL injection attempts
docker-compose logs public_api | grep -i "sql injection"

# Find banned users
docker-compose logs public_api | grep "banned"

# Find validation failures
docker-compose logs public_api | grep "validation failed"
```

## Testing

### Security Test Suite

Run security tests with:

```bash
# Run all security tests
pytest tests/test_sql_injection.py -v

# Run specific test class
pytest tests/test_sql_injection.py::TestSQLInjectionSearchEngine -v
```

### Test Coverage

The security tests verify:

1. **SQL Injection Protection**
   - SSN parameter injection
   - Name parameter injection
   - Address parameter injection
   - LIMIT parameter injection

2. **Validator Rejection**
   - All validators reject SQL injection payloads
   - Validators enforce maximum lengths

3. **Sanitizer Cleaning**
   - Control characters removed
   - Metadata depth/size limited

4. **DoS Protection**
   - Extremely long inputs handled
   - Deeply nested JSON handled

### Adding New Tests

When adding new endpoints, create security tests:

```python
def test_new_endpoint_rejects_injection(self):
    """Test that new endpoint rejects SQL injection."""
    for payload in SQL_INJECTION_PAYLOADS:
        response = client.post("/api/new-endpoint", json={"field": payload})
        # Should return 400 or empty result, not 500
        assert response.status_code in [200, 400]
```

## Deployment Security

### Environment Variables

1. **Never commit `.env`** to version control
2. **Use secrets manager** in production (AWS Secrets Manager, HashiCorp Vault)
3. **Different secrets** for dev/staging/production
4. **Rotate secrets** every 90 days

### Docker Security

```yaml
# docker-compose.yml security settings
services:
  api:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
```

### Network Security

1. **Internal network** for database communication
2. **External access** only through Nginx
3. **Firewall rules** to restrict database ports

### HTTPS/TLS

1. Configure HTTPS via Cloudflare or Let's Encrypt
2. Redirect HTTP to HTTPS
3. Enable HSTS header

## Incident Response

### SQL Injection Detected

1. **Identify** the affected endpoint and IP
2. **Block** the IP at firewall/Nginx level
3. **Review** database for unauthorized changes
4. **Audit** logs for data exfiltration
5. **Patch** any vulnerabilities found
6. **Document** the incident

### Credential Leak

1. **Immediately rotate** all affected secrets
2. **Invalidate** existing JWT tokens
3. **Force password reset** for affected users
4. **Audit** access logs
5. **Notify** affected parties

### Reporting Vulnerabilities

If you discover a security vulnerability:

1. **Do not** disclose publicly
2. **Email** the security contact
3. **Provide** detailed reproduction steps
4. **Allow** reasonable time for fix

## Security Checklist

### Code Review Checklist

- [ ] All SQL queries use parameterized statements
- [ ] User input is validated before use
- [ ] Data is sanitized before storage
- [ ] Authentication is required for protected endpoints
- [ ] Rate limiting is applied
- [ ] Sensitive data is not logged
- [ ] Error messages don't leak internal details

### Deployment Checklist

- [ ] All secrets are strong and unique
- [ ] `.env` is not in version control
- [ ] HTTPS is enabled
- [ ] Rate limiting is configured
- [ ] Logging is enabled
- [ ] Database is not directly accessible
- [ ] Firewall rules are configured
- [ ] Backups are encrypted

### Regular Security Tasks

- [ ] **Weekly**: Review security logs
- [ ] **Monthly**: Run security tests
- [ ] **Quarterly**: Rotate secrets
- [ ] **Annually**: Security audit

---

## References

- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html)
- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [SQLite Security Best Practices](https://www.sqlite.org/security.html)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
