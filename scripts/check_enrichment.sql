SELECT d.ssn, d.id, d.address as orig_addr, m.address as enriched_addr
FROM ssn_database.ssn_data d
JOIN ssn_database.ssn_mutants m ON d.id = m.id
WHERE d.address = '' AND m.address != ''
LIMIT 5
