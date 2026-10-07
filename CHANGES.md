# BizManager – what changed

## POS, discounts, loyalty, VAT, receipts
* New checkout window on the POS screen: customer / loyalty reward, % or fixed discount (with reason), VAT, payment method, other-currency payment, change.
* VAT is set once in **Manager Settings → Sales, VAT & Receipts** (rate, "prices include VAT" or "VAT on top", VAT number). Revenue is recorded without VAT.
* Server works out prices, stock, discount, points, VAT and revenue (the browser can no longer set a price). Staff discount limit is a setting.
* Receipts: preview + print after every sale, reprint from Sales History. Print by Bluetooth, USB cable, browser print (any printer) or the RawBT Android app. 58mm / 80mm.
* Offline sales keep the same sale id (no duplicates), get VAT/discount on sync, rejected sales are no longer deleted.
* Receipt/sale times use local time (Africa/Harare; override with APP_TIMEZONE).

## Products
* Editing a product's price/cost works. Each variant can have its own price/cost; blank = same as product.

## Finance
* Fixed daily costs (day / week / month items), switch on/off, trading days, automatic daily charge, history.

## Customer feedback
* New Feedback page (nav item): star ratings, customer/product/source, follow-up flag for 1-2 stars, average + distribution, themes, draft replies.

## Other fixes
* pos.html curly quotes; base.html `biz` override (500 on POS/AI pages); several crashes on stale/bad input.
* Passwords are now stored hashed (existing logins upgrade automatically on next sign-in).
* Staff can no longer overwrite the manager account; permission checks on product/finance routes.
* offline-sync.js loaded twice; service worker now caches Bootstrap and is served from "/" so offline POS can work.
* App icons added; render.yaml has OPENAI_API_KEY; tzdata added to requirements.
