// static/offline-sync.js

function updateConnectionStatus() {
    if (navigator.onLine) {
        console.log("🟢 Internet connection available");
    } else {
        console.log("🔴 Offline mode");
    }
}

window.addEventListener("online", updateConnectionStatus);
window.addEventListener("offline", updateConnectionStatus);

updateConnectionStatus();
if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
        navigator.serviceWorker.register("/static/service-worker.js")
            .then(() => {
                console.log("Service worker registered");
            })
            .catch(error => {
                console.error("Service worker registration failed:", error);
            });
    });
}
const DB_NAME = "BusinessManagerOffline";
const DB_VERSION = 1;

let db;

const request = indexedDB.open(DB_NAME, DB_VERSION);

request.onupgradeneeded = function(event) {
    db = event.target.result;

    if (!db.objectStoreNames.contains("sales")) {
        db.createObjectStore("sales", {
            keyPath: "transaction_id"
        });
    }

    if (!db.objectStoreNames.contains("sync_queue")) {
        db.createObjectStore("sync_queue", {
            keyPath: "id"
        });
    }

    if (!db.objectStoreNames.contains("stock_movements")) {
        db.createObjectStore("stock_movements", {
            keyPath: "id"
        });
    }

    if (!db.objectStoreNames.contains("customers")) {
        db.createObjectStore("customers", {
            keyPath: "id"
        });
    }
};

request.onsuccess = function(event) {
    db = event.target.result;
    console.log("Offline database ready");
};

request.onerror = function(event) {
    console.error("Offline database error:", event.target.error);
};
window.addEventListener("online", function() {
    console.log("Internet restored. Starting sync...");
    syncOfflineData();
});
function updateConnectionStatus() {

    const indicator =
        document.getElementById("connection-status");

    if (!indicator) return;

    if (navigator.onLine) {
        indicator.textContent = "🟢 Online";
    } else {
        indicator.textContent = "🔴 Offline";
    }
}