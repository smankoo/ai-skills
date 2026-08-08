---
name: book-car-service
description: >
  Book a service appointment at a car dealership through its online scheduler, then
  optionally log it to a personal-records system and a calendar. Use when the user
  asks to book/schedule car service, or their vehicle's app/dashboard shows a
  "service due" notice. Especially useful when the dealer's scheduler is a Keyloop
  "SWA" widget (common across many franchise dealers) embedded via a cross-origin
  iframe, which browser automation needs to target directly rather than through the
  dealer's marketing site wrapper.
---

# Book a dealership car-service appointment

This skill carries no one's name, phone number, VIN, dealer, or account IDs. All of
that comes from the user or their own connected records at run time. Ask for
whatever isn't already known:

- Which car (make/model/year), and its current odometer reading.
- Which dealer, and whether the user is an existing customer there.
- Any personal-records system (e.g. a notes app, task tracker, or custom MCP) to log
  the appointment to afterward.
- Which calendar to add the appointment to, and the exact calendar name if the user
  has more than one similarly named calendar.

## Finding and driving the real scheduler

Many franchise dealers (Kia, Hyundai, and others) use a **Keyloop "SWA"** (Service Web
Appointments) widget for online booking. The dealer's own marketing page
(`<dealer>.com/.../service-appointment.html` or similar) usually just embeds this
widget in a cross-origin `<iframe>`. Browser automation tools generally can't reach
into a cross-origin iframe's DOM from the parent page's context, so:

1. Load the dealer's service-appointment page and find the iframe `src` -- it points
   at a URL shaped like `https://<dealer-subdomain>.sdswebapp.com:<port>/appointments/launch?dealerId=<id>&code=<brand-code>`.
2. **Navigate the browser directly to that iframe URL**, skipping the wrapper page
   entirely. This is what makes the DOM inspectable and clickable.

If the dealer uses a different scheduling vendor, look for the same pattern (an
embedded booking widget from a third-party subdomain) before assuming automation
won't work -- driving the widget's own URL directly is usually the fix.

## Wizard flow (typical shape; adapt to what's actually on screen)

1. **Customer lookup**: existing customers can usually search by phone number and
   jump straight to their vehicle on file, skipping name/address entry until a final
   review step.
2. **Vehicle + odometer**: selecting the vehicle usually opens a modal asking for the
   current odometer reading. Use the latest reading available (ask the user, or read
   it from their vehicle app/records) -- don't leave a default/placeholder value in
   place.
3. **Service package selection**: dealers often rotate a small set of maintenance
   packages by distance interval (e.g. every 6,000 km/miles), not a strictly repeating
   single package. If the manufacturer's maintenance schedule isn't obviously
   labelled, ask the user for it or infer the pattern from the package names shown
   (e.g. "Service 1/2/3/4") plus the last-serviced odometer reading shown in the
   wizard. Pick the engine/trim-specific variant if the widget offers multiple (e.g.
   different cylinder counts for the same model). After selecting a package, confirm
   it actually landed in the cart/total before moving on -- some wizards close the
   detail modal without adding the item if you click "Next" instead of the explicit
   add button.
4. **Appointment details**: advisor selection, transport/loaner preference (e.g.
   waiter / drop-off / drive-back / shuttle), and a calendar of available slots.
   The calendar/slot picker often only appears after transport mode is chosen. Verify
   the header summary reflects the choice actually made -- some pickers mis-register a
   click as selecting a specific option when "no preference"/"first available" was
   intended.
5. **Review and submit**: fill in contact details, choose a confirmation method
   (email/SMS), and submit. Confirm success via the resulting confirmation
   dialog/page, which usually restates the date and service summary.

Browser-automation notes: these widgets are often React/MUI single-page apps.
Standard `<select>`-element queries can return nothing against a MUI custom select --
use the accessible DOM/role tree instead. If relying on screenshot coordinates, factor
in the displayed-vs-actual image scale, and verify each click landed correctly before
proceeding, especially on calendar grids.

## After booking

1. **Log it** to whatever personal-records system the user has, if any -- include
   date/time, package, price, advisor, transport mode, and odometer in the notes.
2. **Add it to the requested calendar**, using its exact name (confirm if the user has
   more than one similarly named calendar) -- a 1-2 hour block depending on whether
   they're waiting on-site, with the service details in the description.
3. **Report back**: date/time, package + price, advisor, and the reasoning used to
   pick the service package.

## Gotchas

- A vehicle's "preferred dealer" on file may differ from where the user actually wants
  to book -- confirm rather than assuming, especially if the car was purchased through
  a different dealer group than the one servicing it.
- Dealer perks (free wash, shuttle, loaner) are frequently weekday-only; recalls
  usually require a phone call rather than the online scheduler. Mention these if they
  come up on the booking page rather than assuming the online flow covers everything.
