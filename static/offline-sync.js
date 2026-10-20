(function () {
// Loaded by both base.html and pos.html: only run once.
if (window.offlineSync) { return; }

// ============================================================
// BizManager Offline Sync
// ============================================================

const DB_NAME = "BusinessManagerOffline";
const DB_VERSION = 4;

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

            if (!database.objectStoreNames.contains("snapshots")) {
                database.createObjectStore("snapshots", {
                    keyPath: "biz"
                });
            }

            if (!database.objectStoreNames.contains("actions")) {
                database.createObjectStore("actions", {
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
// OFFLINE SNAPSHOTS: products, customers and employees
// ------------------------------------------------------------
async function refreshSnapshot(biz) {
    if (!biz || !navigator.onLine) return null;
    try {
        const response = await fetch("/api/offline/snapshot/" + encodeURIComponent(biz), {
            method: "GET",
            credentials: "same-origin",
            headers: { "Accept": "application/json" },
            cache: "no-store"
        });
        if (!response.ok) return null;
        const snapshot = await response.json();
        if (snapshot.status !== "ok") return null;
        await dbReady;
        await new Promise((resolve, reject) => {
            const tx = db.transaction("snapshots", "readwrite");
            tx.objectStore("snapshots").put(snapshot);
            tx.oncomplete = resolve;
            tx.onerror = event => reject(event.target.error);
        });
        return snapshot;
    } catch (error) {
        console.log("BizManager offline snapshot refresh deferred.", error);
        return null;
    }
}

async function getSnapshot(biz) {
    await dbReady;
    return new Promise((resolve, reject) => {
        const request = db.transaction("snapshots", "readonly")
            .objectStore("snapshots").get(biz);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = event => reject(event.target.error);
    });
}

async function clearSnapshots() {
    await dbReady;
    return new Promise((resolve, reject) => {
        const tx = db.transaction("snapshots", "readwrite");
        tx.objectStore("snapshots").clear();
        tx.oncomplete = resolve;
        tx.onerror = event => reject(event.target.error);
    });
}

function businessFromPath() {
    const match = window.location.pathname.match(/^\/biz\/([^/]+)/);
    if (!match) return null;
    try { return decodeURIComponent(match[1]); }
    catch (_) { return match[1]; }
}


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
// OFFLINE FORM ACTION QUEUE (Products / Employees)
// ------------------------------------------------------------
async function applyLocalFormAction(action) {
    const snapshot = await getSnapshot(action.biz);
    if (!snapshot) return;
    const data = Object.fromEntries(action.entries || []);
    const path = action.url;
    const parts = path.split("/").filter(Boolean).map(part => {
        try { return decodeURIComponent(part); } catch (_) { return part; }
    });
    const module = parts[2];
    if (module === "products") {
        snapshot.products = snapshot.products || {};
        if (parts.length === 4 && parts[3] === "add") {
            const name = String(data.product_name || "").trim().replace(/\b\w/g, c => c.toUpperCase());
            if (name && !snapshot.products[name]) {
                snapshot.products[name] = { Price: "$" + Number(data.price || 0).toFixed(2), Cost: "$" + Number(data.cost || 0).toFixed(2), variants: [] };
            }
        } else if (parts.length === 5 && parts[4] === "edit") {
            const product = snapshot.products[parts[3]];
            if (product) {
                if (data.price !== undefined) product.Price = "$" + Number(data.price || 0).toFixed(2);
                if (data.cost !== undefined) product.Cost = "$" + Number(data.cost || 0).toFixed(2);
            }
        } else if (parts.length === 5 && parts[4] === "remove") {
            delete snapshot.products[parts[3]];
        }
    } else if (module === "employees") {
        snapshot.employees = Array.isArray(snapshot.employees) ? snapshot.employees : [];
        if (parts.length === 4 && parts[3] === "add") {
            const name = String(data.name || "").trim().replace(/\b\w/g, c => c.toUpperCase());
            const role = String(data.role || "").trim().replace(/\b\w/g, c => c.toUpperCase());
            if (name && role) snapshot.employees.push({ name, role, salary: Number(data.salary || 0), notes: String(data.notes || "") });
        } else if (parts.length === 5 && parts[4] === "edit") {
            const index = Number(parts[3]);
            if (snapshot.employees[index]) {
                ["name", "role", "notes"].forEach(key => { if (data[key] !== undefined) snapshot.employees[index][key] = String(data[key]); });
                if (data.salary !== undefined) snapshot.employees[index].salary = Number(data.salary || 0);
            }
        } else if (parts.length === 5 && parts[4] === "remove") {
            const index = Number(parts[3]);
            if (index >= 0 && index < snapshot.employees.length) snapshot.employees.splice(index, 1);
        }
    }
    await new Promise((resolve, reject) => {
        const tx = db.transaction("snapshots", "readwrite");
        tx.objectStore("snapshots").put(snapshot);
        tx.oncomplete = resolve;
        tx.onerror = event => reject(event.target.error);
    });
    renderOfflineModule(snapshot);
}

function renderOfflineModule(snapshot) {
    const path = window.location.pathname;
    if (/\/products\/?$/.test(path)) {
        const grid = document.getElementById("productGrid");
        if (!grid) return;
        const products = snapshot.products || {};
        const existing = new Map(Array.from(grid.querySelectorAll(".product-card-col"))
            .map(card => [String(card.dataset.name || "").toLowerCase(), card]));
        existing.forEach((card, key) => {
            if (!Object.keys(products).some(name => name.toLowerCase() === key)) card.style.display = "none";
        });
        Object.entries(products).forEach(([name, details]) => {
            const key = name.toLowerCase();
            if (existing.has(key)) {
                const card = existing.get(key);
                card.style.display = "";
                const nameEl = card.querySelector(".product-name");
                if (nameEl) nameEl.textContent = name;
                const priceEl = card.querySelector(".product-price");
                if (priceEl && details.Price !== undefined) priceEl.textContent = String(details.Price);
                return;
            }
            const col = document.createElement("div");
            col.className = "col-6 col-md-4 col-lg-3 product-card-col";
            col.dataset.name = key;
            const link = document.createElement("a");
            link.className = "text-decoration-none";
            link.href = window.location.pathname.replace(/\/products\/?$/, "/products/" + encodeURIComponent(name));
            const card = document.createElement("div");
            card.className = "card h-100 product-catalogue-card p-3";
            const title = document.createElement("div");
            title.className = "product-name";
            title.textContent = name;
            const price = document.createElement("div");
            price.className = "product-price";
            price.textContent = String(details.Price || details.price || "");
            const variants = document.createElement("div");
            variants.className = "small text-muted";
            variants.textContent = (details.variants || []).length + " variants (saved locally)";
            card.append(title, price, variants);
            link.appendChild(card);
            col.appendChild(link);
            grid.appendChild(col);
        });
    }
    if (/\/employees\/?$/.test(path)) {
        const body = document.querySelector("table tbody");
        if (!body) return;
        const employees = snapshot.employees || [];
        const rows = Array.from(body.querySelectorAll("tr"));
        employees.forEach((emp, index) => {
            let row = rows[index];
            if (!row) {
                row = document.createElement("tr");
                for (let i = 0; i < 8; i++) row.appendChild(document.createElement("td"));
                body.appendChild(row);
            }
            const cells = row.querySelectorAll("td");
            if (cells[0]) cells[0].textContent = String(index + 1);
            if (cells[1]) cells[1].textContent = emp.name || "";
            if (cells[2]) cells[2].textContent = emp.role || "";
            if (cells[3]) cells[3].textContent = String(emp.salary ?? 0);
            if (cells[4]) cells[4].textContent = "—";
            if (cells[5]) cells[5].textContent = String(emp.salary ?? 0);
            if (cells[6]) cells[6].textContent = emp.notes || "—";
            row.style.display = "";
            row.dataset.offlineEmployee = "true";
        });
        rows.slice(employees.length).forEach(row => {
            // Keep the row's action controls and hide only rows removed from the local snapshot.
            row.style.display = "none";
        });
    }
}

async function queueFormAction(form) {
    await dbReady;
    const entries = Array.from(new FormData(form).entries()).map(([key, value]) => [key, String(value)]);
    const action = {
        id: generateSaleId(),
        url: new URL(form.action, window.location.origin).pathname,
        method: "POST",
        entries,
        biz: businessFromPath(),
        created_at: new Date().toISOString(),
        synced: false
    };
    await new Promise((resolve, reject) => {
        const tx = db.transaction("actions", "readwrite");
        tx.objectStore("actions").put(action);
        tx.oncomplete = resolve;
        tx.onerror = event => reject(event.target.error);
    });
    await applyLocalFormAction(action);
    await updateSyncBadge();
    return action;
}

async function getQueuedActions() {
    await dbReady;
    return new Promise((resolve, reject) => {
        const request = db.transaction("actions", "readonly").objectStore("actions").getAll();
        request.onsuccess = () => resolve((request.result || []).sort((a, b) =>
            a.created_at.localeCompare(b.created_at)));
        request.onerror = event => reject(event.target.error);
    });
}

async function removeQueuedAction(id) {
    await dbReady;
    return new Promise((resolve, reject) => {
        const tx = db.transaction("actions", "readwrite");
        tx.objectStore("actions").delete(id);
        tx.oncomplete = resolve;
        tx.onerror = event => reject(event.target.error);
    });
}

async function syncQueuedActions() {
    if (!navigator.onLine) return;
    const actions = await getQueuedActions();
    for (const action of actions) {
        try {
            const body = new URLSearchParams();
            action.entries.forEach(([key, value]) => body.append(key, value));
            const response = await fetch(action.url, {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
                body: body.toString(),
                redirect: "follow"
            });
            if (response.url.includes("/business-login") || response.url.includes("/admin/login")) break;
            if (!response.ok) break;
            const html = await response.clone().text();
            // Validation/access errors are not silently discarded; keep them queued.
            if (/alert-danger|Access denied|not logged in/i.test(html)) {
                console.error("Offline change needs attention and remains queued:", action.url);
                break;
            }
            await removeQueuedAction(action.id);
        } catch (error) {
            console.log("Offline form changes will retry later.", error);
            break;
        }
    }
    await updateSyncBadge();
}

function installOfflineFormQueue() {
    document.addEventListener("submit", async event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || navigator.onLine) return;
        if ((form.method || "get").toUpperCase() !== "POST") return;
        const path = new URL(form.action, window.location.origin).pathname;
        // Keep POS checkout on its existing, feature-preserving local sale flow.
        const isProductsOrEmployees = /^\/biz\/[^/]+\/(?:products(?:\/.*)?|employees(?:\/.*)?|attendance\/quick)\/?$/.test(path);
        if (!isProductsOrEmployees) return;
        event.preventDefault();
        try {
            await queueFormAction(form);
            alert("Saved on this device and queued to sync when internet returns. The displayed list may not update until the change syncs.");
        } catch (error) {
            console.error("Could not queue offline change:", error);
            alert("BizManager could not save this change locally. Please keep this page open and try again.");
        }
    }, true);
}

// ------------------------------------------------------------
// SYNC EVERYTHING
// ------------------------------------------------------------

async function saveCustomer(customer) {
    await dbReady;
    const record = Object.assign({}, customer, {
        id: customer.id || generateSaleId(), synced: false,
        offline_created_at: new Date().toISOString()
    });
    return new Promise((resolve, reject) => {
        const tx = db.transaction("customers", "readwrite");
        tx.objectStore("customers").put(record);
        tx.oncomplete = async () => {
            if (navigator.onLine) await syncCustomers();
            resolve(record);
        };
        tx.onerror = event => reject(event.target.error);
    });
}
async function getCustomers() {
    await dbReady;
    return new Promise((resolve, reject) => {
        const req = db.transaction("customers", "readonly").objectStore("customers").getAll();
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = event => reject(event.target.error);
    });
}
async function syncCustomers() {
    if (!navigator.onLine) return;
    const customers = (await getCustomers()).filter(c => !c.synced);
    for (const customer of customers) {
        try {
            const response = await fetch("/api/sync/customer", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify(customer)
            });
            let body = {};
            try { body = await response.json(); } catch (_) {}
            if (response.ok || body.status === "already_processed" || body.status === "already_exists") {
                const saved = Object.assign({}, customer, {
                    synced: true, server_customer_id: body.customer && body.customer.id || customer.id
                });
                await new Promise((resolve, reject) => {
                    const tx = db.transaction("customers", "readwrite");
                    tx.objectStore("customers").put(saved);
                    tx.oncomplete = resolve;
                    tx.onerror = event => reject(event.target.error);
                });
            } else if (response.status === 401 || response.status >= 500) {
                break;
            } else {
                console.error("Customer sync rejected:", customer.id, body.error || response.status);
            }
        } catch (error) {
            console.log("Customer sync will retry when online.", error);
            break;
        }
    }
    await updateSyncBadge();
}
async function syncOfflineData() {
    if (!navigator.onLine) return;
    await syncCustomers();
    await syncQueuedActions();
    const sales = await getQueuedSales();
    if (sales.length > 0) {
        console.log(`Attempting to sync ${sales.length} sale(s)`);
        window.offlineSyncRejected = {};
        for (const sale of sales) {
            const result = await syncSale(sale);
            if (result === "retry") break;
        }
        const rejected = Object.keys(window.offlineSyncRejected || {});
        if (rejected.length > 0 && !window.__rejectedAlertShown) {
            window.__rejectedAlertShown = true;
            alert(rejected.length + " offline sale(s) could not be recorded:\n\n" +
                rejected.map(id => "- " + window.offlineSyncRejected[id]).join("\n") +
                "\n\nThey are still saved on this device. Ask a manager to check them.");
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


    const sales = await getQueuedSales();
    const customers = (await getCustomers()).filter(c => !c.synced);
    const actions = await getQueuedActions();
    const pending = sales.length + customers.length + actions.length;
    if (pending === 0) {
        badge.style.display = "none";
        return;
    }
    badge.style.display = "inline-block";
    const parts = [];
    if (sales.length) parts.push(sales.length + " sale(s)");
    if (customers.length) parts.push(customers.length + " customer(s)");
    if (actions.length) parts.push(actions.length + " product/employee change(s)");
    badge.textContent = parts.join(" + ") + " waiting to sync";
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

        await refreshSnapshot(businessFromPath());
        await syncOfflineData();
    }
);

window.addEventListener("online", function() {
    syncOfflineData();
    updateConnectionStatus();
});
window.addEventListener("offline", updateConnectionStatus);


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

// Clear private snapshots when a signed-in user explicitly logs out.
document.addEventListener("click", async function(event) {
    const link = event.target.closest && event.target.closest('a[href="/logout"]');
    if (!link) return;
    try { await clearSnapshots(); } catch (error) {
        console.warn("Could not clear offline snapshots on logout.", error);
    }
}, true);

installOfflineFormQueue();

window.addEventListener(
    "load",
    async function() {

        updateConnectionStatus();

        await dbReady;

        await updateSyncBadge();

        const savedSnapshot = await getSnapshot(businessFromPath());
        if (savedSnapshot) renderOfflineModule(savedSnapshot);

        if (navigator.onLine) {
            await refreshSnapshot(businessFromPath());
            await syncOfflineData();
        }
    }
);


// ------------------------------------------------------------
// PUBLIC API
// ------------------------------------------------------------

window.offlineSync = {

    queueSale,
    refreshSnapshot,
    getSnapshot,
    clearSnapshots,
    queueFormAction,
    getQueuedActions,
    syncQueuedActions,
    saveCustomer,
    getCustomers,
    syncCustomers,

    syncOfflineData,

    updateSyncBadge,

    getQueuedSales,

    generateSaleId
};

})();
