// BizManager Service Worker — caches the POS shell so it opens with no internet,
// and lets offline-sync.js handle queuing/replaying actual sales.

const CACHE_NAME = 'bizmanager-v1';

// Add any other static assets you want guaranteed offline here.
const CORE_ASSETS = [
  '/static/style.css',
  '/static/offline-sync.js',
  '/static/manifest.json',
  '/static/offline.html',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n)))
    )
  );
  self.clients.claim();
});

// Network-first for pages, falling back to cache when offline.
// POS pages get cached after a successful load so they're available offline next time.
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Never intercept POST/PUT/DELETE — those go through offline-sync.js's own queue.
  if (event.request.method !== 'GET') return;

  // Don't cache the sync endpoint itself.
  if (url.pathname.startsWith('/api/sync')) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache a copy of successful GETs to /biz/.../pos pages for offline use.
        if (response.ok && url.pathname.includes('/pos')) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() =>
        caches.match(event.request).then((cached) => {
          if (cached) return cached;
          // Page was never visited before and we're offline — show fallback,
          // but only for actual page navigations, not for assets like images/JS.
          if (event.request.mode === 'navigate') {
            return caches.match('/static/offline.html');
          }
          return new Response('', { status: 504 });
        })
      )
  );
});
