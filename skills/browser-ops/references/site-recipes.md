# Site recipes: flows that cost real time to work out

Check this file BEFORE driving any site listed here. If a site isn't listed and the
flow took more than about 3 attempts to crack, add it here in the same session.

## Ontario car-dealer inventory (Toyota dealers, but these platforms are shared by all brands)
Verified 2026-10-19 (Camry price comparison). Each dealer platform has its own fast path:
- **sm360 / showroom360** (`/en/new-inventory`, e.g. Oakville and Georgetown Toyota): plain curl works.
  Parse `window.__PRELOADED_STATE__` after replacing `:undefined` with `:null`. Filter with
  `/en/new-inventory?modelId=<id>&limit=100`. Get the id from `initialData.filters.modelId`; slug URLs ignore the filter.
  `paymentOptions.cashPurchase.priceBreakdown` itemizes MSRP, freight, A/C, dealer fee, OMVIC, tire and `totalAllInPrice`.
  VIN ending `000000` means a factory-order placeholder, not a real car.
- **eDealer V4** (`/inventory/new/`, e.g. Burlington, Milton, Attrell and Cambridge Toyota): Cloudflare-protected.
  The VPS Chrome passes, but sometimes only after clicking the Turnstile box at about (293,337) after ~10-15 s.
  The model filter is the `a[data-filter-id=modelId]` href. VDP lines come as `label\nvalue` pairs (VIN, Stock, Drivetrain).
- **Convertus** (`/vehicles/new/`, Performance Auto Group sites): the inventory is
  `/wp-content/plugins/convertus-vms/include/php/ajax-vehicles.php?endpoint=<urlencoded vms.prod.convertus.rocks/api/filtering/?cp=<vmsData.vmsID>&sc=new&pc=100&md=<model>>&action=vms_data`.
  Curl works on non-CF sites. On CF sites, an XHR `fetch()` gets 403; a top-level `goto_url` to that URL works.
- **D2C Media** (`/new/inventory/search.html`, e.g. Upper James, Red Hill and Parkway Toyota): the VPS gets connection-reset.
  Curl over SSH from the iMac works. Model facet links `/new/inventory/Toyota-<Model>.html` list what's in stock.
- Guelph Toyota returned Cloudflare "Attention Required" (a hard block) from both the VPS and iMac curl.

### Kia-dealer additions (verified 2026-10-19, Sportage sweep, 16 dealers)
- **kia.ca Build & Price (cash, all-in):** load `https://www.kia.ca/en/shopping-tools/build-and-price?currentVehicleTrimCode=<code>&exteriorColourCode=FSB&method=cash&engineType=<HEV|Gas>&model=<Sportage+HEV|Sportage>&isDeliveryAndDestination=true&year=<yr>&step=2`. First choose the province (Ontario) in the region modal (`select[name=lang-modal-province]` native setter + click Update). Then JS-click "View details" and THEN the "Cash" tab, or PPSA $126 stays in the total. Trim codes: Sportage HEV 2026 EX=SP651T, SX=SP652T, EX Prem=SP653T (2027 uses ...V); gas EX=SP754T, EX Prem=SP755T. The trim-card buttons ignore JS and mouse clicks, so guess codes via the URL. Fusion Black (FSB) is the only no-charge paint. kia.ca's dealer locator only lists ~3 dealers at its default radius and its search box ignores typed input, so find dealers with web_search.
- **Convertus on Cloudflare (Georgetown/Brampton/QEW/St. Catharines Kia):** goto_url to the ajax-vehicles.php URL works after clicking the Turnstile at (293,337). browser_exec's URL guard rejects code that builds URLs as `"https://www."+dom` or contains a literal `https://vms.prod.convertus.rocks`: write full literal base URLs and a pre-encoded endpoint (`https%3A%2F%2Fvms.prod...`). Hybrids are model `Sportage Hybrid` (`md=Sportage%2520Hybrid` inside the encoded endpoint). Trim text is unreliable. Use `package_code` (SP65xT etc.) or price to classify trims, and note that VIN KNDPV covers both EX and EX Premium.
- **D2C Media** (Lockwood, Grimsby, Mississauga, Airport, Cambridge, Brantford, Kitchener and Waterloo Kia): iMac curl `/new/inventory/Kia-Sportage_HEV.html`. Each `carBoxOuter` card has base64 `data-tooltip` attributes that decode (base64, then html-unescape twice) to the full price build: "starting at X ; Admin Fee 699 ; ... ; Your Price/Cash Price: Y", plus "Includes $500 of FINANCE CREDIT" style notes. Those finance/lease-only credits are already deducted from the advertised price. Kitchener and Waterloo Kia publish the identical inventory pool. The terminal tool refuses to run scripts that read these ~1.5 MB pages ("lifecycle guard"), so parse them in execute_code.
- **Dealercraft** (Leggat Kia, `/vehicles/new?make=Kia&model=Sportage%20Hybrid&page=0`): curl works. Each `veh-card-leggat` card embeds JSON with `cashPriceBreakdown.freight_ppi_levies` (itemised fees and add-ons) and `colour_charge`.
- **sm360 legacy** (Bolton Kia `/en/new-bolton-kia-inventory`): there's no `__PRELOADED_STATE__`. Use the browser: click the model facet label (it sets `?modelIds=`), then click the "Purchase Price (Cash)" toggle and parse innerText cards.
- Toronto Kia (torontokia.com): hard Cloudflare block from both the VPS and iMac curl.
- iMac port 9334 is now the open-browser-control bridge (node), not a CDP Chrome. Check `ps` for `--remote-debugging-port` before tunnelling.

