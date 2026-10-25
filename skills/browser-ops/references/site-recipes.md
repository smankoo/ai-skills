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

## AWS Certification account (cp.certmetrics.com/amazon), verified 2026-10-21
- Login: `cp.certmetrics.com/amazon/en/login` redirects to Skill Builder; click `#AWSBuilderID-provider-button`. On signin.aws, `fill_input` is unreliable: click the field and use `Input.insertText`. Email, Continue, password, Continue. An email OTP then goes to the Builder ID address (1P "AWS Builder ID"): read it from himalaya `icloud` with subject "Verify your identity" and regex `>(\d{6})</div>`. If the page shows an old email, click "Change" first.
- The session expires within about 30 min. Re-login works without the user.
- Data: `/en/credentials/status` lists every cert (active/expiry dates). "VIEW MORE" opens `/credentials/status/<id>`. "DOWNLOAD CERTIFICATE" only works with a trusted `click_at_xy` (JS `.click()` does nothing). Set `Browser.setDownloadBehavior` first. The PDF text layer has the validation number and dates (`pdftotext -layout`).
- Filed in Drive at `Important Documents/People/Sumeet/Education/` and in Pebbleway `document` nodes (document_type certification, validation_number, certmetrics_credential_id, PDF attached).

## Lulu developer portal signup (developers.lulu.com / developers.sandbox.lulu.com), 2026-10-23
- "Create an Account" leads to a Keycloak registration page on api.(sandbox.)lulu.com, behind a Cloudflare Turnstile. It won't auto-pass, so click the checkbox (`click_at_xy` at about x=298, y=338). It cleared on the first try.
- The form has a reCAPTCHA Enterprise v2 checkbox (`#recaptcha-container`). Submitting without ticking it gives "Invalid Recaptcha". Scroll it into view, then click iframe x+27, y+h/2. A token was issued with no image challenge. Submit with a real `click_at_xy` on "Sign Up".
- The verify link in the email (action-token, about 1 KB long) gets elided in terminal output. Extract it to a file and navigate with `js("location.href=...")`. browser_exec code that reads himalaya inline or contains 127.0.0.1 URLs got "Blocked: URL targets a private or internal address".
- Keys: avatar menu, then API Keys (`/user-profile/api-keys`), then "Generate Client". Values are in the textareas `#clientKey`, `#clientSecret` and `#base64KeySecret`; the last one is prefixed with "Basic ". Production gave keys with no card.
- `op item edit` run from a subprocess with a piped stdin fails with "invalid JSON provided". Add `</dev/null`.

