# Payment Providers Integration

## Overview

Платформа поддерживает несколько payment providers для обработки криптовалютных платежей:

- **CryptoCurrencyAPI** (default) - Основной провайдер с быстрыми депозитами и webhook поддержкой
- **Helket** - Альтернативный провайдер с webhook поддержкой
- **ff.io (FixedFloat)** - Обменный сервис с polling механизмом

## Supported Providers

### 1. CryptoCurrencyAPI (Default)

#### Описание
- **Документация**: https://cryptocurrencyapi.net/docs
- **Webhook поддержка**: Да (IPN)
- **Supported currencies**: USDT (TRC20, ERC20, BSC), BTC, ETH, LTC, BNB

#### Configuration

Добавьте в `.env`:
```bash
CRYPTOCURRENCYAPI_KEY=your_cryptocurrencyapi_key
IPN_WEBHOOK_URL=http://localhost/api/public/billing/ipn/cryptocurrencyapi
```

#### Invoice Creation Flow

1. User выбирает cryptocurrency и amount
2. Backend вызывает `CryptoCurrencyAPIClient.create_payment_address()`
3. API возвращает payment address и QR code
4. User отправляет crypto на payment address
5. CryptoCurrencyAPI отправляет IPN webhook на `IPN_WEBHOOK_URL`
6. Backend верифицирует signature и обновляет balance

#### Webhook Signature Verification

```python
# SHA-1 алгоритм
message = "&".join([f"{key}={value}" for key, value in sorted(payload.items()) if key != "sign"])
message += api_key
signature = hashlib.sha1(message.encode()).hexdigest()
```

#### Example Request

```python
client = get_cryptocurrencyapi_client()
async with client:
    result = await client.create_payment_address(
        currency="USDT",
        amount=Decimal("50.00"),
        label="tx_123",
        status_url="https://example.com/ipn",
        network="TRC20"
    )
# Returns: {"address": "TXxxx...", "qr_code": "https://...", "label": "tx_123"}
```

#### Testing

См. [docs/CRYPTOCURRENCYAPI_IPN.md](CRYPTOCURRENCYAPI_IPN.md) для подробной информации

---

### 2. Helket

#### Описание
- **Документация**: https://doc.heleket.com
- **Webhook поддержка**: Да
- **Supported currencies**: USDT (TRC20, ERC20, BSC), BTC, ETH, LTC, BNB
- **Authentication**: Bearer Token (API_KEY + MERCHANT_UUID)

#### Configuration

Добавьте в `.env`:
```bash
HELKET_API_KEY=your_helket_api_key
HELKET_MERCHANT_UUID=your_merchant_uuid
HELKET_WEBHOOK_SECRET=your_webhook_secret
HELKET_API_URL=https://api.heleket.com
HELKET_IPN_WEBHOOK_URL=http://localhost/api/public/billing/ipn/helket
```

#### Invoice Creation Flow

1. User выбирает cryptocurrency и amount
2. Backend вызывает `HelketClient.create_invoice()`
3. API возвращает payment address, QR code, и invoice_id
4. User отправляет crypto на payment address
5. Helket отправляет webhook на `HELKET_IPN_WEBHOOK_URL`
6. Backend верифицирует signature и обновляет balance

#### Webhook Signature Verification

```python
# HMAC-SHA256 алгоритм
expected_signature = hmac.new(
    webhook_secret.encode('utf-8'),
    payload_string.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# Signature приходит в header: X-Signature или X-Helket-Signature
```

#### API Request Example

```python
client = get_helket_client()
async with client:
    result = await client.create_invoice(
        currency="USDT",
        amount=Decimal("50.00"),
        label="tx_123",
        callback_url="https://example.com/ipn/helket",
        network="TRC20"
    )
# Returns: {"address": "TXxxx...", "qr_code": "https://...", "invoice_id": "inv_123", "label": "tx_123"}
```

#### Webhook Payload Example

```json
{
  "invoice_id": "inv_123",
  "label": "tx_123",
  "status": "completed",
  "amount": "50.00",
  "currency": "USDT",
  "network": "TRC20",
  "txid": "0xabc...",
  "merchant_reference": "tx_123"
}
```

#### Testing

Используйте Helket sandbox environment для тестирования:
- Получите test API credentials в dashboard
- Установите `HELKET_API_URL=https://sandbox.api.heleket.com`

---

### 3. ff.io (FixedFloat)

