import { browser } from '$app/environment';

/**
 * Set a cookie from the client side
 */
export function setCookie(name: string, value: string, days: number = 7) {
	if (!browser) return;

	const expires = new Date();
	expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);

	document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
}

/**
 * Delete a cookie from the client side
 */
export function deleteCookie(name: string) {
	if (!browser) return;

	document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/;`;
}

/**
 * Get a cookie value from the client side
 */
export function getCookie(name: string): string | null {
	if (!browser) return null;

	const nameEQ = name + '=';
	const ca = document.cookie.split(';');

	for (let i = 0; i < ca.length; i++) {
		let c = ca[i];
		while (c.charAt(0) === ' ') c = c.substring(1, c.length);
		if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
	}

	return null;
}
