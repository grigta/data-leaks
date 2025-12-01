/**
 * NEW PRICING MODEL:
 * SSN record price is now determined by enrichment result:
 * - $3.50 if enrichment succeeds (data updated)
 * - $3.00 if enrichment fails (no changes found)
 *
 * The price is only known AFTER enrichment attempt.
 */
export const ENRICHMENT_FAILURE_COST = 3.00;
export const ENRICHMENT_SUCCESS_COST = 3.50;

/**
 * Default price shown before enrichment (average of success/failure)
 */
export const DEFAULT_RECORD_PRICE = 3.25;

/**
 * Manual SSN ticket cost
 */
export const MANUAL_SSN_COST = 3.00;

/**
 * @deprecated Use ENRICHMENT_FAILURE_COST or ENRICHMENT_SUCCESS_COST instead
 */
export const ENRICHMENT_COST = 3.00;

/**
 * @deprecated Table-specific pricing removed. All records now priced by enrichment result.
 */
export const PRICE_BY_TABLE: Record<string, number> = {
	ssn_1: DEFAULT_RECORD_PRICE,
	ssn_2: DEFAULT_RECORD_PRICE
};

/**
 * Returns default price (before enrichment).
 * Actual price will be determined after enrichment attempt.
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

/**
 * Returns the appropriate enrichment cost based on success status
 * @param success - Whether enrichment was successful
 * @returns Enrichment cost
 */
export function getEnrichmentCost(success: boolean): number {
	return success ? ENRICHMENT_SUCCESS_COST : ENRICHMENT_FAILURE_COST;
}
