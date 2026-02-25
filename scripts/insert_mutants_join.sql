INSERT INTO ssn_database.ssn_mutants (id, firstname, lastname, middlename, address, city, state, zip, phone, email, ssn, dob, source_table, tag)
SELECT
    d.id,
    d.firstname,
    d.lastname,
    if(d.middlename = '' OR d.middlename IS NULL, e.best_middlename, d.middlename) as middlename,
    if(d.address = '' OR d.address IS NULL, e.best_address, d.address) as address,
    if(d.city = '' OR d.city IS NULL, e.best_city, d.city) as city,
    if(d.state = '' OR d.state IS NULL, e.best_state, d.state) as state,
    if(d.zip = '' OR d.zip IS NULL, e.best_zip, d.zip) as zip,
    if(d.phone = '' OR d.phone IS NULL, e.best_phone, d.phone) as phone,
    if(d.email = '' OR d.email IS NULL, e.best_email, d.email) as email,
    d.ssn,
    if(d.dob = '' OR d.dob IS NULL, e.best_dob, d.dob) as dob,
    d.source_table,
    'mutant' as tag
FROM ssn_database.ssn_data d
INNER JOIN ssn_database.ssn_enrichment e ON d.ssn = e.ssn
