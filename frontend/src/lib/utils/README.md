# Storage and Persistent Store Utilities

Комплексная система для безопасной работы с localStorage, автоматической синхронизацией между вкладками и graceful degradation.

## Обзор

### Архитектура

```
┌─────────────────────────────────────────┐
│         Application Layer               │
│  (Components, Stores, Business Logic)   │
└─────────────────┬───────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
┌───────▼────────┐  ┌──────▼──────────┐
│ persistent-    │  │  Direct usage   │
│ store.ts       │  │  of storage.ts  │
│ (High-level)   │  │  (Low-level)    │
└───────┬────────┘  └──────┬──────────┘
        │                   │
        └─────────┬─────────┘
                  │
        ┌─────────▼─────────┐
        │   storage.ts      │
        │  (Core utilities) │
        └─────────┬─────────┘
                  │
        ┌─────────▼─────────┐
        │   localStorage    │
        │  BroadcastChannel │
        └───────────────────┘
```

### Модули

**storage.ts** - Низкоуровневые утилиты:
- Безопасные операции с localStorage
- Обработка QuotaExceededError
- TTL (Time To Live) для кэша
- Версионирование и миграции
- JSON сериализация/десериализация

**persistent-store.ts** - Высокоуровневая абстракция:
- Автоматическая синхронизация с localStorage
- BroadcastChannel для cross-tab sync
- Debounced сохранение
- Retry логика
- Graceful degradation

## Quick Start

### Простое использование

```typescript
import { createPersistentStore } from '$lib/utils/persistent-store';

// Создать persistent store
const themeStore = createPersistentStore('dark', {
  key: 'theme',
  broadcastChannel: 'theme-sync'
});

// Использовать как обычный Svelte store
themeStore.set('light');
themeStore.update(theme => theme === 'dark' ? 'light' : 'dark');

// Cleanup в onDestroy
import { onDestroy } from 'svelte';
onDestroy(() => themeStore.destroy());
```

### С кэшированием данных с сервера

```typescript
import { createCachedStore } from '$lib/utils/persistent-store';
import { getCart } from '$lib/api/client';

const cartStore = createCachedStore('cart',
  () => getCart(),
  {
    initialValue: { items: [], total_price: 0 },
    ttl: 5 * 60 * 1000, // 5 минут
    broadcastChannel: 'cart-sync',
    refetchOnFocus: true
  }
);
```

### С версионированием и миграциями

```typescript
type UserV1 = { id: number; name: string };
type UserV2 = UserV1 & { email: string };

const userStore = createPersistentStore<UserV2>(null, {
  key: 'user',
  version: 2,
  migrations: {
    1: (data: UserV1) => ({
      ...data,
      // Добавить новое поле в v2
      email: ''
    })
  },
  ttl: 3600000, // 1 час
  broadcastChannel: 'user-sync'
});
```

## API Reference

### storage.ts

#### Basic Operations

```typescript
// Set value
const success = safeSet('key', 'value');

// Get value
const value = safeGet('key');

// Remove value
safeRemove('key');

// Clear all
safeClear();
```

**Функции:**
- `safeSet(key: string, value: string, options?: StorageOptions): boolean` - Безопасно сохранить значение
- `safeGet(key: string): string | null` - Безопасно получить значение
- `safeRemove(key: string): boolean` - Удалить значение
- `safeClear(): boolean` - Очистить весь localStorage

#### JSON Operations

```typescript
// Set object
safeSetJSON('user', { id: 1, name: 'John' });

// Get object with type safety
const user = safeGetJSON<User>('user');

// With default value
const user = safeGetJSON<User>('user', { id: 0, name: 'Guest' });
```

**Функции:**
- `safeSetJSON<T>(key: string, value: T, options?: StorageOptions): boolean` - Сохранить объект
- `safeGetJSON<T>(key: string, defaultValue?: T): T | null` - Получить объект с типизацией

#### TTL Operations

