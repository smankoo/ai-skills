# Site recipes: flows that cost real time to work out

Check this file BEFORE driving any site listed here. If a site isn't listed and the
flow took more than about 3 attempts to crack, add it here in the same session.

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
- The OTP goes to **smankoo@amazon.com**. The VPS can't read that inbox, so ask Sumeet for the code.
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
