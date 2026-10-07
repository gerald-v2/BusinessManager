/* ============================================================
   BizManager - receipt layout + receipt printer support

   One receipt object (built by the server, or by the POS when the
   device is offline) is turned into:
     * plain text         -> browser print / preview
     * ESC/POS bytes      -> thermal printers

   Ways to print:
     browser   any printer installed on the device (USB cable, Wi-Fi,
               or a Bluetooth printer paired in the OS).  Works everywhere.
     bluetooth Web Bluetooth (BLE printers) - Chrome/Edge on Android,
               Windows, Mac, Linux, ChromeOS.  NOT Safari / iPhone / iPad.
     usb       WebUSB (ESC/POS printer on a USB cable) - Chrome/Edge.
               On Windows the printer needs a WinUSB driver; otherwise use
               "browser" mode.
     rawbt     Android "RawBT" app (hand the receipt to the app).

   Receipt object fields: see Pos.build_receipt() in Pos.py.
============================================================ */

(function () {
    "use strict";

    var MODE_KEY = "bm_printer_mode";
    var USB_KEY = "bm_usb_printer";

    var state = { ble: null, usb: null };

    /* ---------------------------------------------------------
       Text helpers (thermal printers want plain ASCII)
    --------------------------------------------------------- */
    var CHAR_MAP = {
        "\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'",
        "\u201c": "\"", "\u201d": "\"", "\u2026": "...", "\u00d7": "x",
        "\u00a0": " ", "\u2022": "*", "\u20ac": "EUR", "\u00a3": "GBP",
        "\u00a5": "JPY"
    };

    function ascii(value) {
        var text = String(value === null || value === undefined ? "" : value);
        text = text.replace(/[\u2013\u2014\u2018\u2019\u201c\u201d\u2026\u00d7\u00a0\u2022\u20ac\u00a3\u00a5]/g,
            function (c) { return CHAR_MAP[c]; });
        if (text.normalize) {
            text = text.normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
        }
        return text.replace(/[^\x20-\x7e]/g, "?");
    }

    function symbol(sym, code) {
        var s = String(sym || "");
        return /^[\x20-\x7e]+$/.test(s) && s.length ? s : (code || "");
    }

    function money(sym, amount) {
        var n = Number(amount);
        if (!isFinite(n)) { n = 0; }
        return sym + n.toFixed(2);
    }

    function wrap(text, width) {
        var words = ascii(text).split(/\s+/).filter(Boolean);
        var lines = [], line = "";
        words.forEach(function (w) {
            while (w.length > width) {            // very long word
                if (line) { lines.push(line); line = ""; }
                lines.push(w.slice(0, width));
                w = w.slice(width);
            }
            if (!line) { line = w; }
            else if ((line + " " + w).length <= width) { line += " " + w; }
            else { lines.push(line); line = w; }
        });
        if (line) { lines.push(line); }
        return lines.length ? lines : [""];
    }

    function pair(left, right, width) {
        left = ascii(left); right = ascii(right);
        var space = width - left.length - right.length;
        if (space < 1) {
            left = left.slice(0, Math.max(1, width - right.length - 1));
            space = Math.max(1, width - left.length - right.length);
        }
        return left + new Array(space + 1).join(" ") + right;
    }

    /* ---------------------------------------------------------
       Receipt layout -> [{text, align, bold, big}]
    --------------------------------------------------------- */
    function layout(r, widthChars) {
        var W = widthChars || (Number(r.paper_width) === 80 ? 48 : 32);
        var out = [];
        var sym = symbol(r.sym, r.currency);
        var paySym = symbol(r.pay_sym, r.pay_currency);
        var biz = r.business || {};
        var line = new Array(W + 1).join("-");

        function add(text, o) {
            o = o || {};
            out.push({ text: text, align: o.align || "left", bold: !!o.bold, big: !!o.big });
        }
        function center(text, o) {
            wrap(text, W).forEach(function (t) {
                add(t, Object.assign({ align: "center" }, o || {}));
            });
        }

        center(biz.name || "", { bold: true, big: true });
        if (biz.header) { center(biz.header); }
        if (biz.address) { center(biz.address); }
        if (biz.phone) { center("Tel: " + biz.phone); }
        if (biz.vat_number) { center("VAT No: " + biz.vat_number); }
        add(line);

        add(pair("Receipt #" + (r.receipt_no || ""), (r.date || "") + " " + (r.time || ""), W));
        if (r.cashier) { add("Cashier: " + ascii(r.cashier)); }
        if (r.customer && r.customer.name) { add("Customer: " + ascii(r.customer.name)); }
        if (r.refunded) { center("*** REFUNDED ***", { bold: true }); }
        if (r.provisional) { center("(Offline copy - not yet synced)"); }
        add(line);

        (r.items || []).forEach(function (it) {
            var name = it.product + (it.variant ? " (" + it.variant + ")" : "");
            wrap(name, W).forEach(function (t) { add(t); });
            add(pair("  " + it.qty + " x " + money(sym, it.unit_price),
                money(sym, it.subtotal), W));
        });
        add(line);

        add(pair("Subtotal", money(sym, r.subtotal), W));
        if (Number(r.discount_amt) > 0) {
            var label = r.discount_label || "Discount";
            if (Number(r.discount_pct) > 0) {
                label += " (" + Number(r.discount_pct).toFixed(1).replace(/\.0$/, "") + "%)";
            }
            add(pair(label.slice(0, W - 10), "-" + money(sym, r.discount_amt), W));
        }
        if (Number(r.vat_pct) > 0) {
            var vatLabel = "VAT " + Number(r.vat_pct).toFixed(1).replace(/\.0$/, "") + "%" +
                (r.vat_inclusive ? " incl." : "");
            add(pair(vatLabel, money(sym, r.vat_amt), W));
        }
        add(pair("TOTAL", money(sym, r.total), W), { bold: true, big: true });
        add(line);

        var foreign = r.pay_currency && r.currency && r.pay_currency !== r.currency;
        add(pair("Paid by", ascii(r.payment || "Cash"), W));
        if (foreign) {
            add(pair("Total (" + r.pay_currency + ")",
                money(paySym, Number(r.total) * Number(r.alt_rate || 1)), W));
        }
        if (String(r.payment || "Cash") === "Cash") {
            add(pair("Tendered", money(foreign ? paySym : sym, foreign ? r.tendered : r.payment_amount), W));
            add(pair("Change", money(foreign ? paySym : sym, foreign ? r.change_pay : r.change), W));
        }

        if (r.customer && (r.customer.points_earned || r.customer.points_redeemed ||
            (r.customer.balance !== null && r.customer.balance !== undefined))) {
            add(line);
            if (r.customer.points_redeemed) { add(pair("Points used", String(r.customer.points_redeemed), W)); }
            if (r.customer.points_earned) { add(pair("Points earned", String(r.customer.points_earned), W)); }
            if (r.customer.balance !== null && r.customer.balance !== undefined) {
                add(pair("Points balance", String(r.customer.balance), W));
            }
        }

        if (biz.footer) {
            add(line);
            center(biz.footer);
        }
        return out;
    }

    function toText(r, widthChars) {
        var W = widthChars || (Number(r.paper_width) === 80 ? 48 : 32);
        return layout(r, W).map(function (l) {
            var t = l.text;
            if (l.align === "center" && t.length < W) {
                t = new Array(Math.floor((W - t.length) / 2) + 1).join(" ") + t;
            }
            return t;
        }).join("\n");
    }

    /* ---------------------------------------------------------
       ESC/POS
    --------------------------------------------------------- */
    function toEscPos(r, opts) {
        opts = opts || {};
        var W = Number(r.paper_width) === 80 ? 48 : 32;
        var bytes = [];
        function push() { for (var i = 0; i < arguments.length; i++) { bytes.push(arguments[i]); } }
        function text(s) {
            s = ascii(s);
            for (var i = 0; i < s.length; i++) { bytes.push(s.charCodeAt(i)); }
        }

        push(0x1b, 0x40);              // initialise
        push(0x1b, 0x74, 0x00);        // code page 0 (PC437)
        layout(r, W).forEach(function (l) {
            push(0x1b, 0x61, l.align === "center" ? 1 : 0);
            push(0x1b, 0x45, l.bold ? 1 : 0);
            push(0x1d, 0x21, l.big ? 0x01 : 0x00);   // double height only: keeps 32/48 columns
            text(l.text);
            push(0x0a);
        });
        push(0x1b, 0x45, 0x00);
        push(0x1d, 0x21, 0x00);
        push(0x1b, 0x61, 0x00);
        push(0x1b, 0x64, 4);           // feed 4 lines
        if (opts.cut !== false && r.cut !== false) {
            push(0x1d, 0x56, 0x42, 0x00);   // partial cut (ignored by printers without a cutter)
        }
        return new Uint8Array(bytes);
    }

    function toBase64(bytes) {
        var bin = "";
        for (var i = 0; i < bytes.length; i++) { bin += String.fromCharCode(bytes[i]); }
        return btoa(bin);
    }

    function rawbtUrl(r) {
        return "intent:base64," + toBase64(toEscPos(r)) +
            "#Intent;scheme=rawbt;package=ru.a402d.rawbtprinter;end;";
    }

    /* ---------------------------------------------------------
       Browser print (any printer the device knows about)
    --------------------------------------------------------- */
    function printBrowser(r) {
        var mm = Number(r.paper_width) === 80 ? 80 : 58;
        var W = mm === 80 ? 48 : 32;
        var body = toText(r, W)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        var html = "<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>Receipt</title>" +
            "<style>@page{size:" + mm + "mm auto;margin:0}" +
            "html,body{margin:0;padding:0;background:#fff}" +
            "pre{margin:0;padding:2mm;font-family:'Courier New',monospace;" +
            "font-size:" + (mm === 80 ? "12px" : "11px") + ";line-height:1.25;" +
            "width:" + mm + "mm;box-sizing:border-box;white-space:pre-wrap;color:#000}" +
            "</style></head><body><pre>" + body + "</pre></body></html>";

        var frame = document.createElement("iframe");
        frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
        document.body.appendChild(frame);
        var doc = frame.contentWindow.document;
        doc.open(); doc.write(html); doc.close();
        return new Promise(function (resolve) {
            setTimeout(function () {
                frame.contentWindow.focus();
                frame.contentWindow.print();
                setTimeout(function () { document.body.removeChild(frame); resolve(); }, 1500);
            }, 250);
        });
    }

    /* ---------------------------------------------------------
       Bluetooth (BLE thermal printers)
    --------------------------------------------------------- */
    var BLE_SERVICES = [
        "000018f0-0000-1000-8000-00805f9b34fb",
        "e7810a71-73ae-499d-8c15-faa9aef0c3f2",
        "49535343-fe7d-4ae5-8fa9-9fafd205e455",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000fff0-0000-1000-8000-00805f9b34fb",
        "0000ff00-0000-1000-8000-00805f9b34fb",
        "0000ae30-0000-1000-8000-00805f9b34fb"
    ];

    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    async function findWritable(server) {
        var services = await server.getPrimaryServices();
        for (var i = 0; i < services.length; i++) {
            var chars = await services[i].getCharacteristics();
            for (var j = 0; j < chars.length; j++) {
                if (chars[j].properties.write || chars[j].properties.writeWithoutResponse) {
                    return chars[j];
                }
            }
        }
        return null;
    }

    async function connectBluetooth() {
        if (!navigator.bluetooth) {
            throw new Error("Bluetooth printing needs Chrome or Edge (not Safari/iPhone). " +
                "Use Browser print instead.");
        }
        var device = await navigator.bluetooth.requestDevice({
            acceptAllDevices: true,
            optionalServices: BLE_SERVICES
        });
        var server = await device.gatt.connect();
        var characteristic = await findWritable(server);
        if (!characteristic) {
            throw new Error("Could not find a print channel on this Bluetooth device. " +
                "It may be a classic (non-BLE) printer - pair it in Bluetooth settings " +
                "and use Browser print or the RawBT app.");
        }
        state.ble = { device: device, characteristic: characteristic };
        return device.name || "Bluetooth printer";
    }

    async function writeBluetooth(bytes) {
        if (!state.ble) { throw new Error("Printer not connected."); }
        var dev = state.ble.device;
        if (!dev.gatt.connected) {
            var server = await dev.gatt.connect();
            state.ble.characteristic = await findWritable(server);
        }
        var ch = state.ble.characteristic;
        var size = 100;
        for (var i = 0; i < bytes.length; i += size) {
            var chunk = bytes.slice(i, i + size);
            if (ch.writeValueWithoutResponse) {
                await ch.writeValueWithoutResponse(chunk);
            } else {
                await ch.writeValue(chunk);
            }
            await sleep(20);
        }
    }

    /* ---------------------------------------------------------
       USB cable (WebUSB)
    --------------------------------------------------------- */
    async function openUsb(device) {
        await device.open();
        if (device.configuration === null) { await device.selectConfiguration(1); }
        var pick = null;
        device.configuration.interfaces.forEach(function (iface) {
            iface.alternates.forEach(function (alt) {
                var out = alt.endpoints.filter(function (e) {
                    return e.direction === "out" && e.type === "bulk";
                })[0];
                if (out && (!pick || alt.interfaceClass === 7)) {
                    pick = { iface: iface.interfaceNumber, alt: alt.alternateSetting, ep: out.endpointNumber };
                }
            });
        });
        if (!pick) { throw new Error("This USB device has no printer output channel."); }
        await device.claimInterface(pick.iface);
        if (pick.alt) { await device.selectAlternateInterface(pick.iface, pick.alt); }
        state.usb = { device: device, ep: pick.ep };
        try {
            localStorage.setItem(USB_KEY, JSON.stringify({
                vendorId: device.vendorId, productId: device.productId
            }));
        } catch (e) { /* storage unavailable - fine */ }
        return device.productName || "USB printer";
    }

    async function connectUsb() {
        if (!navigator.usb) {
            throw new Error("USB printing needs Chrome or Edge on a computer or Android. " +
                "Use Browser print instead.");
        }
        var device = await navigator.usb.requestDevice({ filters: [] });
        return openUsb(device);
    }

    async function reconnectUsb() {
        if (state.usb || !navigator.usb) { return !!state.usb; }
        var saved = null;
        try { saved = JSON.parse(localStorage.getItem(USB_KEY) || "null"); } catch (e) { saved = null; }
        if (!saved) { return false; }
        var devices = await navigator.usb.getDevices();
        var match = devices.filter(function (d) {
            return d.vendorId === saved.vendorId && d.productId === saved.productId;
        })[0];
        if (!match) { return false; }
        await openUsb(match);
        return true;
    }

    async function writeUsb(bytes) {
        if (!state.usb) { throw new Error("Printer not connected."); }
        var size = 4096;
        for (var i = 0; i < bytes.length; i += size) {
            await state.usb.device.transferOut(state.usb.ep, bytes.slice(i, i + size));
        }
    }

    /* ---------------------------------------------------------
       Public API
    --------------------------------------------------------- */
    function getMode() {
        try { return localStorage.getItem(MODE_KEY) || "browser"; } catch (e) { return "browser"; }
    }
    function setMode(mode) {
        try { localStorage.setItem(MODE_KEY, mode); } catch (e) { /* ignore */ }
    }

    function support() {
        return {
            bluetooth: !!navigator.bluetooth,
            usb: !!navigator.usb,
            android: /android/i.test(navigator.userAgent || "")
        };
    }

    async function print(r, mode) {
        mode = mode || getMode();
        if (mode === "bluetooth") {
            if (!state.ble) { await connectBluetooth(); }
            await writeBluetooth(toEscPos(r));
            return "Sent to Bluetooth printer.";
        }
        if (mode === "usb") {
            if (!state.usb && !(await reconnectUsb())) { await connectUsb(); }
            await writeUsb(toEscPos(r));
            return "Sent to USB printer.";
        }
        if (mode === "rawbt") {
            window.location.href = rawbtUrl(r);
            return "Opening RawBT...";
        }
        await printBrowser(r);
        return "Print dialog opened.";
    }

    /* ---------------------------------------------------------
       Ready-made controls (mode picker, connect, print)
    --------------------------------------------------------- */
    var HELP = {
        browser: "Uses the normal print dialog: choose your receipt printer (USB cable, " +
            "Wi-Fi, or a Bluetooth printer already paired in the device settings).",
        bluetooth: "Connect once per visit, then print. Works with most Bluetooth (BLE) " +
            "58mm/80mm receipt printers in Chrome or Edge. Not available on iPhone/iPad.",
        usb: "For an ESC/POS printer on a USB cable (Chrome/Edge). On Windows the printer " +
            "needs a WinUSB driver - if Connect fails, use Browser print instead.",
        rawbt: "Android only: needs the free RawBT app installed and your printer set up in it."
    };

    function mountControls(el, getReceipt) {
        if (!el) { return null; }
        var sup = support();
        el.innerHTML =
            '<div class="row g-2 align-items-center">' +
            '<div class="col-12 col-md-5"><select class="form-select" data-bm="mode">' +
            '<option value="browser">Browser print (any printer / USB cable)</option>' +
            '<option value="bluetooth"' + (sup.bluetooth ? '' : ' disabled') + '>Bluetooth printer' +
            (sup.bluetooth ? '' : ' (not supported here)') + '</option>' +
            '<option value="usb"' + (sup.usb ? '' : ' disabled') + '>USB cable printer' +
            (sup.usb ? '' : ' (not supported here)') + '</option>' +
            '<option value="rawbt"' + (sup.android ? '' : ' disabled') + '>RawBT app (Android)' +
            (sup.android ? '' : ' (Android only)') + '</option>' +
            '</select></div>' +
            '<div class="col-6 col-md-3"><button type="button" class="btn btn-outline-secondary w-100" data-bm="connect">' +
            '<i class="bi bi-bluetooth me-1"></i>Connect</button></div>' +
            '<div class="col-6 col-md-4"><button type="button" class="btn btn-primary w-100" data-bm="print">' +
            '<i class="bi bi-printer me-1"></i>Print receipt</button></div>' +
            '</div>' +
            '<div class="small text-muted mt-2" data-bm="help"></div>' +
            '<div class="small mt-1" data-bm="status"></div>';

        function q(name) { return el.querySelector('[data-bm="' + name + '"]'); }
        var modeSel = q("mode"), connectBtn = q("connect"), printBtn = q("print");
        var help = q("help"), status = q("status");

        var mode = getMode();
        if (modeSel.querySelector('option[value="' + mode + '"]:not([disabled])')) {
            modeSel.value = mode;
        } else {
            modeSel.value = "browser";
        }

        function say(text, kind) {
            status.textContent = text || "";
            status.className = "small mt-1 " + (kind === "error" ? "text-danger" : "text-success");
        }
        function refresh() {
            var m = modeSel.value;
            help.textContent = HELP[m] || "";
            connectBtn.style.display = (m === "bluetooth" || m === "usb") ? "" : "none";
        }
        function friendly(err) {
            if (err && err.name === "NotFoundError") { return "No printer was selected."; }
            if (err && err.name === "SecurityError") { return "The browser blocked printer access (needs HTTPS)."; }
            return (err && err.message) ? err.message : "Printing failed.";
        }

        modeSel.addEventListener("change", function () {
            setMode(modeSel.value); say(""); refresh();
        });
        connectBtn.addEventListener("click", async function () {
            try {
                var name = modeSel.value === "usb" ? await connectUsb() : await connectBluetooth();
                say("Connected: " + name);
            } catch (err) { say(friendly(err), "error"); }
        });
        async function doPrint() {
            try {
                say("Printing...");
                say(await print(getReceipt(), modeSel.value));
            } catch (err) { say(friendly(err), "error"); }
        }
        printBtn.addEventListener("click", doPrint);
        refresh();
        return { print: doPrint, mode: function () { return modeSel.value; } };
    }

    window.ReceiptPrinter = {
        layout: layout,
        toText: toText,
        toEscPos: toEscPos,
        rawbtUrl: rawbtUrl,
        printBrowser: printBrowser,
        connectBluetooth: connectBluetooth,
        connectUsb: connectUsb,
        print: print,
        getMode: getMode,
        setMode: setMode,
        support: support,
        mountControls: mountControls,
        isConnected: function () { return { bluetooth: !!state.ble, usb: !!state.usb }; }
    };
})();