```typescript
// Set with TTL (5 minutes)
setWithTTL('cache-key', data, 5 * 60 * 1000);

// Get (returns null if expired)
const data = getWithTTL<Data>('cache-key');

// Cleanup expired entries
const removed = cleanupExpired();
```

**Функции:**
- `setWithTTL<T>(key: string, value: T, ttlMs: number): boolean` - Установить значение с TTL
- `getWithTTL<T>(key: string): T | null` - Получить значение, проверить TTL
- `cleanupExpired(): number` - Удалить все истекшие записи

#### Versioned Storage

```typescript
const storage = createVersionedStorage<UserData>('user', 2, {
  1: (data) => ({ ...data, newField: 'default' })
});

storage.set({ id: 1, name: 'John' });
const data = storage.get(); // Автоматическая миграция
```

**Функции:**
- `createVersionedStorage<T>(key: string, currentVersion: number, migrations: Record<number, MigrationFunction<T>>)` - Создать versioned storage

**Возвращаемый объект:**
- `get(): T | null` - Загрузить с автоматической миграцией
- `set(data: T): boolean` - Сохранить с текущей версией
- `remove(): boolean` - Удалить
- `migrate(): boolean` - Принудительная миграция

#### Utility Functions

```typescript
// Get storage size
const size = getStorageSize(); // bytes

// Check availability
const available = isStorageAvailable();

// Get all keys
const keys = getStorageKeys();

// Get keys with prefix
const userKeys = getStorageKeys('user:');

// Get available space
const space = await getAvailableSpace();
```

**Функции:**
- `getStorageSize(): number` - Размер данных в localStorage (bytes)
- `isStorageAvailable(): boolean` - Проверить доступность localStorage
- `getStorageKeys(prefix?: string): string[]` - Получить все ключи
- `getAvailableSpace(): Promise<number | null>` - Доступное место

### persistent-store.ts

#### createPersistentStore

```typescript
const store = createPersistentStore<T>(initialValue, options);
```

**Options:**
- `key: string` - ключ для localStorage (обязательно)
- `ttl?: number` - время жизни кэша в мс
- `broadcastChannel?: string` - имя канала для синхронизации
- `version?: number` - версия схемы данных
- `migrations?: Record<number, MigrationFunction<T>>` - функции миграции
- `onError?: (error: Error) => void` - обработчик ошибок
- `debounceMs?: number` - задержка перед сохранением
- `syncOnInit?: boolean` - синхронизировать при инициализации (default: true)
- `fallbackValue?: T` - значение по умолчанию при ошибках

**Methods:**
- `subscribe(fn)` - подписаться на изменения (Svelte store API)
- `set(value)` - установить значение
- `update(fn)` - обновить значение
- `sync()` - принудительная синхронизация с localStorage
- `clear()` - очистить store и localStorage
- `reset()` - сбросить к fallbackValue
- `destroy()` - cleanup (закрыть BroadcastChannel)
- `isAvailable()` - проверить доступность localStorage

**Пример:**

```typescript
const themeStore = createPersistentStore('dark', {
  key: 'theme',
  broadcastChannel: 'theme-sync',
  debounceMs: 300,
  onError: (error) => console.error('Theme store error:', error)
});

// В компоненте
import { onDestroy } from 'svelte';
onDestroy(() => themeStore.destroy());
```

#### createCachedStore

```typescript
const store = createCachedStore<T>(key, fetchFn, options);
```

**Parameters:**
- `key: string` - ключ для localStorage
- `fetchFn: () => Promise<T>` - функция для загрузки данных
- `options: CachedStoreOptions<T>` - опции

**Additional Options (extends PersistentStoreOptions):**
- `initialValue: T` - начальное значение (обязательно)
- `refetchOnFocus?: boolean` - перезагружать при focus window
- `refetchInterval?: number` - периодическая перезагрузка (мс)
- `retryOnError?: boolean` - повторять при ошибках (default: true)
- `maxRetries?: number` - количество попыток (default: 3)
- `retryDelay?: number` - задержка между попытками (default: 1000ms)

