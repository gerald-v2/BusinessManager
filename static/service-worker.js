// BizManager service worker - keeps the POS usable without internet.
//
//  * CDN files the pages need (Bootstrap, icons, fonts) are cached so the
//    checkout window and styling still work offline.
//  * Our own /static files and the POS page are served from cache when the
//    network is down.  Open the POS screen once while online on each device.
//  * Everything else (sales, saving data) always goes to the network.

const CACHE_NAME = "bizmanager-v3";

const CORE_FILES = [
    "/static/style.css",
    "/static/offline-sync.js",
    "/static/receipt-printer.js",
    "/static/manifest.json"
];

const CDN_ASSETS = [
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css",
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js",
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css"
];

const CDN_HOSTS = [
    "cdn.jsdelivr.net",
    "fonts.googleapis.com",
    "fonts.gstatic.com"
];

const OFFLINE_PAGE =
    "<!DOCTYPE html><html><head><meta charset=\"utf-8\">" +
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">" +
    "<title>BizManager Offline</title></head>" +
    "<body style=\"font-family:sans-serif;text-align:center;padding:50px\">" +
    "<h2>BizManager is offline</h2>" +
    "<p>Your saved sales are safe on this device.</p>" +
    "<p>Open the POS screen once while online so it can work offline, " +
    "then reconnect to sync.</p></body></html>";


// ------------------------------------------------------------
// INSTALL
// ------------------------------------------------------------

self.addEventListener("install", event => {

    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {

            // One missing file must never stop the worker installing.
            const all = CORE_FILES.concat(CDN_ASSETS).map(url =>
                cache.add(url).catch(() => null)
            );
            return Promise.all(all);
        })
    );

    self.skipWaiting();
});


// ------------------------------------------------------------
// ACTIVATE
// ------------------------------------------------------------

self.addEventListener("activate", event => {

    event.waitUntil(
        caches.keys().then(names =>
            Promise.all(
                names
                    .filter(name => name !== CACHE_NAME)
                    .map(name => caches.delete(name))
            )
        )
    );

    self.clients.claim();
});


// ------------------------------------------------------------
// HELPERS
// ------------------------------------------------------------

function store(request, response) {
    if (response && (response.ok || response.type === "opaque")) {
        const copy = response.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, copy)).catch(() => null);
    }
    return response;
}

function cacheFirst(request) {
    return caches.match(request).then(hit => {
        if (hit) {
            return hit;
        }
        return fetch(request).then(response => store(request, response));
    });
}

function networkFirst(request, shouldStore) {
    return fetch(request)
        .then(response => (shouldStore ? store(request, response) : response))
        .catch(() =>
            caches.match(request).then(cached => {

                if (cached) {
                    return cached;
                }

                if (request.mode === "navigate") {
                    return new Response(OFFLINE_PAGE, {
                        headers: { "Content-Type": "text/html" }
                    });
                }

                // Scripts / styles we do not have: fail cleanly instead of
                // returning an HTML page where JavaScript was expected.
                return Response.error();
            })
        );
}


// ------------------------------------------------------------
// FETCH
// ------------------------------------------------------------

self.addEventListener("fetch", event => {

    const request = event.request;

    // Only GET requests. Sales and saves are POSTs and go straight to the server.
    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);

    // Bootstrap, icons, fonts: version-pinned files, so cache-first is safe.
    if (CDN_HOSTS.indexOf(url.hostname) !== -1) {
        event.respondWith(cacheFirst(request));
        return;
    }

    // Anything else on another site: leave it to the browser.
    if (url.origin !== self.location.origin) {
        return;
    }

    // Our static files: newest when online, cached when offline.
    if (url.pathname.indexOf("/static/") === 0) {
        event.respondWith(networkFirst(request, true));
        return;
    }

    // The POS screen itself is kept for offline use. Other pages are not stored.
    const isPosPage = request.mode === "navigate" && /\/pos\/?$/.test(url.pathname);
    event.respondWith(networkFirst(request, isPosPage));
});