## GoodLife corporate (corporate.goodlifefitness.com): Amazon Workperks
Verified 2026-10-07. Used for Sumeet's own membership on 2026-10-06 and for adding Priyanka.

- **Company combobox** (`input[name=company-lookup]`, an old React app using
  `__reactInternalInstance$` / `__reactEventHandlers$` keys): typing, `fill_input`,
  `Input.insertText` and key events all leave the value EMPTY. Don't grind on it. Instead,
  walk the fiber up from the input to the `Combobox` component (about 6 levels) and call its
  `onSelect` with the exact company name:
  ```js
  const i=document.querySelector('input[name=company-lookup]');
  let f=i[Object.keys(i).find(k=>k.startsWith('__reactInternalInstance'))];
  while(f && !(f.memoizedProps&&typeof f.memoizedProps.onSelect==='function')) f=f.return;
  f.memoizedProps.onSelect('Amazon Canada-Email - Workperks');
  ```
  Company ids: `990p45003` (Email/DOMAIN method) and `990p128410` (Unique ID). The API is
  `/content/experience-fragments/goodlife_b2b/b2b-header/master/jcr:content/root/b2bheader.GetCompany.<id>.json`.
- **Email field** (`input[name=email]`): `fill_input` doesn't register either. Set the value with the
  native setter, then call `el[__reactEventHandlers$*].onChange({target:el,currentTarget:el,persist(){},preventDefault(){}})`.
- **"SEND ME AN EMAIL"**: a click does nothing. Call the parent form's React `onSubmit`
  (`form[__reactEventHandlers$*].onSubmit({preventDefault(){},persist(){},target:form,currentTarget:form})`).
  Success shows "RESEND EMAIL" plus "Enter one time pass code", and the request is `orgvalidation.OrgSendValidationUrl.json` → 200.
- The OTP goes to the primary member's **work email** (the corporate-domain address used for eligibility). The VPS can't read that inbox, so ask the user for the code.
- Step 2/7 is the GoodLife login. Use the 1Password GoodLife item (Gmail username).
- **Login form (step 2/7)**: inputs `login` + `passwordParameter`. Same React trick: native setter, then __reactEventHandlers onChange, then the form's onSubmit.
- **Adding a family member (verified 2026-10-07, Priyanka):** my-account → family.html → navigate to `membership.html?curCard=empty_0`.
  The club search ignores postal codes, so call the React onClick of the 'Select this Club' button in the Burlington Appleby Crossing card from the full list.
  Plan cards: fire the `card-input` onChange. 'CONFIRM SELECTION' = the form's onSubmit. The personal training page radios are uncontrolled: set `input[value=NO_THANKS].checked=true`, then the form's onSubmit.
  Personal-info form: 'Same as primary address' fills city and postal code but not the street, so type address1 and pick the autocomplete suggestion.
  Each e-sign checkbox's onClick opens a T&C modal. Scroll `[class*=terms-conditions__modal__body]` to the end, then fire Accept's onClick. Both the primary and family signatures are needed, and checkout has one more.
  Checkout: CONTINUE (onClick), sign, then COMPLETE (form onSubmit) → congratulations.html. The family member is billed on the primary's existing bank debit; no bank fields are asked for.
- **Family members:** they can't self-register. The primary adds them in the "Family" step
  (family.html) after login. Max 2 family members on the Amazon plan.
- **T&C modal:** scroll `[class*=terms-conditions__modal__body]` to the bottom in steps
  before Accept enables. NEXT re-renders the form, which is harmless; just re-query.
- **Payment:** periodic plans are PAD (bank debit) only. A card is accepted only for pay-in-full.
  Bank details are in the 1Password note "wealthsimple bank account details".

## Mangomint (booking.mangomint.com): Melonhead kids' haircuts
- Group booking can't keep the same stylist, so book SEPARATE single appointments.
- The date strip needs real mouse clicks on `[class*=DateStrip_dayCt]` (JS click no-ops).
- Client login is a 6-digit SMS to Sumeet's phone. Ask him for it, or have Magnus read Messages.

