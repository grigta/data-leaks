import { browser } from '$app/environment';
import { writable, derived } from 'svelte/store';

// WebSocket Event Types
export interface WebSocketEvent {
	event_type: string;
	data: any;
	timestamp: string;
}

// Event type constants
export const TICKET_CREATED = 'ticket_created';
export const TICKET_UPDATED = 'ticket_updated';
export const WORKER_REQUEST_CREATED = 'worker_request_created';
export const WORKER_REQUEST_APPROVED = 'worker_request_approved';
export const WORKER_REQUEST_REJECTED = 'worker_request_rejected';
export const SUPPORT_MESSAGE_CREATED = 'support_message_created';
export const SUPPORT_MESSAGE_ANSWERED = 'support_message_answered';
export const CONTACT_MESSAGE_CREATED = 'contact_message_created';
export const CONTACT_MESSAGE_ANSWERED = 'contact_message_answered';
export const STATS_UPDATED = 'stats_updated';
export const WORKER_INVOICE_CREATED = 'worker_invoice_created';
export const WORKER_SHIFT_UPDATED = 'worker_shift_updated';

// Thread-based Support event constants
export const THREAD_CREATED = 'thread_created';
export const THREAD_MESSAGE_ADDED = 'thread_message_added';
export const THREAD_STATUS_UPDATED = 'thread_status_updated';
export const THREAD_MESSAGES_READ = 'thread_messages_read';

// Thread-based Contact event constants
export const CONTACT_THREAD_CREATED = 'contact_thread_created';
export const CONTACT_THREAD_MESSAGE_ADDED = 'contact_thread_message_added';
export const CONTACT_THREAD_STATUS_UPDATED = 'contact_thread_status_updated';
export const CONTACT_THREAD_MESSAGES_READ = 'contact_thread_messages_read';

// WebSocket Manager Class
class WebSocketManager {
	ws: WebSocket | null = null;
	reconnectAttempts: number = 0;
	maxReconnectAttempts: number = 5;
	reconnectDelay: number = 3000;
	isConnected: boolean = false;
	eventHandlers: Map<string, Set<Function>> = new Map();
	reconnectTimer: ReturnType<typeof setTimeout> | null = null;

	/**
	 * Establish WebSocket connection
	 */
	connect(token: string): void {
		if (!browser) {
			console.warn('WebSocket can only be initialized in browser environment');
			return;
		}

		// Close existing connection if any
		if (this.ws) {
			this.disconnect();
		}

		try {
			// Construct WebSocket URL
			const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
			const wsUrl = `${protocol}//${window.location.host}/api/admin/ws?token=${token}`;

			console.log('Connecting to WebSocket:', wsUrl);
			this.ws = new WebSocket(wsUrl);

			// On connection open
			this.ws.onopen = () => {
				console.log('WebSocket connected');
				this.isConnected = true;
				this.reconnectAttempts = 0;
				connectionStatus.set(true);

				// Clear reconnection timer if any
				if (this.reconnectTimer) {
					clearTimeout(this.reconnectTimer);
					this.reconnectTimer = null;
				}
			};

			// On message received
			this.ws.onmessage = (event) => {
				try {
					const data = JSON.parse(event.data);
					console.log('WebSocket message received:', data);

					if (data.event_type) {
						this.emit(data.event_type, data.data);
					}
				} catch (error) {
					console.error('Failed to parse WebSocket message:', error);
				}
			};

			// On error
			this.ws.onerror = (error) => {
				console.error('WebSocket error:', error);
			};

			// On connection close
			this.ws.onclose = (event) => {
				console.log('WebSocket disconnected:', event.code, event.reason);
				this.isConnected = false;
				connectionStatus.set(false);

				// Attempt reconnection if not manual disconnect
				if (this.reconnectAttempts < this.maxReconnectAttempts && !event.wasClean) {
					this.reconnect(token);
				}
			};
		} catch (error) {
			console.error('Failed to create WebSocket connection:', error);
		}
	}

	/**
	 * Disconnect WebSocket gracefully
	 */
	disconnect(): void {
		if (this.ws) {
			this.ws.close(1000, 'Client disconnect');
			this.ws = null;
		}

		this.isConnected = false;
		this.eventHandlers.clear();
		connectionStatus.set(false);

		// Clear reconnection timer if any
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}
	}

	/**
	 * Register event handler for specific event type
	 */
	on(eventType: string, handler: Function): () => void {
		if (!this.eventHandlers.has(eventType)) {
			this.eventHandlers.set(eventType, new Set());
		}

		this.eventHandlers.get(eventType)!.add(handler);

		// Return unsubscribe function
		return () => {
			this.off(eventType, handler);
		};
	}

	/**
	 * Unregister event handler for specific event type
	 */
	off(eventType: string, handler: Function): void {
		if (this.eventHandlers.has(eventType)) {
			this.eventHandlers.get(eventType)!.delete(handler);
		}
	}

	/**
	 * Dispatch event to all registered handlers for that event type
	 */
	emit(eventType: string, data: any): void {
		if (this.eventHandlers.has(eventType)) {
			this.eventHandlers.get(eventType)!.forEach((handler) => {
				try {
					handler(data);
				} catch (error) {
					console.error(`Error in event handler for ${eventType}:`, error);
				}
			});
		}
	}

	/**
	 * Attempt to reconnect with exponential backoff
	 */
	reconnect(token: string): void {
		this.reconnectAttempts++;
		const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

		console.log(
			`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${delay}ms...`
		);

		this.reconnectTimer = setTimeout(() => {
			this.connect(token);
		}, delay);
	}

	/**
	 * Get current connection status
	 */
	getConnectionStatus(): boolean {
		return this.isConnected;
	}
}

// Singleton instance
export const wsManager = new WebSocketManager();

// Svelte Store Integration
export const connectionStatus = writable(false);
export const isConnected = derived(connectionStatus, ($status) => $status);