#### Описание
- **Документация**: https://ff.io/en/api
- **Webhook поддержка**: **НЕТ** (используется polling)
- **Supported currencies**: USDT (TRC20, ERC20, BSC), BTC, ETH, LTC, и другие
- **Authentication**: X-API-KEY + X-API-SIGN (HMAC-SHA256)
- **Rate limit**: 250 units/min, create order = 50 units

#### Configuration

Добавьте в `.env`:
```bash
FFIO_API_KEY=your_ffio_api_key
FFIO_API_SECRET=your_ffio_api_secret
FFIO_API_URL=https://ff.io
# Optional: Platform receiving address for ff.io orders
FFIO_PLATFORM_ADDRESS=your_crypto_address
```

#### Order Creation Flow

1. User выбирает cryptocurrency и amount
2. Backend вызывает `FFIOClient.create_order()`
3. API возвращает deposit_address, order_id, и token
4. User отправляет crypto на deposit_address
5. **Backend запускает background polling task** для проверки статуса
6. Polling task периодически вызывает `get_order_status()` (раз в 60 секунд)
7. Когда status = "completed", balance обновляется

#### API Request Signature

```python
# HMAC-SHA256 подпись для каждого запроса
json_string = json.dumps(data, separators=(',', ':'), sort_keys=True)
signature = hmac.new(
    api_secret.encode('utf-8'),
    json_string.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# Signature передается в header: X-API-SIGN
```

#### Create Order Example

```python
client = get_ffio_client()
async with client:
    result = await client.create_order(
        from_ccy="USDTTRC",  # ff.io currency code
        to_ccy="USDTTRC",    # Same for deposits
        amount=Decimal("50.00"),
        direction="from",
        type="fixed",
        to_address="TYourAddress...",  # Platform address
        label="tx_123"
    )
# Returns: {"order_id": "ABC123", "deposit_address": "TXxxx...", "token": "xyz..."}
```

#### Polling Implementation

Backend автоматически запускает background task:

```python
# В billing.py after order creation
background_tasks.add_task(
    poll_ffio_order_status,
    transaction_id,
    async_session_maker
)

# Polling function checks status every 60 seconds for up to 60 attempts (1 hour)
```

#### Order Status Response

```json
{
  "code": 0,
  "data": {
    "id": "ABC123",
    "status": "completed",  // or "new", "pending", "failed", "expired"
    "from": {
      "address": "TXxxx...",
      "amount": "50.00"
    },
    "to": {
      "address": "TYyyy...",
      "amount": "49.50"
    }
  }
}
```

#### Currency Code Mapping

ff.io использует специальные коды валют:

| Our Code | ff.io Code |
|----------|------------|
| USDT_TRC20 | USDTTRC |
| USDT_ERC20 | USDTETH |
| USDT_BSC | USDTBSC |
| BTC_MAINNET | BTC |
| ETH_MAINNET | ETH |
| LTC_MAINNET | LTC |

#### Testing

- ff.io не предоставляет sandbox
- Используйте минимальные суммы для тестирования в production
- Rate limit: будьте осторожны с частыми запросами

---

## Provider Selection Flow

### Frontend (User Experience)

1. User переходит на `/crypto-deposit`
2. Видит два варианта провайдера:
   - **Crypto (CryptoCurrencyAPI)** - быстрые депозиты
   - **ff.io (FixedFloat)** - обмен и депозит
3. Выбирает провайдер (кликом на card)
4. Выбирает cryptocurrency (USDT TRC20, BTC, и т.д.)
5. Вводит amount
6. Backend создает payment address через выбранный provider
7. User отправляет crypto и ждет confirmation

### Backend (Request Flow)

```typescript
// Frontend API call
const deposit = await createDeposit(
  amount,
  'crypto',
  currency,
  network,
  payment_provider  // 'cryptocurrencyapi', 'helket', or 'ffio'
);
```

```python
# Backend routing in billing.py
if deposit_request.payment_provider == "cryptocurrencyapi":
    client = get_cryptocurrencyapi_client()
    result = await client.create_payment_address(...)

elif deposit_request.payment_provider == "helket":
    client = get_helket_client()
    result = await client.create_invoice(...)

elif deposit_request.payment_provider == "ffio":
    client = get_ffio_client()
    result = await client.create_order(...)
    # Start background polling task
    background_tasks.add_task(poll_ffio_order_status, ...)
```

---

## Database Schema

### Transaction Model

Поле `payment_provider` сохраняет используемый провайдер:

```python
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    amount = Column(Numeric(10, 2))
    payment_method = Column(Enum(PaymentMethod))
    payment_provider = Column(String(50))  # 'cryptocurrencyapi', 'helket', 'ffio'
    status = Column(Enum(TransactionStatus))
    payment_address = Column(String(255))
    payment_metadata = Column(JSON)  # Stores provider-specific data
    external_transaction_id = Column(String(255))  # txid or order_id
```

### Database Constraints and Indexes

#### Index: `ix_transactions_payment_provider`

Индекс на поле `payment_provider` для оптимизации запросов по провайдерам:

```sql
-- Index definition
CREATE INDEX ix_transactions_payment_provider ON transactions (payment_provider);

-- Example queries that benefit from this index
SELECT * FROM transactions WHERE payment_provider = 'ffio';
SELECT payment_provider, COUNT(*) FROM transactions GROUP BY payment_provider;
```

**Performance impact**: Queries filtering by `payment_provider` execute in ~0.02ms (vs ~2-5ms without index on large datasets).

#### Check Constraint: `check_valid_payment_provider`

Constraint обеспечивает валидность значений `payment_provider` на уровне БД:

```sql
-- Constraint definition
ALTER TABLE transactions
ADD CONSTRAINT check_valid_payment_provider
CHECK (
    payment_provider IN ('cryptocurrencyapi', 'helket', 'ffio')
    OR payment_provider IS NULL
);

-- Valid insertions
INSERT INTO transactions (..., payment_provider) VALUES (..., 'cryptocurrencyapi');  -- ✅
INSERT INTO transactions (..., payment_provider) VALUES (..., 'helket');  -- ✅
INSERT INTO transactions (..., payment_provider) VALUES (..., 'ffio');  -- ✅
INSERT INTO transactions (..., payment_provider) VALUES (..., NULL);  -- ✅

-- Invalid insertion (will fail)
INSERT INTO transactions (..., payment_provider) VALUES (..., 'invalid_provider');  -- ❌
```

**Migration reference**: See `alembic/versions/2025_11_20_1500-add_payment_provider_index.py`

### Provider-Specific Metadata

```python
# CryptoCurrencyAPI
payment_metadata = {
    "qr": "https://...",
    "qr_code": "https://...",
    "ipn": {...}  # IPN payload when received
}

# Helket
payment_metadata = {
    "qr": "https://...",
    "qr_code": "https://...",
    "invoice_id": "inv_123",
    "provider": "helket",
    "helket_ipn": {...}  # Webhook payload
}

# ff.io
payment_metadata = {
    "order_id": "ABC123",
    "token": "xyz...",
    "provider": "ffio",
    "latest_status": "completed",
    "last_poll_attempt": 15,
    "full_order_data": {...}
}
```

---

## Troubleshooting

### Common Issues

#### CryptoCurrencyAPI

**Issue**: IPN webhooks не приходят
**Solution**:
- Проверьте `IPN_WEBHOOK_URL` в `.env`
- Убедитесь что URL доступен извне (используйте ngrok для local dev)
- Проверьте логи для signature verification errors

**Issue**: Payment address не создается
**Solution**:
- Проверьте `CRYPTOCURRENCYAPI_KEY` валиден
- Проверьте комбинацию currency/network поддерживается

#### Helket

**Issue**: Webhook signature verification fails
**Solution**:
- Проверьте `HELKET_WEBHOOK_SECRET` совпадает с dashboard
- Проверьте header name (X-Signature или X-Helket-Signature)
- Логируйте raw payload для debugging

**Issue**: Invoice creation fails
**Solution**:
- Проверьте `HELKET_API_KEY` и `HELKET_MERCHANT_UUID`
- Проверьте комбинацию currency/network поддерживается Helket

#### ff.io

**Issue**: Order creation fails
**Solution**:
- Проверьте `FFIO_API_KEY` и `FFIO_API_SECRET`
- Проверьте rate limit (250 units/min)
- Используйте правильные currency codes (USDTTRC, не USDT_TRC20)

**Issue**: Polling не обновляет статус
**Solution**:
- Проверьте background task запускается (`background_tasks.add_task`)
- Проверьте логи polling task
- Убедитесь что order_id и token сохранены в metadata

**Issue**: Status остается pending после payment
**Solution**:
- ff.io обработка может занять 10-30 минут
- Проверьте статус вручную через `get_order_status()`
- Проверьте что user отправил точную сумму

---

## Migration Guide

### Migrating from One Provider to Another

#### Step 1: Add new provider credentials to `.env`