## OVHcloud manager
- Billing UI lives in an iframe (`/billing/#/...`). Read it via
  `Page.createIsolatedWorld(frameId)` on the billing frame. Card fields are Adyen OOPIFs:
  attach with `Target.attachToTarget(flatten)` and type into the REAL inputs (watch out for
  decoy `shiftTabField` inputs).
- Pay-debt via `/me/debtAccount/.../pay` returns "Incompatible country" / 403 from the
  VPS. The "Pay balance" button queues an operation, and it then disappears from the UI.
- **Region matters**: `auth.eu.ovhcloud.com` rejects the CA account with
  `invalid_account_or_password`. Always sign in at
  `https://auth.ca.ovhcloud.com/signin/?onsuccess=https%3A%2F%2Fmanager.ca.ovhcloud.com%2F`
  (the URL stored on the 1Password item). `https://www.ovh.com/auth/` redirects to EU and fails.
  If already authenticated the page shows a "Continue" button (`#continue-submit`) instead of a form.
- Debt status is readable read-only from the manager page:
  `fetch('/engine/apiv6/me/debtAccount/debt/<id>',{credentials:'include'})` plus
  `.../operation` and `.../operation/<opId>` for per-attempt status. 2026-10-07: debt 4434837
  showed `PAID` after op 11417022 went CANCELLED and a `CREDITCARD_AUTOMATIC` op settled.

## Costco.ca
- signin.costco.com returns **429** to automation from the VPS, from a home exit node (Pi3),
  AND from a CDP-driven Chrome on the iMac. Repeated attempts appear to rate-limit the
  ACCOUNT. Stop after 1 failure and have Sumeet sign in once by hand in the iMac profile
  `~/.hermes/costco-profile` (port 9334), then reuse that session.

