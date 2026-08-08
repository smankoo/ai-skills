---
name: send-to-kindle
description: >
  Send an epub/pdf/document to a Kindle end-to-end via Amazon's Send to Kindle email
  feature -- mail the attachment, wait for Amazon's verification email, and confirm the
  link automatically. Use when the user gives a book/document file and mentions
  Kindle, or asks to "send this to my kindle".
---

# Send a document to a Kindle (end-to-end)

Fully autonomous once the user's addresses are known. Given a file path and a mention of
"kindle", do the whole thing and report back. Don't ask the user to click anything --
the verification step is a plain link fetch, not a real approval action.

This skill carries no one's email addresses. Ask the user (once, then treat as settled
for the session) for:

- **Send-from address**: the mailbox you'll send the attachment from, and which mail
  tool/account can send from it (e.g. an MCP mail server, or `smtplib`).
- **Send-to address**: their Kindle email address (ends in `kindle.com`), from Amazon >
  Manage Your Content and Devices > Preferences > Personal Document Settings. It must be on their
  **Approved Personal Document E-mail List** (also on that page) as an approved sender,
  or Amazon will reject the document outright.
- **Verification-inbox address**: which mailbox receives Amazon's verification email.
  It is very often a *different* address/account than the one that sent the document
  (e.g. an alias, or a secondary account tied to the Amazon account) -- confirm this
  explicitly rather than assuming it matches the sender. Check that mailbox's Inbox
  *and* Trash/Deleted folder; mail rules or manual cleanup can move Amazon's mail out
  of the inbox.

## Key mechanics (verified against Amazon's flow, subject to Amazon changing it)

- **Verification is required on every send, from every approved address, with no way
  to turn it off.** Adding a sender to the approved list controls whether the
  attachment is accepted at all -- it does not skip the verification step. The
  verification is keyed to the document *request*, not the sender's approval status.
  Don't spend time trying to disable it; budget for the wait instead.
- **The verify link is a plain GET -- there is no button, form, or login required.**
  Fetching the `https://www.amazon.com/sendtokindle/verification/confirm/<ID>/<uuid>`
  URL *is* the confirmation; it returns a "Verified! Your document request has been
  successfully verified" page.
- Verification email typically arrives within **10-15 minutes** of the send. The link
  is valid for 48 hours.

## Steps

1. **Verify the file exists** and check its size. Amazon's limit is 50 MB per
   attachment. Supported formats: `.epub`, `.pdf`, `.docx`, `.txt`, `.rtf`, `.htm(l)`,
   `.png`, `.jpg`. (MOBI/AZW are no longer accepted.)

2. **Send it.** Subject = a clean human title for the book (derive it from the
   filename if it's a messy download name -- strip site tags, underscores, and IDs
   down to the actual title). Body can be a single newline; Amazon only cares about
   the attachment. Keep the original filename on the attachment.

   Send from the confirmed send-from address, to the user's Kindle email address,
   with the file attached, via whatever mail-sending tool is available.

3. **Poll for the verification email** in the confirmed verification-inbox account.
   Expect one on every send. Check **both** the Inbox and Trash/Deleted folders -- a
   verification email that never appears in the inbox is often sitting in the deleted
   folder because of a rule or prior cleanup, not because it wasn't sent. Sleep a few
   minutes between checks, up to roughly 25-30 minutes total before giving up.

   Search for a message from Amazon's automated sender address (a `do-not-reply`
   address at `amazon.com`) with a subject containing "Verify your Send to Kindle",
   searching from the send time onward. Watch for
   timezone drift: Amazon's timestamps are UTC, so an evening send in a
   negative-UTC-offset timezone can show as *tomorrow's* date -- search from a day
   before the send to be safe, and take the **newest** hit dated after your send.

4. **Extract the verify URL.** The plaintext body is enough. Pull the bare URL from the
   `Verify Request (...)` line: `https://www.amazon.com/sendtokindle/verification/confirm/<ACCOUNT_ID>/<REQUEST_UUID>`.
   Use that direct `amazon.com` URL, not a `.ca` (or other regional) click-tracking
   wrapper link that may also appear in the HTML part.

5. **Confirm it** by fetching the URL (a plain GET is enough -- no browser or login
   needed). Success looks like: "Your document request has been successfully verified
   and is now being processed." If it says expired/invalid, the 48h window lapsed or
   the request was already consumed -- re-send from step 2.

6. **Report**: book title, that it was sent and verified, and that it'll sync to the
   Kindle shortly.

## Notes / gotchas

- A browser isn't needed anywhere in this flow -- the verification link is a plain GET,
  so a direct HTTP fetch is sufficient and more reliable than driving a browser.
- If Amazon replies "Your email to Kindle(s) did not include any attachments," the
  attachment didn't survive the send -- re-send and confirm the mail tool reported a
  real attachment size (hundreds of KB or more, not near-zero).
- The real *failure* signal is an Amazon **error reply** landing in the send-from
  inbox (e.g. "did not include any attachments" / "There was a problem with the
  document(s) you sent"). Absence of a verification email is not a success signal --
  it usually means you searched the wrong folder or account.
- Sending multiple books at once: send them as separate emails (one subject per book)
  so each shows up with a proper title in the Kindle library; each gets its own
  verification email to confirm separately.
