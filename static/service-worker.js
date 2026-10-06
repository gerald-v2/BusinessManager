const CACHE_NAME = "bizmanager-v2";

const CORE_FILES = [
    "/static/style.css",
    "/static/offline-sync.js",
    "/static/manifest.json"
];


// ------------------------------------------------------------
// INSTALL
// ------------------------------------------------------------

self.addEventListener(
    "install",
    event => {

        event.waitUntil(

            caches
                .open(CACHE_NAME)
                .then(cache => {

                    return cache.addAll(
                        CORE_FILES
                    );
                })
        );

        self.skipWaiting();
    }
);


// ------------------------------------------------------------
// ACTIVATE
// ------------------------------------------------------------

self.addEventListener(
    "activate",
    event => {

        event.waitUntil(

            caches.keys()
                .then(names => {

                    return Promise.all(

                        names
                            .filter(
                                name =>
                                    name !==
                                    CACHE_NAME
                            )
                            .map(
                                name =>
                                    caches.delete(name)
                            )
                    );
                })
        );

        self.clients.claim();
    }
);


// ------------------------------------------------------------
// FETCH
// ------------------------------------------------------------

self.addEventListener(
    "fetch",
    event => {

        const request =
            event.request;

        // Only handle GET requests.
        if (request.method !== "GET") {
            return;
        }


        event.respondWith(

            fetch(request)

                .then(response => {

                    if (
                        response.ok &&
                        new URL(request.url)
                            .pathname
                            .includes("/pos")
                    ) {

                        const copy =
                            response.clone();

                        caches
                            .open(CACHE_NAME)
                            .then(cache => {

                                cache.put(
                                    request,
                                    copy
                                );
                            });
                    }

                    return response;
                })


                .catch(() => {

                    return caches
                        .match(request)
                        .then(cached => {

                            if (cached) {
                                return cached;
                            }


                            return new Response(
                                `
                                <!DOCTYPE html>
                                <html>
                                <head>
                                    <title>BizManager Offline</title>
                                </head>
                                <body style="font-family:sans-serif;text-align:center;padding:50px">
                                    <h2>BizManager is offline</h2>
                                    <p>Your saved sales are safe.</p>
                                    <p>Reconnect to sync them.</p>
                                </body>
                                </html>
                                `,
                                {
                                    headers: {
                                        "Content-Type":
                                            "text/html"
                                    }
                                }
                            );
                        });
                })
        );
    }
);