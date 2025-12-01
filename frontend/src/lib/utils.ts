import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes intelligently, resolving conflicts
 * @param inputs - Class values to merge
 * @returns Merged class string
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format number as USD currency
 * @param amount - Numeric amount
 * @returns Formatted currency string (e.g., "$1,234.56")
 */
export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

/**
 * Format date in readable format
 * @param date - Date string or Date object
 * @returns Formatted date string (e.g., "Jan 15, 2024")
 */
export function formatDate(date: string | Date): string {
  if (!date) return '';

  let dateObj: Date;

  if (typeof date === 'string') {
    // Handle YYYYMMDD format (e.g., "19420409")
    if (/^\d{8}$/.test(date)) {
      const year = date.substring(0, 4);
      const month = date.substring(4, 6);
      const day = date.substring(6, 8);
      dateObj = new Date(`${year}-${month}-${day}`);
    } else {
      dateObj = new Date(date);
    }
  } else {
    dateObj = date;
  }

  // Check if date is valid
  if (isNaN(dateObj.getTime())) {
    return date.toString(); // Return original if invalid
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(dateObj);
}

/**
 * Format date with time in readable format
 * @param date - Date string or Date object
 * @returns Formatted date and time string (e.g., "Jan 15, 2024 at 10:30 AM")
 */
export function formatDateTime(date: string | Date): string {
  const dateObj = typeof date === 'string' ? new Date(date) : date;
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(dateObj);
}

/**
 * Mask SSN showing only last 4 digits
 * @param ssn - Social Security Number
 * @returns Masked SSN (e.g., "***-**-6789")
 */
export function maskSSN(ssn: string): string {
  if (!ssn) return '';

  // Remove any existing formatting
  const cleanSSN = ssn.replace(/\D/g, '');

  if (cleanSSN.length !== 9) {
    return ssn; // Return as-is if not valid format
  }

  // Show only last 4 digits
  return `***-**-${cleanSSN.slice(-4)}`;
}

/**
 * Format SSN with proper dashes
 * @param ssn - Social Security Number
 * @returns Formatted SSN (e.g., "123-45-6789")
 */
export function formatSSN(ssn: string): string {
  if (!ssn) return '';

  // Remove any existing formatting
  const cleanSSN = ssn.replace(/\D/g, '');

  if (cleanSSN.length <= 3) {
    return cleanSSN;
  } else if (cleanSSN.length <= 5) {
    return `${cleanSSN.slice(0, 3)}-${cleanSSN.slice(3)}`;
  } else if (cleanSSN.length <= 9) {
    return `${cleanSSN.slice(0, 3)}-${cleanSSN.slice(3, 5)}-${cleanSSN.slice(5)}`;
  }

  // Format as XXX-XX-XXXX for full SSN
  return `${cleanSSN.slice(0, 3)}-${cleanSSN.slice(3, 5)}-${cleanSSN.slice(5, 9)}`;
}

/**
 * Format phone number as (XXX) XXX-XXXX
 * @param phone - Phone number
 * @returns Formatted phone (e.g., "(123) 456-7890")
 */
export function formatPhone(phone: string): string {
  if (!phone) return '';

  // Remove any existing formatting
  const cleanPhone = phone.replace(/\D/g, '');

  if (cleanPhone.length !== 10) {
    return phone; // Return as-is if not valid format
  }

  // Format as (XXX) XXX-XXXX
  return `(${cleanPhone.slice(0, 3)}) ${cleanPhone.slice(3, 6)}-${cleanPhone.slice(6)}`;
}

/**
 * Clean phone number removing all non-digit characters
 * @param phone - Phone number
 * @returns Clean phone number (e.g., "1234567890")
 */
export function cleanPhone(phone: string): string {
  if (!phone) return '';
  return phone.replace(/\D/g, '');
}

/**
 * Truncate text with ellipsis
 * @param text - Text to truncate
 * @param maxLength - Maximum length before truncation
 * @returns Truncated text with ellipsis if needed
 */
export function truncate(text: string, maxLength: number): string {
  if (!text || text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

/**
 * Get Tailwind CSS classes for order status badge
 * @param status - Order status (pending, completed, failed, cancelled)
 * @returns Tailwind CSS classes for badge styling
 */
export function getStatusBadgeClass(status: string): string {
  switch (status.toLowerCase()) {
    case 'pending':
      return 'bg-yellow-100 text-yellow-800 hover:bg-yellow-100';
    case 'completed':
      return 'bg-green-100 text-green-800 hover:bg-green-100';
    case 'failed':
      return 'bg-red-100 text-red-800 hover:bg-red-100';
    case 'cancelled':
      return 'bg-gray-100 text-gray-800 hover:bg-gray-100';
    default:
      return 'bg-gray-100 text-gray-800 hover:bg-gray-100';
  }
}

/**
 * Get icon name for order status
 * @param status - Order status (pending, completed, failed, cancelled)
 * @returns Icon name to be used with Lucide icons
 */
export function getStatusIconName(status: string): string {
  switch (status.toLowerCase()) {
    case 'pending':
      return 'clock';
    case 'completed':
      return 'check-circle';
    case 'failed':
      return 'x-circle';
    case 'cancelled':
      return 'ban';
    default:
      return '';
  }
}

/**
 * Mask date of birth showing only year
 * @param dob - Date of birth in YYYYMMDD format (e.g., "19750122")
 * @returns Masked DOB (e.g., "xx-xx-1975")
 */
export function maskDOB(dob: string): string {
  if (!dob) return '';

  // Handle YYYYMMDD format (e.g., "19750122")
  if (/^\d{8}$/.test(dob)) {
    const year = dob.substring(0, 4);
    return `xx-xx-${year}`;
  }

  return dob; // Return as-is if not valid format
}

/**
 * Format date of birth in ISO format (YYYY-MM-DD)
 * @param dob - Date of birth in YYYYMMDD format (e.g., "19750122")
 * @returns Formatted DOB in ISO format (e.g., "1975-01-22")
 */
export function formatDOBISO(dob: string): string {
  if (!dob) return '';

  // Handle YYYYMMDD format (e.g., "19750122")
  if (/^\d{8}$/.test(dob)) {
    const year = dob.substring(0, 4);
    const month = dob.substring(4, 6);
    const day = dob.substring(6, 8);
    return `${year}-${month}-${day}`;
  }

  return dob; // Return as-is if not valid format
}

/**
 * Parse full name into firstname and lastname
 *
 * Logic:
 * - First word = firstname
 * - Last word = lastname
 * - All middle words are ignored (middle names are excluded)
 * - Removes common prefixes (Mr., Mrs., Ms., Dr., Prof., Miss)
 * - Removes common suffixes (Jr., Sr., II, III, IV, V, Esq.)
 * - Normalizes whitespace and capitalizes words
 *
 * Examples:
 * - "John Doe" → {firstname: "John", lastname: "Doe"}
 * - "John Michael Doe" → {firstname: "John", lastname: "Doe"} (Michael ignored)
 * - "Mr. John Doe Jr." → {firstname: "John", lastname: "Doe"}
 * - "Doe John" → {firstname: "Doe", lastname: "John"}
 * - "John" → {firstname: "John", lastname: ""} (single word)
 * - "" → {firstname: "", lastname: ""} (empty)
 *
 * @param fullName - Full name string
 * @returns Object with firstname and lastname
 */
export function parseFullName(fullName: string): { firstname: string; lastname: string } {
  if (!fullName || typeof fullName !== 'string') {
    return { firstname: '', lastname: '' };
  }

  // Trim and normalize whitespace
  const normalized = fullName.trim().replace(/\s+/g, ' ');

  if (!normalized) {
    return { firstname: '', lastname: '' };
  }

  // Remove common prefixes and suffixes
  const prefixes = ['mr.', 'mrs.', 'ms.', 'dr.', 'prof.', 'miss'];
  const suffixes = ['jr.', 'jr', 'sr.', 'sr', 'ii', 'iii', 'iv', 'v', 'esq.', 'esq'];

  let cleaned = normalized.toLowerCase();

  // Remove prefixes
  for (const prefix of prefixes) {
    if (cleaned.startsWith(prefix + ' ')) {
      cleaned = cleaned.substring(prefix.length + 1).trim();
    }
  }

  // Remove suffixes
  for (const suffix of suffixes) {
    if (cleaned.endsWith(' ' + suffix)) {
      cleaned = cleaned.substring(0, cleaned.length - suffix.length - 1).trim();
    }
  }

  // Additional safety check
  if (!cleaned || typeof cleaned !== 'string') {
    return { firstname: '', lastname: '' };
  }

  // Split by space
  const words = cleaned.split(' ');

  if (words.length === 0) {
    return { firstname: '', lastname: '' };
  }

  if (words.length === 1) {
    // Single word - treat as firstname only
    return {
      firstname: capitalizeWord(words[0]),
      lastname: ''
    };
  }

  // First word = firstname, Last word = lastname, middle words ignored
  const firstname = words[0];
  const lastname = words[words.length - 1];

  return {
    firstname: capitalizeWord(firstname),
    lastname: capitalizeWord(lastname)
  };
}

/**
 * Capitalize first letter of a word
 * @param word - Word to capitalize
 * @returns Capitalized word
 */
function capitalizeWord(word: string): string {
  if (!word) return '';
  return word.charAt(0).toUpperCase() + word.slice(1);
}