**Пример:**

```typescript
import { getCart } from '$lib/api/client';

const cartStore = createCachedStore('cart',
  () => getCart(),
  {
    initialValue: { items: [], total_price: 0 },
    ttl: 5 * 60 * 1000,
    broadcastChannel: 'cart-sync',
    refetchOnFocus: true,
    refetchInterval: 60000, // Обновлять каждую минуту
    onError: (error) => {
      console.error('Cart fetch error:', error);
      toast.error('Failed to load cart');
    }
  }
);
```

## Migration Guide

### Рефакторинг существующих stores

**До:**
```typescript
import { writable } from 'svelte/store';

const cartStore = writable<CartResponse>({ items: [], total_price: 0 });

// Manual localStorage
function saveCart(cart: CartResponse) {
  try {
    localStorage.setItem('cart', JSON.stringify(cart));
  } catch (error) {
    console.error('Failed to save cart:', error);
  }
}

function loadCart(): CartResponse {
  try {
    const raw = localStorage.getItem('cart');
    if (raw) {
      return JSON.parse(raw);
    }
  } catch (error) {
    console.error('Failed to load cart:', error);
  }
  return { items: [], total_price: 0 };
}

// Manual BroadcastChannel
const channel = new BroadcastChannel('cart-sync');
channel.onmessage = (event) => {
  cartStore.set(event.data);
};

// Manual subscription
cartStore.subscribe(cart => {
  saveCart(cart);
  channel.postMessage(cart);
});

// Manual cleanup needed
export function cleanupCart() {
  channel.close();
}
```

**После:**
```typescript
import { createCachedStore } from '$lib/utils/persistent-store';
import { getCart } from '$lib/api/client';

const cartStore = createCachedStore('cart',
  () => getCart(),
  {
    initialValue: { items: [], total_price: 0 },
    ttl: 5 * 60 * 1000,
    broadcastChannel: 'cart-sync',
    onError: (error) => console.error('Cart error:', error)
  }
);

export { cartStore };

// В компоненте просто:
// onDestroy(() => cartStore.destroy());
```

**Преимущества:**
- ✅ Автоматическая синхронизация с localStorage
- ✅ Встроенная BroadcastChannel синхронизация
- ✅ Обработка ошибок с graceful degradation
- ✅ TTL-based cache invalidation
- ✅ Автоматическая загрузка данных с сервера
- ✅ Retry логика при ошибках
- ✅ Меньше boilerplate кода (с ~50 строк до ~10)
- ✅ Type-safe

### Миграция auth store

**До:**
```typescript
import { writable } from 'svelte/store';

export const authStore = writable<AuthUser | null>(null);

// Много кода для localStorage, BroadcastChannel, error handling...
```

**После:**
```typescript
import { createPersistentStore } from '$lib/utils/persistent-store';

export const authStore = createPersistentStore<AuthUser | null>(null, {
  key: 'auth-user',
  ttl: 24 * 60 * 60 * 1000, // 24 часа
  broadcastChannel: 'auth-sync',
  version: 1,
  onError: (error) => console.error('Auth store error:', error)
});
```

## Best Practices

### 1. Всегда используйте cleanup

```typescript
import { onDestroy } from 'svelte';

const store = createPersistentStore(...);

onDestroy(() => {
  store.destroy();
});
```

**Почему:** Освобождает ресурсы (BroadcastChannel, subscriptions, timers)

### 2. Используйте TTL для кэша

```typescript
// Для часто меняющихся данных - короткий TTL
const ordersStore = createCachedStore('orders', fetchOrders, {
  initialValue: [],
  ttl: 2 * 60 * 1000 // 2 минуты
});

// Для редко меняющихся - длинный TTL
const settingsStore = createPersistentStore(defaultSettings, {
  key: 'settings',
  ttl: 24 * 60 * 60 * 1000 // 24 часа
});
```

**Почему:** Предотвращает использование устаревших данных

