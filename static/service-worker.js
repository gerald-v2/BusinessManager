/*
 * BizManager PWA cache.
 *
 * Cache only pages explicitly needed for offline shop operations. Cached pages
 * are a local snapshot; all mutations must be saved to IndexedDB by the page's
 * offline logic and synced when connectivity returns.
 */
const CACHE_NAME = "bizmanager-offline-v2";
const CORE_FILES = [
  "/static/style.css",
  "/static/offline-sync.js",
  "/static/receipt-printer.js",
  "/static/manifest.json",
  "/static/icon-192.png",
  "/static/icon-512.png",
  "/static/attendance-sync.json"
];
const CDN_ASSETS = [
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css",
  "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js",
  "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css"
];
const CDN_HOSTS = ["cdn.jsdelivr.net", "fonts.googleapis.com", "fonts.gstatic.com"];

function isOfflineModulePath(path) {
  return /^\/biz\/[^/]+\/(?:pos|products(?:\/[^/]+)?|employees|crm|attendance\/quick)\/?$/.test(path) ||
         /^\/biz\/[^/]+\/?$/.test(path);
}

function offlinePage() {
  return caches.open(CACHE_NAME).then(cache => cache.keys()).then(keys => {
    const links = keys.map(req => new URL(req.url)).filter(url =>
      url.origin === self.location.origin && isOfflineModulePath(url.pathname)
    );
    const unique = new Map();
    links.forEach(url => unique.set(url.pathname, url.pathname));
    const entries = Array.from(unique.values()).sort().map(path => {
      const label = path.match(/\/pos\/?$/) ? "Point of Sale" :
        path.match(/\/products(?:\/[^/]+)?\/?$/) ? "Products" :
        path.match(/\/employees\/?$/) ? "Employees" :
        path.match(/\/crm\/?$/) ? "Customers / CRM" :
        path.match(/\/attendance\/quick\/?$/) ? "Quick Clock" : "Business Dashboard";
      return '<a style="display:block;padding:14px;margin:10px 0;border:1px solid #ddd;border-radius:10px;color:#0d6efd;text-decoration:none" href="' +
        path.replace(/&/g, "&amp;").replace(/"/g, "&quot;") + '">' + label + '</a>';
    }).join("");
    const message = entries || '<p>Connect to the internet once, sign in, and visit POS, Products and Employees so BizManager can save them on this device.</p>';
    return new Response(
      '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0d6efd"><title>BizManager Offline</title><style>body{font:16px system-ui,sans-serif;max-width:560px;margin:35px auto;padding:0 18px;color:#222}h1{color:#0d6efd}small{color:#666}</style></head><body><h1>BizManager</h1><p><strong>You are offline.</strong> Open a saved module below. Cached pages show the last data saved on this device.</p>' +
      message + '<small>New changes must be stored locally by the module and sync when the internet returns. Keep this device secure.</small></body></html>',
      { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } }
    );
  });
}

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache =>
    Promise.all(CORE_FILES.concat(CDN_ASSETS).map(url =>
      cache.add(url).catch(() => null)
    ))
  ));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(names => Promise.all(
    names.filter(name => name.startsWith("bizmanager-") && name !== CACHE_NAME)
      .map(name => caches.delete(name))
  )));
  self.clients.claim();
});

async function store(request, response) {
  if (response && response.ok && response.type !== "opaque") {
    try {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    } catch (error) {
      // Cache quota or storage failures must not break the online page.
    }
  }
  return response;
}

function cacheFirst(request) {
  return caches.match(request).then(hit => hit || fetch(request).then(response => store(request, response)));
}

function networkFirst(request, cachePage) {
  return fetch(request).then(async response => {
    if (cachePage && response.ok && response.type === "basic") await store(request, response);
    return response;
  }).catch(async () => {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    if (request.mode === "navigate") return offlinePage();
    return Response.error();
  });
}

self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);

  if (CDN_HOSTS.includes(url.hostname)) {
    event.respondWith(cacheFirst(request));
    return;
  }
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/static/")) {
    event.respondWith(networkFirst(request, true));
    return;
  }

  // Never cache login, logout, password reset, or admin pages.
  if (/\/(?:business-login|admin\/login|logout|forgot-password|reset-password)(?:\/|$)/.test(url.pathname)) {
    if (url.pathname === "/logout") {
      event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.keys()).then(keys =>
        Promise.all(keys.filter(key => isOfflineModulePath(new URL(key.url).pathname))
          .map(key => caches.delete(key)))
      ));
    }
    return;
  }

  // Cache only the operational pages required for offline use.
  const cachePage = request.mode === "navigate" && isOfflineModulePath(url.pathname);
  if (cachePage || request.mode === "navigate") {
    event.respondWith(networkFirst(request, cachePage));
  }
});
