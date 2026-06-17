/**
 * offline-sync.js — Offline-first cash sale queue for BizManager POS.
 *
 * Scope: cash sales only, full amount, no discount/points/currency conversion.
 * Those features still require a connection. This covers the most common
 * case for a small shop: "sell this item for cash right now."
 *
 * How it works:
 *  1. Register the service worker (sw.js) so the POS page shell loads offline.
 *  2. Maintain an IndexedDB store of pending sales made while offline.
 *  3. When a sale is completed offline, save it locally + update the on-screen
 *     cart/stock display immediately, instead of waiting on the network.
 *  4. Listen for the browser coming back online, then POST all pending sales
 *     to /api/sync in order. On success, clear them from the queue.
 */

const DB_NAME = 'bizmanager_offline';
const DB_VERSION = 1;
const STORE_NAME = 'pending_sales';

let dbPromise = null;

function openDB() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'localId', autoIncrement: true });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

/** Save a sale to the local offline queue. Returns the new record's localId. */
async function queueSale(biz, items, totalGuess) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    const record = {
      biz,
      items,                 // [{product, variant, plu, qty, subtotal}, ...]
      total: totalGuess,
      created_at: new Date().toISOString(),
      synced: false,
    };
    const req = store.add(record);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Get every sale still waiting to sync. */
async function getPendingSales() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result.filter((r) => !r.synced));
    req.onerror = () => reject(req.error);
  });
}

/** Remove a synced sale from the local queue. */
async function removeSale(localId) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete(localId);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

/** How many sales are still waiting — used to show a badge in the UI. */
async function pendingCount() {
  const pending = await getPendingSales();
  return pending.length;
}

/** Push every pending sale to the backend. Call this when back online. */
async function syncPendingSales() {
  const pending = await getPendingSales();
  if (pending.length === 0) return { synced: 0, failed: 0 };

  let synced = 0;
  let failed = 0;

  for (const sale of pending) {
    try {
      const resp = await fetch('/api/sync/sale', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          biz: sale.biz,
          items: sale.items,
          created_at: sale.created_at,
        }),
      });
      if (resp.ok) {
        await removeSale(sale.localId);
        synced++;
      } else {
        failed++;
      }
    } catch (e) {
      // Still offline or server unreachable — stop here, try again later.
      failed++;
      break;
    }
  }

  updateSyncBadge();
  return { synced, failed };
}

/** Update a small on-page badge showing how many sales are waiting to sync. */
async function updateSyncBadge() {
  const badge = document.getElementById('offlineSyncBadge');
  if (!badge) return;
  const count = await pendingCount();
  if (count > 0) {
    badge.style.display = 'inline-block';
    badge.textContent = `${count} sale${count > 1 ? 's' : ''} waiting to sync`;
  } else {
    badge.style.display = 'none';
  }
}

// ── Wire up online/offline events ────────────────────────────────────────────
window.addEventListener('online', async () => {
  console.log('[offline-sync] Back online — syncing pending sales...');
  const result = await syncPendingSales();
  console.log(`[offline-sync] Synced ${result.synced}, failed ${result.failed}`);
});

window.addEventListener('load', () => {
  updateSyncBadge();
  // Try syncing on load too, in case sales were queued before a refresh.
  if (navigator.onLine) syncPendingSales();
});

// Register service worker
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/static/sw.js').catch((e) =>
      console.error('[offline-sync] Service worker registration failed:', e)
    );
  });
}

// Expose functions for pos.html to call directly
window.offlineSync = { queueSale, getPendingSales, syncPendingSales, pendingCount, updateSyncBadge };
