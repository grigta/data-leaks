/**
 * Animation duration constants in milliseconds
 */
export const ANIMATION_DURATIONS = {
	/** Fast animations for micro-interactions (hover, focus) */
	fast: 150,
	/** Normal speed for standard transitions (fade, slide) */
	normal: 200,
	/** Slow animations for more noticeable transitions (page transitions) */
	slow: 300,
	/** Slower animations for accent states (success, completion) */
	slower: 500
} as const;

/**
 * Standard easing functions for smooth animations
 */
export const ANIMATION_EASINGS = {
	/** Smooth acceleration and deceleration */
	easeInOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
	/** Smooth deceleration */
	easeOut: 'cubic-bezier(0, 0, 0.2, 1)',
	/** Smooth acceleration */
	easeIn: 'cubic-bezier(0.4, 0, 1, 1)'
} as const;
