/* ============================================================
   BizManager - offline clock in / clock out queue

   Clock events are saved on the device first (IndexedDB), with the
   REAL time they happened, then sent to /api/sync/attendance whenever
   there is internet. Every event has a unique id, so sending it twice
   can never create a duplicate record.

   Uses its own small database so it does not touch offline-sync.js.
   Loaded from base.html, so queued events sync from ANY page.
============================================================ */
(function () {
    "use strict";
    if (window.attendanceSync) { return; }

    var DB_NAME = "BizManagerAttendance";
    var STORE = "queue";
    var dbPromise = null;
    var syncing = false;

    function openDb() {
        if (!dbPromise) {
            dbPromise = new Promise(function (resolve, reject) {
                var req = indexedDB.open(DB_NAME, 1);
                req.onupgradeneeded = function () {
                    req.result.createObjectStore(STORE, { keyPath: "id" });
                };
                req.onsuccess = function () { resolve(req.result); };
                req.onerror = function () { reject(req.error); };
            });
        }
        return dbPromise;
    }

    function run(mode, fn) {
        return openDb().then(function (db) {
            return new Promise(function (resolve, reject) {
                var t = db.transaction(STORE, mode);
                var request = fn(t.objectStore(STORE));
                t.oncomplete = function () { resolve(request && request.result); };
                t.onerror = function () { reject(t.error); };
            });
        });
    }

    function queue(ev) { return run("readwrite", function (s) { return s.put(ev); }); }
    function all() { return run("readonly", function (s) { return s.getAll(); }).then(function (r) { return r || []; }); }
    function remove(ids) {
        return run("readwrite", function (s) { ids.forEach(function (id) { s.delete(id); }); });
    }

    function pad(n) { return String(n).padStart(2, "0"); }
    function localDate() {
        var d = new Date();
        return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    }
    function localTime() {
        var d = new Date();
        return pad(d.getHours()) + ":" + pad(d.getMinutes());
    }
    function uuid() {
        if (window.crypto && crypto.randomUUID) { return crypto.randomUUID(); }
        return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
    }

    /* Build an event. time is optional "HH:MM" (manager typing a different time). */
    function makeEvent(biz, employee, action, time, source) {
        return {
            id: uuid(), biz: biz, employee: employee, action: action,
            date: localDate(), time: time || localTime(),
            created: Date.now(), source: source || "quick"
        };
    }

    async function updateBadge() {
        var el = document.getElementById("attendanceSyncBadge");
        if (!el) { return; }
        var n = (await all()).length;
        if (!n) { el.style.display = "none"; return; }
        el.style.display = "inline-block";
        el.textContent = n + " clock event" + (n === 1 ? "" : "s") + " waiting to sync";
    }

    async function sync() {
        if (!navigator.onLine || syncing) { return { synced: 0, issues: [] }; }
        syncing = true;
        var synced = 0, issues = [];
        try {
            var events = await all();
            var byBiz = {};
            events.forEach(function (e) { (byBiz[e.biz] = byBiz[e.biz] || []).push(e); });

            for (var biz of Object.keys(byBiz)) {
                var list = byBiz[biz].sort(function (a, b) { return a.created - b.created; });
                var resp;
                try {
                    resp = await fetch("/api/sync/attendance", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ biz: biz, events: list })
                    });
                } catch (e) { break; }                       // still offline
                if (resp.status === 401 || resp.status >= 500) { break; }   // log in again / try later

                var body = {};
                try { body = await resp.json(); } catch (e) {}
                if (resp.ok && body.results) {
                    var done = Object.keys(body.results);
                    await remove(done);
                    synced += done.length;
                    done.forEach(function (id) {
                        var st = body.results[id];
                        if (st === "rejected" || st === "forbidden") { issues.push({ id: id, status: st }); }
                    });
                } else {
                    console.warn("Attendance sync refused:", resp.status, body.error || "");
                }
            }
        } finally {
            syncing = false;
        }
        await updateBadge();
        if (synced > 0) {
            document.dispatchEvent(new CustomEvent("attendance-synced", { detail: { synced: synced, issues: issues } }));
        }
        return { synced: synced, issues: issues };
    }

    window.addEventListener("online", sync);
    window.addEventListener("load", function () { updateBadge(); sync(); });
    setInterval(sync, 60000);        // catches the case where the "online" event never fires

    window.attendanceSync = {
        makeEvent: makeEvent, queue: queue, all: all, sync: sync,
        updateBadge: updateBadge, localDate: localDate, localTime: localTime
    };
})();
