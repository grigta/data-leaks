export const COUNTRIES = [
	{ code: 'CA', name: 'Canada' },
	{ code: 'FR', name: 'France' },
	{ code: 'DE', name: 'Germany' },
	{ code: 'UK', name: 'United Kingdom' },
	{ code: 'US', name: 'United States' }
];

export function getCountryName(code: string): string {
	const country = COUNTRIES.find(c => c.code === code);
	return country ? country.name : code;
}