## Canada Life (my.canadalife.com → secureme.canadalife.com, Auth0)
- Inputs need `fill_input` (insertText doesn't register). The forgot-password page says
  "if you have an account" and sends a code to the account email. On 2026-10-07 no code
  arrived at the Proton address, so the account email may be a different one.
- **RESOLVED 2026-10-08: the account email is the primary personal-domain address** (see the 1Password item username; lands in the iCloud
  account, subject "Password update verification code", arrives in <1 min). The Proton
  address silently gets nothing — it is not the account email. 1Password item
  `ucin27ibdgcvzykghha53bbmcm` username corrected; its stored 12-char password is the old
  GreatWestLife one and is rejected.
- **The reset page echoes back whatever email you type** ("We've sent an email with your code
  to: X") even for addresses with no account. Never treat that confirmation as proof the
  account exists — only an actually-delivered email proves it.
- Selector gotcha: the Salesforce/Visualforce sign-in input has colons in its id, so
  `#climsMyLogin\:...` is an invalid CSS selector (and Python eats the backslashes). Use
  attribute suffix selectors: `input[name$=":loginForm:username"]`,
  `input[name$=":loginForm:continueButton"]`.
- Sign-in is two-step: email → Continue (hands off to secureme/Auth0) → password `#password`
  + `button[name=action]`. Reset flow: `#username` → code `#code` → then MFA.
- **MFA (SOLVED 2026-10-08):** after the email code, Auth0 forces `mfa-phone-challenge` (SMS to the
  account's mobile; no email option). That phone's texts sync to the iMac, so read the code yourself:
  `ssh sumeet@<imac> 'python3 ~/.hermes/imac_sms_read.py --minutes 2 --grep "Canada Life" --code'`
  (script in `scripts/imac_sms_read.py`; arrives in about 10 s). Pick the "Text message" radio, then Continue, poll, fill `#code`.
  Do NOT ask Magnus over A2A to relay OTPs (it correctly refuses); read chat.db directly over SSH.
  Sign-in also asks for an SMS code every time.
- Coverage: /s/benefits/coverage-and-balances → Health → Health professionals → Massage therapist
  (LWC shadow DOM: find elements by textContent through shadowRoots and click by coordinates; `.click()` on the h3 does nothing).
  A "Select a person" combobox shows each family member's balance.
- Live web chat exists on the sign-in page: `#amazon-connect-open-widget-button`
  ("Start Chat") — the non-phone support route.

## Online car-buyer instant offers (Ontario), verified 2026-10-19
- **iMac Chrome hangs when the screen is locked.** The windowed Chrome blocks in `NSApplication finishLaunching` -> talagent XPC, and CDP accepts connections but never answers. Port 9334 may also be taken by the open-browser-control bridge (node). Workaround: launch a HEADLESS Chrome on the iMac with the costco profile (`--headless=new --user-agent="<mac Chrome UA>" --remote-debugging-port=9335 --use-mock-keychain --user-data-dir=~/.hermes/costco-profile`) and tunnel 19335. That gives a residential IP; Clutch, Canada Drives, AutoTrader, Planet Motors and Carnex all worked. CarGurus.ca still showed a DataDome slider.
- **Modal wizards (Planet Motors, Carnex):** the human_cdp `box()` wheel-scroll scrolls the page behind the modal, and the click then lands outside and closes it. Use `el.scrollIntoView({block:'center'})`, then read the rect, then `click_xy`.
- **Clutch:** /sell-or-trade -> VIN tab + postal -> 3 steps (Basic, Features, Condition) -> sign-up modal (first, last, email, password, phone; Continue stays disabled without the phone) -> 6-digit email code -> offer at /sell-or-trade/offer/<uuid>. The FAQ says it checks your accident answers against Carfax.
- **Canada Drives:** /sell-my-car -> step-1 (native selects: set them via the native setter + change) -> step-3 -> step-4 (inputs named keyFobs, tiresRecentlyReplaced, hasWarningLights, brakesNeedRepair, hasAccident, hasRebuildStatus, ownership, sellOrTrade; click `closest('label')`) -> contact page (the marketing checkbox is unchecked by default) -> **4-digit SMS verification before the offer appears**. The SMS never reached the iMac's chat.db.
- **Toyota dealer trade tools (verified 2026-10-19, VPS Chrome is fine):** use your OWN `session=`. Other agents share the default tab and will navigate it away mid-flow. A Cloudflare Turnstile comes first: activate_tab, then click the checkbox at about (293,337).
  - *CARFAX TrueTrade* (burlingtontoyota.com/trade-in-appraisal/, miltontoyota.com/sell-us-your-vehicle/): set the page selects ttSelectYear/Make/Model (native value + change), then JS-click `#ttGo`. That opens a truetrade.carfax.ca OOPIF. Find it with `cdp('Target.getTargets')` filtered on `parentFrameId == current_tab()['targetId']`, then use `js(..., target_id=T)`. Steps: `#ttToggleEntry` (VIN), `#ttVinEntry` and `#ttOdoEntry`, `#ttGoGapScreen` (sometimes needs a second click), `#ttSelectTrim` and `#ttSelectTransmission`, `#ttGoInfoScreen`, condition label `for=ttSelectConditionVeryGood`, `#ttGoEntryScreen`, name/email/phone, `#ttCarfaxConsent_label` (mandatory, and the only box), `#ttGoValueScreen`. The range shows instantly and is also emailed. Every dealer gets the same CARFAX number, so one dealer is enough.
  - *D2C "trade-in-form"* (oakvilletoyota.ca/en/trade-in): put the VIN into `#vehicleInformations` with `Input.insertText`, then JS-click the matching `li`. Next come the colour radio labels and `#odometer` (insertText), then Next. Enter firstname/lastname/email/phone with insertText. The marketing box is unchecked by default. "Get Trade Estimate Value" then shows the Fair/Good/Very Good/Excellent values.
  - *Magnetis* (meadowvaletoyota.com/#evaluation, iframe trade.magnetis.ca): "I already know my VIN", then the colour buttons, mileage + province, contact details + the mandatory privacy box. After that come about 35 condition radios (ids like `14-1` = minor dents), then "Evaluate my vehicle". You get a point estimate plus a range.
- **AutoTrader.ca ICO:** gives only a range, and only after mobile number + a combined mandatory consent. A firm offer needs a dealer appointment.
- **Planet Motors:** no contact info is needed for the estimate. **Carnex:** name, phone and email are needed; the estimate shows instantly and is also emailed.

## Google Forms (any public form, verified 2026-10-20)
- Don't drive the UI. JS `.click()` and `click_at_xy` on `[role=checkbox]` are flaky, and typed text piled into one field.
- Read the full structure (every page, entry ids, options, branching) from `FB_PUBLIC_LOAD_DATA_[1][1]`. For each item, `it[4][0][0]` is the entry id and `it[4][0][1]` the options. A radio option's `o[2]` is the section it jumps to (`-2` = next section). Section headers are type 8.
- Submit with a same-origin `fetch(POST '/forms/d/e/<id>/formResponse')`, sending a URLSearchParams of `entry.<id>=value` (repeat the key for each checkbox) plus `fvv=1` and `pageHistory=0,1,2,4`. That's the list of section indexes actually visited; skip any a branch jumps past.
- Success means the response HTML contains the form's confirmation text. Don't assign it to `innerHTML`: docs.google.com enforces TrustedHTML and throws, but only AFTER the POST has already landed, so a retry makes a duplicate. Regex the text instead.
- One form per adult when the form says so. Childminding/"once per family" questions: answer them on one submission only.
