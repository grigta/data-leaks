#!/bin/bash
# Батчевая вставка дубликатов в ssn_mutants
# Использует хеш-партицирование для обхода лимита памяти

# Общее количество батчей (100 батчей по ~1.36M SSN = 2.7M записей)
TOTAL_BATCHES=100

for bucket in $(seq 0 $((TOTAL_BATCHES - 1))); do
    echo "$(date '+%Y-%m-%d %H:%M:%S') Processing bucket $bucket of $((TOTAL_BATCHES - 1))..."

    docker compose exec -T clickhouse clickhouse-client --send_timeout=3600 --receive_timeout=3600 --query "
INSERT INTO ssn_database.ssn_mutants (id, firstname, lastname, middlename, address, city, state, zip, phone, email, ssn, dob, source_table, tag)
SELECT
    id,
    firstname,
    lastname,
    if(middlename = '' OR middlename IS NULL,
       anyIf(middlename, middlename != '' AND middlename IS NOT NULL) OVER (PARTITION BY ssn),
       middlename) as middlename,
    if(address = '' OR address IS NULL,
       anyIf(address, address != '' AND address IS NOT NULL) OVER (PARTITION BY ssn),
       address) as address,
    if(city = '' OR city IS NULL,
       anyIf(city, city != '' AND city IS NOT NULL) OVER (PARTITION BY ssn),
       city) as city,
    if(state = '' OR state IS NULL,
       anyIf(state, state != '' AND state IS NOT NULL) OVER (PARTITION BY ssn),
       state) as state,
    if(zip = '' OR zip IS NULL,
       anyIf(zip, zip != '' AND zip IS NOT NULL) OVER (PARTITION BY ssn),
       zip) as zip,
    if(phone = '' OR phone IS NULL,
       anyIf(phone, phone != '' AND phone IS NOT NULL) OVER (PARTITION BY ssn),
       phone) as phone,
    if(email = '' OR email IS NULL,
       anyIf(email, email != '' AND email IS NOT NULL) OVER (PARTITION BY ssn),
       email) as email,
    ssn,
    if(dob = '' OR dob IS NULL,
       anyIf(dob, dob != '' AND dob IS NOT NULL) OVER (PARTITION BY ssn),
       dob) as dob,
    source_table,
    'mutant' as tag
FROM ssn_database.ssn_data
WHERE ssn IN (
    SELECT ssn FROM ssn_database.duplicate_ssns
    WHERE cityHash64(ssn) % $TOTAL_BATCHES = $bucket
)
" 2>&1 | grep -v "level=warning" || echo "ERROR in bucket $bucket"

    # Статус после каждого батча
    count=$(docker compose exec -T clickhouse clickhouse-client --query "SELECT count() FROM ssn_database.ssn_mutants" 2>/dev/null)
    echo "$(date '+%Y-%m-%d %H:%M:%S') Bucket $bucket done. Total rows in ssn_mutants: $count"
done

echo "$(date '+%Y-%m-%d %H:%M:%S') All batches completed!"
