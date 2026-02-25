-- Агрегированная таблица с лучшими значениями по каждому SSN
CREATE TABLE IF NOT EXISTS ssn_database.ssn_enrichment
ENGINE = MergeTree()
ORDER BY ssn
AS
SELECT
    ssn,
    anyIf(middlename, middlename != '' AND middlename IS NOT NULL) as best_middlename,
    anyIf(address, address != '' AND address IS NOT NULL) as best_address,
    anyIf(city, city != '' AND city IS NOT NULL) as best_city,
    anyIf(state, state != '' AND state IS NOT NULL) as best_state,
    anyIf(zip, zip != '' AND zip IS NOT NULL) as best_zip,
    anyIf(phone, phone != '' AND phone IS NOT NULL) as best_phone,
    anyIf(email, email != '' AND email IS NOT NULL) as best_email,
    anyIf(dob, dob != '' AND dob IS NOT NULL) as best_dob
FROM ssn_database.ssn_data
WHERE ssn IN (SELECT ssn FROM ssn_database.duplicate_ssns)
GROUP BY ssn