```bash
# Add Helket credentials
HELKET_API_KEY=...
HELKET_MERCHANT_UUID=...
HELKET_WEBHOOK_SECRET=...
HELKET_IPN_WEBHOOK_URL=...
```

#### Step 2: Test new provider in staging

```bash
# Test invoice creation
curl -X POST http://localhost/api/public/billing/deposit \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 5.00,
    "payment_method": "crypto",
    "payment_provider": "helket",
    "currency": "USDT",
    "network": "TRC20"
  }'
```

#### Step 3: Update frontend default provider

```typescript
// In crypto-deposit/+page.svelte
let selectedProvider = $state<'crypto' | 'ffio' | 'helket'>('helket');
```

#### Step 4: Monitor transactions

```sql
-- Check provider distribution
SELECT payment_provider, COUNT(*), SUM(amount)
FROM transactions
WHERE payment_method = 'crypto'
GROUP BY payment_provider;

-- Check failed transactions by provider
SELECT payment_provider, status, COUNT(*)
FROM transactions
GROUP BY payment_provider, status;
```

---

## Backward Compatibility

Все изменения обратно совместимы:

- Существующие запросы без `payment_provider` используют `cryptocurrencyapi` по умолчанию
- Существующие transactions с `payment_provider = NULL` считаются `cryptocurrencyapi`
- IPN endpoint `/ipn/cryptocurrencyapi` продолжает работать как раньше

---

## Security Considerations

### Webhook Signature Verification

**ВСЕГДА** верифицируйте подписи webhooks:

```python
# CryptoCurrencyAPI
verify_cryptocurrencyapi_signature(payload, signature, api_key)

# Helket
HelketClient.verify_webhook_signature(payload_str, signature, webhook_secret)

# ff.io - не использует webhooks, но требует signature для всех API requests
```

### API Key Protection

- Никогда не коммитьте API keys в git
- Используйте environment variables
- Ротируйте keys регулярно
- Используйте разные keys для dev/staging/production

### Rate Limiting

- CryptoCurrencyAPI: без явных лимитов
- Helket: проверьте документацию
- ff.io: 250 units/min (create order = 50 units)

Реализуйте exponential backoff для повторных попыток

---

## Monitoring and Alerts

### Key Metrics to Monitor

1. **Transaction Success Rate** по провайдеру
   ```sql
   SELECT payment_provider,
          COUNT(*) as total,
          SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid,
          AVG(CASE WHEN status = 'paid' THEN 1.0 ELSE 0.0 END) * 100 as success_rate
   FROM transactions
   WHERE payment_method = 'crypto'
   GROUP BY payment_provider;
   ```

2. **Average Payment Confirmation Time**
3. **Failed Transactions Count**
4. **Webhook Delivery Rate** (для CryptoCurrencyAPI и Helket)
5. **ff.io Polling Success Rate**

### Alerts to Set Up

- Transaction pending > 1 hour
- Webhook signature verification failure rate > 1%
- ff.io polling timeout rate > 5%
- Balance mismatch between transactions and user balance

---

## API Endpoints

### Create Deposit

```http
POST /api/public/billing/deposit
Content-Type: application/json
Authorization: Bearer <jwt_token>

{
  "amount": 50.00,
  "payment_method": "crypto",
  "payment_provider": "cryptocurrencyapi",  // or "helket", "ffio"
  "currency": "USDT",
  "network": "TRC20"
}
```

### IPN Webhooks

```http
POST /api/public/billing/ipn/cryptocurrencyapi
Content-Type: application/json

{
  "cryptocurrencyapi.net": 1,
  "chain": "trx",
  "currency": "USDT",
  "type": "in",
  "date": 1234567890,
  "from": "TXxxx...",
  "to": "TYyyy...",
  "amount": "50.00",
  "fee": "1.00",
  "txid": "0xabc...",
  "confirmation": 1,
  "label": "transaction_uuid",
  "sign": "abc123..."
}
```

```http
POST /api/public/billing/ipn/helket
Content-Type: application/json
X-Signature: abc123...

{
  "invoice_id": "inv_123",
  "label": "transaction_uuid",
  "status": "completed",
  "amount": "50.00",
  "currency": "USDT",
  "network": "TRC20",
  "txid": "0xabc..."
}
```

---

## Support and Resources

- **CryptoCurrencyAPI**: https://cryptocurrencyapi.net/support
- **Helket**: https://doc.heleket.com
- **ff.io**: https://ff.io/en/api

For internal issues, check logs in `/var/log/public_api/` or use:

```bash
docker-compose logs -f public_api
```