### 3. Используйте версионирование для production

```typescript
const userStore = createPersistentStore(null, {
  key: 'user',
  version: 1, // Увеличивайте при изменении схемы
  migrations: {
    // Добавляйте миграции при breaking changes
  }
});
```

**Почему:** Безопасное обновление схемы данных без потери данных пользователей

### 4. Обрабатывайте ошибки

```typescript
const store = createPersistentStore(initialValue, {
  key: 'data',
  onError: (error) => {
    // Логировать в monitoring service
    console.error('Store error:', error);

    // Показать уведомление пользователю
    toast.error('Failed to save data');

    // Отправить в Sentry
    Sentry.captureException(error);
  },
  fallbackValue: defaultValue
});
```

**Почему:** Graceful degradation и visibility проблем

### 5. Используйте debounce для частых обновлений

```typescript
const searchStore = createPersistentStore('', {
  key: 'search-query',
  debounceMs: 500 // Сохранять только после 500ms без изменений
});
```

**Почему:** Уменьшает количество записей в localStorage, улучшает производительность

### 6. Используйте BroadcastChannel для синхронизации

```typescript
const userStore = createPersistentStore(null, {
  key: 'user',
  broadcastChannel: 'user-sync' // Синхронизация между вкладками
});
```

**Почему:** Consistent state между вкладками браузера

### 7. Используйте createCachedStore для server data

```typescript
// ✅ Good - автоматическая загрузка и кэширование
const productsStore = createCachedStore('products',
  () => fetchProducts(),
  {
    initialValue: [],
    ttl: 10 * 60 * 1000,
    refetchOnFocus: true
  }
);

// ❌ Bad - ручная загрузка и кэширование
const productsStore = createPersistentStore([], { key: 'products' });
// Нужно вручную вызывать fetchProducts() и обновлять store
```

## Testing

### Setup

```bash
# Install vitest
pnpm add -D vitest @vitest/ui jsdom

# Run tests
pnpm test

# Run with UI
pnpm test:ui

# Coverage
pnpm test:coverage
```

### Create vitest.config.ts

```typescript
import { defineConfig } from 'vitest/config';
import { sveltekit } from '@sveltejs/kit/vite';

export default defineConfig({
  plugins: [sveltekit()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/lib/utils/__tests__/setup.ts']
  }
});
```

### Add to package.json

```json
{
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage"
  }
}
```

### Example Test

```typescript
import { describe, it, expect } from 'vitest';
import { createPersistentStore } from '$lib/utils/persistent-store';
import { get } from 'svelte/store';

describe('My Store', () => {
  it('should persist data', () => {
    const store = createPersistentStore('initial', {
      key: 'test-key'
    });

    store.set('updated');

    // Create new instance - should load from localStorage
    const store2 = createPersistentStore('initial', {
      key: 'test-key'
    });

    const value = get(store2);
    expect(value).toBe('updated');

    store.destroy();
    store2.destroy();
  });
});
```

## Troubleshooting

### localStorage недоступен

**Проблема:** localStorage может быть недоступен в private mode или при QuotaExceededError

**Решение:** Утилиты автоматически обрабатывают это через graceful degradation:

```typescript
const store = createPersistentStore(initialValue, {
  key: 'data',
  fallbackValue: defaultValue // Используется при недоступном localStorage
});

if (!store.isAvailable()) {
  console.warn('localStorage unavailable, using in-memory only');
  // Показать уведомление пользователю
  toast.warning('Data will not be saved between sessions');
}
```

### Данные не синхронизируются между вкладками

**Проблема:** BroadcastChannel не работает

**Решение:** Проверьте что:
1. Указан `broadcastChannel` в options
2. Имя канала одинаковое для всех stores
3. BroadcastChannel поддерживается браузером (все современные браузеры)

