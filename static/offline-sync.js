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
    taxPct = 0
) {

    await dbReady;

    const saleId = generateSaleId();

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

    try {

        const response = await fetch(
            "/api/sync/sale",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify(sale)
            }
        );


        if (response.ok) {

            await removeQueuedSale(
                sale.sale_id
            );

            console.log(
                "Sale synced:",
                sale.sale_id
            );

            return true;
        }


        if (response.status === 409) {

            // Server says this sale already exists.
            // This prevents duplicate sales.

            await removeQueuedSale(
                sale.sale_id
            );

            console.log(
                "Sale already processed:",
                sale.sale_id
            );

            return true;
        }


        console.error(
            "Sale sync failed:",
            response.status
        );

        return false;

    } catch (error) {

        console.log(
            "Still offline. Sale remains queued."
        );

        return false;
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


    for (const sale of sales) {

        const success =
            await syncSale(sale);

        if (!success) {
            break;
        }
    }


    await updateSyncBadge();
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
                    "/static/service-worker.js"
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