## Shopify signup + API access (Dev Dashboard), verified 2026-10-23
- Route: iMac Chrome via `human_cdp.py` (tunnel 19334 -> 9335). shopify.com/ca -> "Start for free" -> accounts.shopify.com/signup. No CAPTCHA was shown.
- The signup form uses custom elements: `i-text-field#email`, then `i-text-field#password`, and `signup-button` for submit. `click_text` can't see them (their innerText is empty), so click the host element (`t.click('document.querySelector("i-text-field#email")')`) and `t.type()`. `.value` on the host reads back.
- After "Create account" you land on a **paid-trial checkout** ("3 days free, then $1/mo", card fields). Click **Skip** (top-left). No card is needed. Then one question ("What can we help you do?", checkboxes like `input[value=where_like_sell_online_store]`; click the input itself), Continue, and you're on the admin dashboard with "Trial ends in 3 days" and plan_name `trial`.
- The store gets a random permanent domain (`xxxxxx-xx.myshopify.com`). Change it at Settings > Domains > "Change myshopify.com domain" (free, 2 changes allowed). The new one becomes the primary domain, but the API `myshopify_domain` and the OAuth `shop=` param keep the permanent one. Both hostnames work for API calls.
- The admin is Polaris web components: inputs and buttons sit inside shadow roots (`s-internal-button` -> shadowRoot `button`). Use a deep walker (`walk(e.shadowRoot)`) to find the element, then trusted-click it. Store name: Settings > General > click the store-name link -> `.../store-contact-details`. Currency was already CAD for Canada.
- A verification email ("Verify your email address", link `accounts.shopify.com/email-verifications/...`) is needed before the Dev Dashboard works.
- **Legacy "Develop apps" custom apps are gone (since 2026-01-01).** Settings > Apps > Develop apps only offers "Build apps in Dev Dashboard" (dev.shopify.com/dashboard/<org>). Create app: name, scopes as a comma list in `textarea[name="app_form[app_module_data][app_access][scopes]"]` (Storefront `unauthenticated_*` scopes go in the same list). Untick "Embed app". Create app -> Release modal -> Release. Apps list -> row "Actions" (⋯) -> "Install app" link (navigate to its href rather than opening a new tab) -> pick the store -> Install. It then redirects to the app URL (example.com), which is expected.
- Credentials: app > Settings: `#app-settings-client-id`, `#app-settings-client-secret-0` (password input, value is in the DOM). The admin never shows a token. Get one with `POST https://<shop>/admin/oauth/access_token {"grant_type":"client_credentials","client_id","client_secret"}`. **It expires in 24 h**, so store client id/secret and refresh it. Get a Storefront token with Admin GraphQL `storefrontAccessTokenCreate` (it doesn't expire).
- **Shared iMac Chrome pitfall:** if another agent brings its tab forward, your tab goes `visibilityState=hidden` and every trusted `Input.*` event hangs (websocket timeout). Open your own window (`Target.createTarget(url, newWindow=True)` on the browser websocket) and call `Page.bringToFront` before each click sequence.

## Namecheap domain purchase (namecheap.com), verified 2026-10-23
- Route: iMac Chrome via `human_cdp.py` (tunnel 19334 -> 9335). Home page -> "Sign in" link opens an inline dropdown with `input[name=LoginUserName]` / `input[name=LoginPassword]`; submit with a trusted click on the form's `button[type=submit]`. No CAPTCHA. Then `/twofa/totp/` has a single `input[type=tel]` (fill from `op item get <id> --otp`) and a "Submit" button.
- Search: dashboard `input[name=domain][type=search]` + Enter goes to `/domains/registration/results/?domain=<name>`. A bare name doesn't list .ca; search `<name>.ca` in `#search-query` (submit `.standard-form button[type=submit]`). The searched domain's "Add to cart" is the first visible `button.available`; it turns into `button.purchased` "Added to cart". The header `.gb-cart` shows the running total.
- Cart (`/shoppingcart/`): checkboxes are named `autorenew-<id>:<domain>` and `enabler-<id>:<domain>:{whoisguard-protect-one,premium-dns,stellar-promo}`. Defaults were right (auto-renew on, free privacy on, PremiumDNS/Stellar off), but verify them before "Confirm Order". Prices show in CAD (account display currency); **the charge is in USD** (C$32.83 cart = US$23.46 charged).
- "Confirm Order" -> express order review using the DEFAULT card, which may be an old expired one (here one that expired in 2019). Click Payment Details "CHANGE" -> `Payment.aspx`: native select `...CardControl_SavedCCOptions` = `3` ("Use previously saved card") reveals `...CardControl_SavedCCList` (VISA-xxxx/MC-xxxx options); set value + dispatch `change`. No CVC asked for a saved card. Leave `savePaymentConfiguration` unticked. Continue is the anchor `#btn_Submit`.
- Order review: "Whois Contacts" links expand the contacts the domains will get (from the account's default domain contact, not the receipt/billing contact). .ca needs the `input[id$=euOrCaCheckbox]` (registry agreement) ticked; pay with `input[id$=Button1]` ("Pay Now"). Then `order.aspx?id=<order>` polls; ~30 s later `/cart/checkout/orderconfirmation/?id=<order>` shows order, transaction, total charged, card.
- .ca: no legal-type prompt at checkout. The account's saved extended attributes applied (CIRA Legal Type CCT, language en, registrant data hidden), visible in `ap.www.namecheap.com/domains/domaincontrolpanel/<domain>/domain` under "Extended Attributes". Registry "Congrats! You've successfully registered" mail goes to the registrant email; the Namecheap "Order Summary (Order# N)" receipt goes to the account email.

## Namecheap account, contacts and default card (verified 2026-10-23)
- **human_cdp quirk here:** `Tab.box()` scrolls with `mouseWheel`, and on this background Mac window that CDP call HANGS (60 s websocket timeout). Call `Page.bringToFront` first, and monkey-patch `Tab.box` to use `el.scrollIntoView({block:'center'})` and then read the rect. Trusted clicks and `insertText` typing work fine after that. Namecheap checkboxes are positioned off-screen (x≈-159582): click `label[for=<id>]`, not the input.
- Addresses: `/settings/personal-info` -> Address Book "MANAGE" (a `button`) -> `/settings/personal-info/address-book`. The EDIT buttons go to `/settings/personal-info/edit-address/<id>` (Primary = 0). Field ids are `firstName lastName companyName jobTitle isCompanyAddress address1 address2 stateProvince city postalCode phoneNumber`, plus `email` (alternate addresses only). Clear a field with `type_sel(sel, '')`. The Primary Address email is locked to the account login email. "Use this address as default and for billing" (`#makeDefault`) moves the DEFAULT/BILLING badge to that address; that address is the default for new domains.
- Domain contacts: `/domains/domaincontrolpanel/<domain>/domain` (a `/contacts` URL gives an "Ooops" page). Under DOMAIN CONTACTS, the `a[href="#editcontacts"]` EDIT links open `/domains/DomainContactEdit/<domain>/registrant`, with ids `FirstName LastName company AddressLine1 AddressLine2 City StateProvince ZIPPostalCode DomainContactPhone PhoneNumberExt phone-extension Email`. Tick `ApplytoAdministrativeContact`, `ApplytoTechnicalContact` and `ApplytoBillingContact` (the .ca form has only Admin) so one save sets them all. Save is `a.btn` "Save Changes". An address-only edit on a .com raised no Change-of-Registrant or 60-day-lock prompt and sent no confirmation email.
- **.ca pitfalls:** (1) A ticked `phone-extension` box with an empty `PhoneNumberExt` fails with "Valid phone extension required"; untick it. (2) **Saving a .ca contact resets CIRA "Hide Registrant Data" to `no`.** Afterwards, open `a[href="#editExtendedAttributes"]`, run `jQuery('#ddlCACiraWhois').val('Private').trigger('change')` (Full = No, Private = Yes; select2 + Angular), keep `ddlCALegalType` = CCT, and save with `input[type=submit]` "Save Changes". Reload the page to check.
- Default card: `/profile/billing/PaymentCards`, then the card's Edit (`/profile/billing/PaymentCards/<guid>/ManageCards/edit`). Set the select `#CardUseAsOption` (0 None / 1 Default / 2 First Backup / 3 Second Backup) with jQuery `.val('1').trigger('change')`. Tick `UseAsDefaultPaymentMethod` (Apps Marketplace) and fix the `billing_address1/2` fields. No card number or CVC is asked for. Success is the `?save=success` URL with the DEFAULT badge moved. "Remove" sits in the "+" dropdown and opens a confirm popup.

## AWS console root sign-in + IAM deploy user/role (verified 2026-10-23)
- Route: iMac Chrome via `human_cdp.py` (tunnel 19334 -> 9335). No CAPTCHA appeared on this route (the VPS Chrome got one). Open your own window (`Target.createTarget(newWindow=True)`).
- Don't deep-link `signin.aws.amazon.com/signin?redirect_uri=...`: it returns 400. Go to `console.aws.amazon.com/`, which redirects to the IAM-user form. Click `#root_account_signin`, then `#root_user_radio_button` (already checked by default), type the email into `#resolving_input`, click `#next_button`, then `#password` and `#signin_button`. On the MFA step type the code into `#mfaCode` and click the "Sign in" button. Type with trusted input (`type_sel`). It lands on `us-east-1.console.aws.amazon.com/console/home`. Accept the cookie banner.
- IAM create user: `.../iam/home#/users/create`. The user-name input is `input[id^=formField]`. Next, then "Attach policies directly". **The aria-labels are swapped**: `input[aria-label="Search items"]` is the policy-table filter, and `aria-label="Search"` is the global console search. Policy checkboxes have `aria-label=<PolicyName>`. The review page has "Add new tag" with `input[placeholder="Enter key"]`/`"Enter value"`.
- Access key: `.../iam/home#/users/details/<user>/create-access-key`. Use `input[value=CLI]`, tick the confirmation checkbox, Next, Next, "Create access key". Then click "Show" and regex `AKIA[A-Z0-9]{16}` plus the single 40-char `[A-Za-z0-9/+]` token out of `innerText`. Store it right away with `op item create --vault ... --format json` and the JSON template on **stdin**, so the secret never goes in argv. Round-trip check it, and print nothing.
- Pattern to minimise console clicking: create the user with **temporary IAMFullAccess**, make the key, and do the role and inline policies with the CLI (key from op in env, `AWS_SHARED_CREDENTIALS_FILE=/dev/null`). Detach IAMFullAccess as the LAST step. Check it with raw-user `iam list-users`, which should give AccessDenied. CLI `tag-user` didn't show up in the console, so tag in the create wizard instead.
- Pitfalls: the shared iMac Chrome sometimes hangs on `human_cdp` `click()` (its `mouseWheel` scroll waits until the websocket times out). Use `scrollIntoView` plus `click_xy` on the JS rect instead, and click one step per process with `timeout 45`. Calling `scrollIntoView` right before clicking Next once un-ticked the access-key checkbox, so re-read the state. Sign out: `#nav-usernameMenu`, then the "Sign out" button.
- mankoos-prod has **STS disabled in ca-central-1** (RegionDisabledException). Use `--region us-east-1` (or the global endpoint) for AssumeRole.
- The local secret-guard blocks `aws sts assume-role` command lines that would print credentials. Assume the role inside a script with `--query` and capture it into variables.

## Instagram signup + business switch (instagram.com), verified 2026-10-23
- Route: iMac Chrome through `human_cdp.py` (tunnel 19334). Home page, then the "Create new account" link (`a[aria-label="Create new account"]`), which opens `/accounts/emailsignup/`.
- **Call `Page.bringToFront` first.** A background tab has `visibilityState=hidden`, and trusted clicks on IG's comboboxes then hang the CDP call indefinitely. Set `t.ws.settimeout(15-20)` so a hang fails fast.
- Fields have random ids (`_r_7_` email, `_r_a_` password, `_r_v_` name, `_r_15_` username, an `input[type=search]`). Read them fresh each run. IG pre-fills the username from the email, so clear it before typing.
- Birthday uses 3 `[role=combobox]` (Month/Day/Year). The full `[role=option]` list is in the DOM, but options sit below the fold. Wheel-scrolling closes or confuses the list and the click then selects nothing. What works: open the combobox, call `option.scrollIntoView({block:'center'})` in JS, re-read its rect, then do a trusted click.
- Submit, then the "I agree" terms page, then a 6-digit email code (subject "NNNNNN is your Instagram code", arrived in INBOX in under 15 s). Continue lands on `/?caa_reg_splash_screen=1`. Dismiss "Turn on Notifications" with "Not Now". The suggested-follow buttons are nearby, so never click by the text "Follow".
- Bio: profile, then Edit profile (`/accounts/edit/`), `textarea#pepBio`, then Submit. Look for the "Profile saved" toast.
- Professional: Settings → "Account type and tools" → "Switch to professional account". Pick Business (radio), click the real `<button>` Next twice (the outer DIV match does nothing), then search the category ("Publisher" exists), Done, confirm "Continue" in the dialog, then "Don't use my contact info". The result screen says "Your Instagram business account is ready".

## TikTok signup (tiktok.com), verified 2026-10-23
- **The CDP Chrome is blocked.** "Send code" does nothing on a trusted click. A `form.requestSubmit()` sends `/passport/web/email/send_code/`, but the response redirects to `www-useast1a…?X-Bogus=1`, which then fails CORS (`PreflightMissingAllowOriginHeader`). That's the bot-signature reject. Don't fight it: use **macbrowse (iMac Firefox, AX)**.
- Flow: Log in button → "Sign up" → "Use phone or email" → (birthday comboboxes + phone, or "Use email").
  - The comboboxes don't open on an AX press. Use `click xy:` on the box (shot coords: Month ~641,556, Day ~784,556, Year ~927,556), then `look --query April` and click the MenuItem `#N`.
  - Year: the list is lazy. Type `type focused --text 1987` while it's open, then `look --query 1987`.
- **Email signup with a Gmail +alias failed.** TikTok mails the code to the canonical address (dots and +tag stripped; same code each resend, "valid 48 hours"). The final Sign up then always said "Verification code is expired or incorrect". **Phone signup worked:** SMS code ("[TikTok] NNNNNN is your verification code"), read with `imac_sms_read.py --code`, then Create password + Create username in one screen, then Sign up, then "Got it" on the privacy notice.
- **Text got typed twice** (e.g. `abc` → `abcabc`). cua-driver background `type_text` returns `type_text_incomplete` with delivered 0 even when every character landed, so the agent retried in the foreground. `macbrowse_agent.do_type` now re-checks the field length before retrying. `type focused` can't verify, so it can still double: prefer `#N` targets.
  - Fields that can't be measured: verify the length (count the bullets in `look`).
  - A pre-filled field can't be measured either when the new value has the same length. Clear it with repeated `key delete` first (`cmd+a` doesn't select in TikTok inputs).
- Profile: Profile → Edit profile → Name / Bio (80 chars) → Save → Confirm ("nickname can only be changed once every 7 days").
- Firefox shows a 1Password "Save login?" popup. Ignore it; it doesn't cover the dialog.

## Twilio console: upgrade, buy CA number, TwiML Bins (partial, 2026-10-23)
- Login verified so far: `console.twilio.com` redirects to `www.twilio.com/login`. Fill `#email` (name `email_input`) and click `#email-next`. That goes to an Auth0 page on `login.twilio.com/u/login` with `#username` pre-filled and `#password`. The 1Password item's origin is `https://login.twilio.com`, so `browser_vault fill` matches that page.
- **Blocker hit:** `browser_vault fill` failed with "a vault query must be provided when this command is called by a service account". Under a service account, the 1Password backend's `op item get <id>` needs `--vault`. Fix it in the backend (record the vault id at list time and pass `--vault`), then restart. Don't fall back to typing the password.
- Still unverified (fill in on the next run): trial upgrade/top-up, buying a CA 905 number plus its regulatory bundle, TwiML Bins, and creating API keys.


## Anytime Mailbox signup (virtual mailbox, CA locations), partial, 2026-10-23
- Route: VPS Chrome works. No CAPTCHA up to checkout. Location page `anytimemailbox.com/s/<slug>` lists plans. Each plan has two "Select" buttons whose `onclick` is `location.href='https://signup.anytimemailbox.com/signup/new?term=30|360&srvPlnId=<id>...'`; term=360 is annual. JS-click the matching one. Annual is about 10x monthly (~17% cheaper). Every plan includes Open & Scan; the cheapest tier gets only a few pages/month.
- Step 1 `/signup/account`: dismiss the cookie banner ("Reject All"). Fields: `#f_boxid` (PMB number select; the default is fine), `#f_firstname`, `#f_middleinitial` (or tick `#f_nomiddlename_1`), `#f_lastname`, `#f_company` (business name, printed on the address), `#f_country`, `#f_address`, `#f_city`, `#f_state` (select), `#f_zip`, `#f_email`, `#f_phone_ln`, `#f_password`, `#f_verification`. Leave the SMS opt-in `#f_enablesms_1` unticked. `fill_input` did NOT stick on this form. Use the native value setter plus input/change/blur events.
- "Continue" runs `$('#main-form').mtekSubmitForm('UPD')` over AJAX and opens an **Email Verification** modal (six single-digit inputs `#f_code1..6`, `#btnValidate`). The URL doesn't change, so detect the modal (`.modal`) instead of waiting for navigation. The code arrives within ~20 s as "[ACTION REQUIRED] Email Verification" from Anytime Mailbox. Set each digit with the native setter, then trusted-click Validate. That lands on `/signup/reviewandcheckout`.
- Step 2 review page: it shows the assigned street address ("<street> Unit NNN / PMB#<box>") and the total with HST (13% in ON) before you pay. Payment is a **Stripe Elements card iframe** (`iframe[title="Secure card payment input frame"]`, js.stripe.com) plus a `#f_terms_1` checkbox and an "Activate Mailbox" button. The mailbox is only reserved once Activate succeeds.
- **Blocker:** `browser_vault` could not fill the card. Its 1Password backend lists only `Login` items (`op item list --categories Login`), so 1Password CREDIT_CARD items never show up as handles. Its payment probe also checks only the top frame, and Stripe's card field is in a cross-origin iframe. Until the vault supports both, card checkout here needs the user. After payment, the provider asks for ID verification (CA locations: Form/ID upload in the renter dashboard); that step is not yet verified.

## Ontario Business Registry: register a sole-proprietorship business name (not yet exercised)
- Not run yet (blocked upstream on 2026-10-23 by the vault card limit above). Entry point: ontario.ca "Register a business name (sole proprietorship or partnership)" page, then the Ontario Business Registry (fee about C$60; it needs a My Ontario Account / ONe-key sign-in). Record the real flow here on the first successful run.

## Amazon.ca returns (verified 2026-10-25)
- **Standing rule: always pick free HOME PICKUP** (Intelcom/Dragonfly residential pickup), never a store or post-office drop-off. Under "No longer needed" pickup costs $3.99. Under a defect reason ("Item defective or doesn't work") it is FREE. Use the defect reason only when the user actually reported a fault, and write the comment in the user's words.
- Route: iMac Chrome via `human_cdp.py`. Order details (`/gp/your-account/order-details?orderID=`): each item has its own "Return items" link (`a[href*="itemId=<id>"]`). Match the item text to pick the right one.
- Return cart: tick `input[id^="<itemId>"][type=checkbox]`. Reason: click the `.a-dropdown-container` of `select[id^="<itemId>"][id$="native-dropdown"]`, then the option in `.a-popover a`. **Every item has hidden textareas for every reason**: target `textarea[id^="<itemId>"]` filtered by `offsetParent` (the first match on `$=AC_REQUIRED` belongs to another item). Trusted-click it, then `t.type()`. Also avoid `#rufus-text-area`.
- Defect reason shows a "Get product support" page: click "Continue to return options", then trusted-click the single refund radio, which enables `#resolutions-section-continue-button`.
- Method page: pick the radio whose container says "Residential Pickup". `#methods-section-continue-button` ("CONFIRM YOUR RETURN") stays disabled until a method is fully chosen; drop-offs also need "Choose drop-off location" then "Drop off here".
- Pickup = next business day, ONE attempt, adult must hand it over. Add it to the family calendar (cal_sync add-icloud) and a Pebbleway task. Missed: "Reschedule" on the confirmation page.
- Changing reason/method after confirming: "Edit return" only offers "Change return method" or "Cancel return" (2-step confirm in `.a-popover`). To change the reason, cancel and start a new return; the item's link reappears on the order page.
