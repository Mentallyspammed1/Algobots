
const cache = new Map<string, { value: any; expiry: number }>();

export function withCache<T extends (...args: any[]) => any>(
  fn: T,
  options: { ttl: number; getKey?: (...args: Parameters<T>) => string } = { ttl: 60 * 1000 }
): (...args: Parameters<T>) => Promise<ReturnType<T>> {
  return async function (...args: Parameters<T>): Promise<ReturnType<T>> {
    const key = options.getKey ? options.getKey(...args) : JSON.stringify({ name: fn.name, args });
    const now = Date.now();

    const cached = cache.get(key);
    if (cached && now < cached.expiry) {
      return cached.value;
    }

    const result = await fn(...args);
    cache.set(key, { value: result, expiry: now + options.ttl });

    return result;
  };
}
