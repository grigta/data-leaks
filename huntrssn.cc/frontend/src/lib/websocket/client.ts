import { browser, dev } from '$app/environment';
import { writable } from 'svelte/store';

// WebSocket Event Types
export interface WebSocketMessage {
  event_type: string;
  data: any;
  timestamp: string;
}

// Event type constants
export const TICKET_CREATED = 'ticket_created';
export const TICKET_UPDATED = 'ticket_updated';
export const TICKET_COMPLETED = 'ticket_completed';
export const WORKER_REQUEST_CREATED = 'worker_request_created';
export const WORKER_REQUEST_APPROVED = 'worker_request_approved';
export const SUPPORT_MESSAGE_CREATED = 'support_message_created';
export const SUPPORT_MESSAGE_ANSWERED = 'support_message_answered';
export const CONTACT_MESSAGE_CREATED = 'contact_message_created';
export const CONTACT_MESSAGE_ANSWERED = 'contact_message_answered';

// Balance events
export const BALANCE_UPDATED = 'balance_updated';

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
export class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 5;
  private reconnectDelay: number = 3000;
  private reconnectTimer: number | null = null;
  private isConnected: boolean = false;
  private eventHandlers: Map<string, Set<Function>> = new Map();
  private token: string | null = null;
  private endpoint: string = '/api/public/ws';

  /**
   * Establish WebSocket connection
   * @param token - JWT token for authentication
   * @param endpoint - WebSocket endpoint path (default: '/api/public/ws' for regular users)
   */
  connect(token: string, endpoint: string = '/api/public/ws'): void {
    if (!browser) {
      console.warn('WebSocket can only be initialized in browser environment');
      return;
    }

    this.token = token;
    this.endpoint = endpoint;

    // Determine WebSocket protocol based on current protocol
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}${endpoint}?token=${encodeURIComponent(token)}`;

    dev && console.log('[WebSocket] Connecting to:', wsUrl);

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        dev && console.log('[WebSocket] Connection established');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        wsConnected.set(true);
        wsError.set(null);
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          dev && console.log('[WebSocket] Message received:', message);

          // Validate message structure
          if (message.event_type && message.data !== undefined) {
            this.emit(message.event_type, message.data);
          } else {
            console.warn('[WebSocket] Invalid message format');
          }
        } catch (error) {
          console.error('[WebSocket] Error parsing message');
        }
      };

      this.ws.onerror = () => {
        console.error('[WebSocket] Connection error');
        wsError.set('WebSocket connection error');
      };

      this.ws.onclose = (event) => {
        dev && console.log('[WebSocket] Connection closed:', event.code, event.reason);
        this.isConnected = false;
        wsConnected.set(false);

        // Attempt reconnection if not a normal closure and attempts remain
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnect();
        } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          console.error('[WebSocket] Max reconnection attempts reached');
          wsError.set('Failed to reconnect after multiple attempts');
        }
      };
    } catch (error) {
      console.error('[WebSocket] Connection failed');
      wsError.set('Failed to establish WebSocket connection');
    }
  }

  /**
   * Close WebSocket connection gracefully
   */
  disconnect(): void {
    dev && console.log('[WebSocket] Disconnecting...');

    // Clear reconnection timer
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    // Close connection
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    // Clear state
    this.isConnected = false;
    this.eventHandlers.clear();
    wsConnected.set(false);
    wsError.set(null);
  }

  /**
   * Register event handler for specific event type
   * @param eventType - The event type to listen for
   * @param handler - The handler function to call when event occurs
   * @returns Unsubscribe function
   */
  on(eventType: string, handler: (data: any) => void): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }

    this.eventHandlers.get(eventType)!.add(handler);
    dev && console.log(`[WebSocket] Event handler registered for: ${eventType}`);

    // Return unsubscribe function
    return () => {
      this.off(eventType, handler);
    };
  }

  /**
   * Unregister specific event handler
   * @param eventType - The event type
   * @param handler - The handler function to remove
   */
  off(eventType: string, handler: Function): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      handlers.delete(handler);
      dev && console.log(`[WebSocket] Event handler unregistered for: ${eventType}`);

      // Clean up empty sets
      if (handlers.size === 0) {
        this.eventHandlers.delete(eventType);
      }
    }
  }

  /**
   * Dispatch event to all registered handlers
   * @param eventType - The event type
   * @param data - The event data
   */
  private emit(eventType: string, data: any): void {
    const handlers = this.eventHandlers.get(eventType);
    if (handlers) {
      handlers.forEach((handler) => {
        try {
          handler(data);
        } catch (error) {
          console.error(`[WebSocket] Error in event handler for ${eventType}`);
        }
      });
    }
  }

  /**
   * Reconnect with exponential backoff
   */
  private reconnect(): void {
    if (!this.token) {
      console.error('[WebSocket] Cannot reconnect: no token available');
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WebSocket] Max reconnection attempts reached');
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;

    dev && console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    this.reconnectTimer = window.setTimeout(() => {
      dev && console.log('[WebSocket] Attempting to reconnect...');
      this.connect(this.token!, this.endpoint);
    }, delay);
  }

  /**
   * Get current connection status
   * @returns True if connected, false otherwise
   */
  getConnectionStatus(): boolean {
    return this.isConnected;
  }
}

// Singleton instance
export const wsManager = new WebSocketManager();

// Reactive stores
export const wsConnected = writable<boolean>(false);
export const wsError = writable<string | null>(null);
