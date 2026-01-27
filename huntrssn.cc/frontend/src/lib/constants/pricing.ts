/**
 * Manual SSN ticket cost
 */
export const MANUAL_SSN_COST = 3.00;

/**
 * Default SSN record price
 */
export const DEFAULT_RECORD_PRICE = 3.00;

/**
 * Table-specific pricing
 */
export const PRICE_BY_TABLE: Record<string, number> = {
	ssn_1: DEFAULT_RECORD_PRICE,
	ssn_2: DEFAULT_RECORD_PRICE
};

/**
 * Returns price for SSN record
 */
export function getRecordPrice(source_table?: string): number {
	return DEFAULT_RECORD_PRICE;
}

export function getRecordPriceOrNull(source_table?: string): number | null {
	if (source_table && source_table in PRICE_BY_TABLE) {
		return PRICE_BY_TABLE[source_table];
	}
	return null;
}