```typescript
// ✅ Правильно - одинаковое имя канала
const store1 = createPersistentStore('data', {
  key: 'key1',
  broadcastChannel: 'sync-channel' // Одинаковое имя
});

const store2 = createPersistentStore('data', {
  key: 'key2',
  broadcastChannel: 'sync-channel' // Одинаковое имя
});

// ❌ Неправильно - разные имена
const store3 = createPersistentStore('data', {
  key: 'key3',
  broadcastChannel: 'different-channel' // Не синхронизируется
});
```

### Миграции не применяются

**Проблема:** Старые данные не мигрируют

**Решение:**
1. Проверьте что version увеличен
2. Проверьте что миграции определены для всех промежуточных версий
3. Используйте `storage.migrate()` для принудительной миграции

```typescript
// Правильная миграция v1 -> v3
const storage = createVersionedStorage('data', 3, {
  1: (data) => ({ ...data, field2: 'default' }), // v1 -> v2
  2: (data) => ({ ...data, field3: 'default' })  // v2 -> v3
});

// ❌ Неправильно - пропущена миграция v1 -> v2
const storage = createVersionedStorage('data', 3, {
  2: (data) => ({ ...data, field3: 'default' }) // Только v2 -> v3
});
```

### QuotaExceededError

**Проблема:** localStorage переполнен (обычно лимит ~5-10MB)

**Решение:** Утилиты автоматически пытаются освободить место:

```typescript
// Автоматический cleanup при QuotaExceededError
const store = createPersistentStore(data, {
  key: 'large-data',
  onError: (error) => {
    if (error.name === 'QuotaExceededError') {
      // Удалить старые данные
      cleanupExpired();

      // Показать уведомление
      toast.warning('Storage is full, old data was removed');
    }
  }
});

// Периодический cleanup
setInterval(() => {
  const removed = cleanupExpired();
  console.log(`Cleaned up ${removed} expired entries`);
}, 60 * 60 * 1000); // Каждый час
```

### Данные теряются после обновления приложения

**Проблема:** Изменилась схема данных, старые данные не совместимы

**Решение:** Используйте версионирование и миграции:

```typescript
// При первом релизе
const store = createPersistentStore(data, {
  key: 'user',
  version: 1
});

// При изменении схемы (добавили email)
const store = createPersistentStore(data, {
  key: 'user',
  version: 2,
  migrations: {
    1: (oldData) => ({
      ...oldData,
      email: '' // Добавить новое поле
    })
  }
});
```

## Performance Tips

### 1. Используйте debounce для частых обновлений

```typescript
// ✅ Good - debounced
const searchStore = createPersistentStore('', {
  key: 'search',
  debounceMs: 300
});

// ❌ Bad - сохраняет при каждом нажатии клавиши
const searchStore = createPersistentStore('', {
  key: 'search'
});
```

### 2. Установите TTL для автоматической очистки

```typescript
const cacheStore = createPersistentStore(data, {
  key: 'api-cache',
  ttl: 5 * 60 * 1000 // Автоматически очистится через 5 минут
});
```

### 3. Используйте cleanupExpired() периодически

```typescript
// В root layout
onMount(() => {
  const interval = setInterval(() => {
    const removed = cleanupExpired();
    if (removed > 0) {
      console.log(`Cleaned up ${removed} expired entries`);
    }
  }, 60 * 60 * 1000); // Каждый час

  return () => clearInterval(interval);
});
```

### 4. Не храните большие объекты в localStorage

```typescript
// ❌ Bad - 5MB+ image в localStorage
const imageStore = createPersistentStore(largeImageBase64, {
  key: 'image'
});

// ✅ Good - храните URL или ID, загружайте при необходимости
const imageIdStore = createPersistentStore(imageId, {
  key: 'image-id'
});
```

### 5. Используйте shallow updates для больших объектов

```typescript
// ❌ Bad - обновляет весь объект
cartStore.update(cart => ({
  ...cart,
  items: [...cart.items, newItem]
}));

// ✅ Better - но всё равно сохраняет весь объект
// Для очень больших объектов рассмотрите использование IndexedDB
```

