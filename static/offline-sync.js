(function () {
// Loaded by both base.html and pos.html: only run once.
if (window.offlineSync) { return; }

// ============================================================
// BizManager Offline Sync
// ============================================================

const DB_NAME = "BusinessManagerOffline";
const DB_VERSION = 2;

let db = null;


// ------------------------------------------------------------
// OPEN DATABASE
// ------------------------------------------------------------

function openOfflineDB() {
    return new Promise((resolve, reject) => {

        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = function(event) {

            const database = event.target.result;

            if (!database.objectStoreNames.contains("sales")) {
                database.createObjectStore("sales", {
                    keyPath: "sale_id"
                });
            }

            if (!database.objectStoreNames.contains("sync_queue")) {
                database.createObjectStore("sync_queue", {
                    keyPath: "sale_id"
                });
            }

            if (!database.objectStoreNames.contains("stock_movements")) {
                database.createObjectStore("stock_movements", {
                    keyPath: "id",
                    autoIncrement: true
                });
            }

            if (!database.objectStoreNames.contains("customers")) {
                database.createObjectStore("customers", {
                    keyPath: "id"
                });
            }
        };

        request.onsuccess = function(event) {
            db = event.target.result;
            console.log("BizManager offline database ready");
            resolve(db);
        };

        request.onerror = function(event) {
            console.error(
                "IndexedDB error:",
                event.target.error
            );

            reject(event.target.error);
        };
    });
}


// ------------------------------------------------------------
// DATABASE READY
// ------------------------------------------------------------

const dbReady = openOfflineDB();


// ------------------------------------------------------------
// GENERATE UNIQUE SALE ID
// ------------------------------------------------------------

function generateSaleId() {

    if (crypto.randomUUID) {
        return crypto.randomUUID();
    }

    return (
        Date.now().toString(36) +
        "-" +
        Math.random().toString(36).substring(2)
    );
}


// ------------------------------------------------------------
// SAVE SALE LOCALLY
// ------------------------------------------------------------

async function queueSale(
    biz,
    items,
    total,
    paymentMethod = "Cash",
    paymentAmount = null,
    discountPct = 0,
    taxPct = 0,
    extra = {}
) {

    await dbReady;

    // Re-use the id of the online attempt (if any) so a sale whose reply was
    // lost can never be recorded twice.
    const saleId = extra.sale_id || generateSaleId();

    const sale = {

        sale_id: saleId,

        biz: biz,

        items: items,

        subtotal: total,

        discount_pct: discountPct,

        tax_pct: taxPct,

        total: total,

        payment: paymentMethod,

        payment_amount:
            paymentAmount === null
                ? total
                : paymentAmount,

        offline_created_at:
            new Date().toISOString(),

        synced: false
    };

    // customer, discount {type,value,note}, pay_currency, client_total, receipt …
    Object.keys(extra).forEach(function(k) {
        if (k !== "sale_id") {
            sale[k] = extra[k];
        }
    });


    return new Promise((resolve, reject) => {

        const transaction =
            db.transaction(
                ["sales", "sync_queue"],
                "readwrite"
            );

        transaction.objectStore("sales")
            .put(sale);

        transaction.objectStore("sync_queue")
            .put(sale);

        transaction.oncomplete = function() {

            console.log(
                "Sale saved offline:",
                saleId
            );

            resolve(sale);
        };

        transaction.onerror = function(event) {

            console.error(
                "Could not save offline sale:",
                event.target.error
            );

            reject(event.target.error);
        };
    });
}


// ------------------------------------------------------------
// GET ALL QUEUED SALES
// ------------------------------------------------------------

async function getQueuedSales() {

    await dbReady;

    return new Promise((resolve, reject) => {

        const transaction =
            db.transaction(
                "sync_queue",
                "readonly"
            );

        const request =
            transaction.objectStore("sync_queue")
                .getAll();

        request.onsuccess = function() {
            resolve(request.result || []);
        };

        request.onerror = function(event) {
            reject(event.target.error);
        };
    });
}


// ------------------------------------------------------------
// DELETE SUCCESSFULLY SYNCED SALE
// ------------------------------------------------------------

async function removeQueuedSale(saleId) {

    await dbReady;

    return new Promise((resolve, reject) => {

        const transaction =
            db.transaction(
                ["sales", "sync_queue"],
                "readwrite"
            );

        transaction.objectStore("sales")
            .delete(saleId);

        transaction.objectStore("sync_queue")
            .delete(saleId);

        transaction.oncomplete = resolve;

        transaction.onerror = function(event) {
            reject(event.target.error);
        };
    });
}


// ------------------------------------------------------------
// SYNC ONE SALE
// ------------------------------------------------------------

async function syncSale(sale) {

    // returns "ok"       - recorded (or already recorded) on the server
    //         "rejected" - server refused it; keep it, tell the user, carry on
    //         "retry"    - network problem / logged out; stop and try later
    try {

        const payload = Object.assign({}, sale, { offline: true });

        const response = await fetch(
            "/api/sync/sale",
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            }
        );

        let body = {};
        try { body = await response.json(); } catch (e) {}

        if (response.ok || body.status === "already_processed") {
            await removeQueuedSale(sale.sale_id);
            return "ok";
        }

        if (response.status === 401) {
            return "retry";            // session expired - log in again
        }

        if (response.status >= 500) {
            return "retry";
        }

        // 400 / 403 / 404 / 409 (real conflicts): do NOT delete the sale.
        const message = body.error || ("Server refused the sale (" + response.status + ")");
        console.error("Sale rejected:", sale.sale_id, message);
        window.offlineSyncRejected = window.offlineSyncRejected || {};
        window.offlineSyncRejected[sale.sale_id] = message;
        return "rejected";

    } catch (error) {

        console.log("Still offline. Sale remains queued.");
        return "retry";
    }
}


// ------------------------------------------------------------
// SYNC EVERYTHING
// ------------------------------------------------------------

async function syncOfflineData() {

    if (!navigator.onLine) {
        return;
    }

    const sales =
        await getQueuedSales();

    if (sales.length === 0) {

        updateSyncBadge();

        return;
    }

    console.log(
        `Attempting to sync ${sales.length} sale(s)`
    );

    window.offlineSyncRejected = {};

    for (const sale of sales) {

        const result =
            await syncSale(sale);

        if (result === "retry") {
            break;
        }
    }

    await updateSyncBadge();

    const rejected = Object.keys(window.offlineSyncRejected || {});
    if (rejected.length > 0 && !window.__rejectedAlertShown) {
        window.__rejectedAlertShown = true;
        alert(
            rejected.length + " offline sale(s) could not be recorded:\n\n" +
            rejected.map(function(id) {
                return "- " + window.offlineSyncRejected[id];
            }).join("\n") +
            "\n\nThey are still saved on this device. Ask a manager to check them."
        );
    }
}


// ------------------------------------------------------------
// SYNC BADGE
// ------------------------------------------------------------

async function updateSyncBadge() {

    const badge =
        document.getElementById(
            "offlineSyncBadge"
        );

    if (!badge) {
        return;
    }


    const sales =
        await getQueuedSales();


    if (sales.length === 0) {

        badge.style.display = "none";

        return;
    }


    badge.style.display = "inline-block";

    badge.textContent =
        `${sales.length} sale(s) waiting to sync`;
}


// ------------------------------------------------------------
// CONNECTION STATUS
// ------------------------------------------------------------

function updateConnectionStatus() {

    const indicator =
        document.getElementById(
            "offlineIndicator"
        );

    if (!indicator) {
        return;
    }


    if (navigator.onLine) {

        indicator.style.display =
            "inline-block";

        indicator.className =
            "badge bg-success";

        indicator.innerHTML =
            '<i class="bi bi-wifi me-1"></i>Online';

    } else {

        indicator.style.display =
            "inline-block";

        indicator.className =
            "badge bg-danger";

        indicator.innerHTML =
            '<i class="bi bi-wifi-off me-1"></i>Offline — sales saved on this device';
    }
}


// ------------------------------------------------------------
// ONLINE / OFFLINE EVENTS
// ------------------------------------------------------------

window.addEventListener(
    "online",
    async function() {

        updateConnectionStatus();

        await syncOfflineData();
    }
);


window.addEventListener(
    "offline",
    function() {

        updateConnectionStatus();
    }
);


// ------------------------------------------------------------
// SERVICE WORKER
// ------------------------------------------------------------

if ("serviceWorker" in navigator) {

    window.addEventListener(
        "load",
        function() {

            navigator.serviceWorker
                .register(
                    "/service-worker.js",
                    { scope: "/" }
                )
                .then(function() {

                    console.log(
                        "BizManager service worker registered"
                    );

                })
                .catch(function(error) {

                    console.error(
                        "Service worker registration failed:",
                        error
                    );
                });
        }
    );
}


// ------------------------------------------------------------
// START
// ------------------------------------------------------------

window.addEventListener(
    "load",
    async function() {

        updateConnectionStatus();

        await dbReady;

        await updateSyncBadge();

        if (navigator.onLine) {
            await syncOfflineData();
        }
    }
);


// ------------------------------------------------------------
// PUBLIC API
// ------------------------------------------------------------

window.offlineSync = {

    queueSale,

    syncOfflineData,

    updateSyncBadge,

    getQueuedSales,

    generateSaleId
};

})();
