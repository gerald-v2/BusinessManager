const CACHE_NAME = "bizmanager-v1";

const STATIC_FILES = [
    "/static/style.css",
    "/static/manifest.json",
    "/static/offline-sync.js"
];

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_FILES))
    );

    self.skipWaiting();
});

self.addEventListener("activate", event => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", event => {
    event.respondWith(
        fetch(event.request)
            .catch(() => caches.match(event.request))
    );
});