## Advanced Usage

### Создание custom store с дополнительной логикой

```typescript
import { createPersistentStore } from '$lib/utils/persistent-store';

function createUserStore() {
  const store = createPersistentStore<User | null>(null, {
    key: 'user',
    version: 1,
    broadcastChannel: 'user-sync',
    ttl: 24 * 60 * 60 * 1000
  });

  return {
    subscribe: store.subscribe,

    login: (user: User) => {
      store.set(user);
      // Дополнительная логика
      analytics.track('user_logged_in', { userId: user.id });
    },

    logout: () => {
      store.clear();
      // Дополнительная логика
      analytics.track('user_logged_out');
    },

    updateProfile: (updates: Partial<User>) => {
      store.update(user => user ? { ...user, ...updates } : null);
    },

    destroy: store.destroy
  };
}

export const userStore = createUserStore();
```

### Composite stores с синхронизацией

```typescript
import { derived } from 'svelte/store';

const userStore = createPersistentStore<User | null>(null, {
  key: 'user',
  broadcastChannel: 'user-sync'
});

const settingsStore = createPersistentStore<Settings>(defaultSettings, {
  key: 'settings',
  broadcastChannel: 'settings-sync'
});

// Derived store автоматически обновляется при изменении любого из stores
export const userPreferences = derived(
  [userStore, settingsStore],
  ([$user, $settings]) => ({
    user: $user,
    theme: $settings.theme,
    language: $settings.language
  })
);
```

### Условное сохранение

```typescript
function createConditionalStore<T>(
  initialValue: T,
  shouldPersist: (value: T) => boolean,
  options: PersistentStoreOptions<T>
) {
  const store = writable(initialValue);
  const persistentStore = createPersistentStore(initialValue, options);

  store.subscribe(value => {
    if (shouldPersist(value)) {
      persistentStore.set(value);
    }
  });

  return {
    subscribe: store.subscribe,
    set: store.set,
    update: store.update,
    destroy: persistentStore.destroy
  };
}

// Пример: сохранять только валидные данные
const formStore = createConditionalStore(
  initialFormData,
  (data) => isValid(data),
  { key: 'form-data' }
);
```

## Common Patterns

### Аутентификация

```typescript
import { createPersistentStore } from '$lib/utils/persistent-store';

export const authStore = createPersistentStore<AuthState>({
  user: null,
  token: null
}, {
  key: 'auth',
  version: 1,
  ttl: 24 * 60 * 60 * 1000,
  broadcastChannel: 'auth-sync',
  onError: (error) => {
    console.error('Auth store error:', error);
    // Logout при критических ошибках
    authStore.clear();
  }
});
```

### Корзина покупок

```typescript
import { createCachedStore } from '$lib/utils/persistent-store';

export const cartStore = createCachedStore('cart',
  async () => {
    const response = await fetch('/api/cart');
    return response.json();
  },
  {
    initialValue: { items: [], total: 0 },
    ttl: 5 * 60 * 1000,
    broadcastChannel: 'cart-sync',
    refetchOnFocus: true,
    refetchInterval: 60000
  }
);
```

### Настройки UI

```typescript
import { createPersistentStore } from '$lib/utils/persistent-store';

export const uiStore = createPersistentStore({
  theme: 'dark',
  sidebarCollapsed: false,
  language: 'en'
}, {
  key: 'ui-settings',
  version: 1,
  broadcastChannel: 'ui-sync'
});
```

### Форма с автосохранением

```typescript
import { createPersistentStore } from '$lib/utils/persistent-store';

export const formDraftStore = createPersistentStore({
  title: '',
  content: '',
  tags: []
}, {
  key: 'form-draft',
  debounceMs: 1000, // Автосохранение через 1 секунду после последнего изменения
  ttl: 7 * 24 * 60 * 60 * 1000 // 7 дней
});
```

## License

MIT

---

**Документация создана для проекта SSN Management System**

Для вопросов и предложений создайте issue в репозитории проекта.
