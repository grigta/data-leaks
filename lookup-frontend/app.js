// DOM References
const searchForm = document.getElementById('searchForm');
const firstnameInput = document.getElementById('firstname');
const lastnameInput = document.getElementById('lastname');
const streetInput = document.getElementById('street');
const phoneInput = document.getElementById('phone');
const searchBtn = document.getElementById('searchBtn');
const loadingDiv = document.getElementById('loading');
const errorDiv = document.getElementById('error');
const resultsSection = document.getElementById('results');
const resultsHeader = document.getElementById('resultsHeader');
const resultsTableBody = document.getElementById('resultsTableBody');

// Get auth token from localStorage
function getAuthToken() {
    return localStorage.getItem('access_token');
}

// Form Submit Handler
searchForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Check authentication
    const token = getAuthToken();
    if (!token) {
        showError('Authentication required. Please login to use this feature.');
        return;
    }

    // Validate required fields
    const firstname = firstnameInput.value.trim();
    const lastname = lastnameInput.value.trim();

    if (!firstname || !lastname) {
        showError('First name and last name are required');
        return;
    }

    // Show loading, hide error and results
    loadingDiv.classList.remove('hidden');
    errorDiv.classList.add('hidden');
    resultsSection.classList.add('hidden');
    searchBtn.disabled = true;

    // Construct request body (only include non-empty values)
    const requestBody = {
        firstname,
        lastname
    };

    const street = streetInput.value.trim();
    const phone = phoneInput.value.trim();

    if (street) requestBody.street = street;
    if (phone) requestBody.phone = phone;

    try {
        // Make POST request to lookup API with auth token
        const response = await fetch('/api/lookup/search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(requestBody)
        });

        // Handle auth errors
        if (response.status === 401) {
            throw new Error('Session expired. Please login again.');
        }

        // Handle subscription errors
        if (response.status === 403) {
            throw new Error('Active subscription required. Please purchase a subscription to access this feature.');
        }

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Search failed with status ${response.status}`);
        }

        const data = await response.json();

        // Display results (now using database_matches instead of combined_results)
        displayResults(data.database_matches || []);

    } catch (error) {
        console.error('Search error:', error);
        showError(error.message || 'Network error, please try again');
    } finally {
        // Hide loading, re-enable button
        loadingDiv.classList.add('hidden');
        searchBtn.disabled = false;
    }
});

// Display Results Function
function displayResults(results) {
    // Clear previous results
    resultsTableBody.innerHTML = '';

    if (!results || results.length === 0) {
        resultsSection.classList.remove('hidden');
        resultsHeader.textContent = 'No Results Found';
        resultsTableBody.innerHTML = '<tr><td colspan="11" class="no-results">No matching records found. Try adjusting your search criteria.</td></tr>';
        return;
    }

    // Update header with count
    resultsHeader.textContent = `Search Results (${results.length} found)`;

    // Create table rows for each result
    results.forEach(result => {
        const row = document.createElement('tr');

        // Name column
        const nameParts = [
            result.firstname || '',
            result.middlename || '',
            result.lastname || ''
        ].filter(part => part).join(' ');
        row.appendChild(createCell(nameParts || '—'));

        // SSN column
        row.appendChild(createCell(result.ssn || '—'));

        // DOB column
        row.appendChild(createCell(result.dob || '—'));

        // Age column
        row.appendChild(createCell(result.age !== undefined && result.age !== null ? result.age : '—'));

        // Gender column
        row.appendChild(createCell(result.gender || '—'));

        // Phones column
        row.appendChild(createCell(formatPhones(result.phones)));

        // Emails column
        row.appendChild(createCell(formatEmails(result.emails)));

        // Addresses column
        row.appendChild(createCell(formatAddresses(result.addresses)));

        // City column
        row.appendChild(createCell(result.city || '—'));

        // State column
        row.appendChild(createCell(result.state || '—'));

        // ZIP column
        row.appendChild(createCell(result.zip || '—'));

        resultsTableBody.appendChild(row);
    });

    // Show results section
    resultsSection.classList.remove('hidden');
}

// Helper Functions

function createCell(content) {
    const cell = document.createElement('td');
    cell.textContent = content;
    return cell;
}

function formatPhones(phones) {
    if (!phones || !Array.isArray(phones) || phones.length === 0) {
        return '—';
    }

    return phones.map(phone => {
        if (typeof phone === 'string') {
            return phone;
        }
        if (typeof phone === 'object' && phone !== null) {
            return phone.number || phone.phone_number || phone.phone || JSON.stringify(phone);
        }
        return String(phone);
    }).join(', ');
}

function formatEmails(emails) {
    if (!emails || !Array.isArray(emails) || emails.length === 0) {
        return '—';
    }

    return emails.map(email => {
        if (typeof email === 'string') {
            return email;
        }
        if (typeof email === 'object' && email !== null) {
            return email.email || email.email_address || email.address || JSON.stringify(email);
        }
        return String(email);
    }).join(', ');
}

function formatAddresses(addresses) {
    if (!addresses || !Array.isArray(addresses) || addresses.length === 0) {
        return '—';
    }

    return addresses.map(addr => {
        if (typeof addr === 'string') {
            return addr;
        }
        if (typeof addr === 'object' && addr !== null) {
            // Try to construct full address from object properties
            if (addr.address) {
                return addr.address;
            }
            // Build from components
            const parts = [];
            if (addr.street || addr.street_line_1) parts.push(addr.street || addr.street_line_1);
            if (addr.city) parts.push(addr.city);
            if (addr.state) parts.push(addr.state);
            if (addr.zip || addr.postal_code) parts.push(addr.zip || addr.postal_code);

            if (parts.length > 0) {
                return parts.join(', ');
            }
            return JSON.stringify(addr);
        }
        return String(addr);
    }).join('; ');
}

function showError(message) {
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
}
