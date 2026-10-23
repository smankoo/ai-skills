---
name: picture-book-maker
description: Use when Sumeet wants a NEW illustrated picture book made for the kids (Tegh, Kirat) — a Tractor Mac, Tractor Ted, Daniel Tiger, Paw Patrol or any other story, starring family (Tegh, Kirat, Priyanka, Sumeet, Daadi, Daadu) as characters — or a sequel, a page redo, or cheaper book art. Writes the story, paints consistent characters with Gemini via OpenRouter, auto-judges each page, typesets and imposes a print-ready saddle-stitch booklet. Also use for "make a book about…", "put Kirat in a story", "another Tractor Mac book".
metadata:
  hermes:
    tags: [kids, books, printing, image-generation, family]
    related_skills: [reading-and-ebooks, personal-shopper]
---

# Picture book maker

Sumeet prints these at home on the Brother laser and staples them into booklets for Tegh (4½) and Kirat (~20 months).
The first book, *Tractor Mac and Tegh's Big Day* (Oct 2026), cost $24 to make; with this pipeline a 28-page book
should cost **$2–4**. Quality is never traded for cost — Sumeet said so explicitly — so use as many illustrations as
the story needs; save money by not wasting tries, not by skipping pictures.

Everything is driven by one CLI: `scripts/pbook.py` (run with `--help`). Data is private (kids' photos) and lives
outside the repo in `~/.hermes/data/kids-books/` — never copy photos or sheets into this skill.

```
~/.hermes/data/kids-books/
  config.json            image/judge models (defaults are in pbook.py DEFAULTS)
  cast/<id>/             cast.json (name, role, description) + sheet.png (+ photo.*)  — reused across books
  series/<id>/           series.json (painting style, series rules) + refs/*.png
  books/<slug>/          story.json, art/, art/tries/, qa.json, book.pdf, "<Title> - BOOKLET …pdf"
```

## Workflow

1. **Story first, in chat.** Pitch 2–3 one-line plots that fit the child (interests, upcoming events, a lesson they're
   learning). Write age-appropriate text: 1–3 short sentences a page, read-aloud rhythm, sound words for fun
   ("CRUNCH!", listed in `story.json` `sfx` so they're set in red). 28 pages is the sweet spot (7 sheets); the page
   count must be a multiple of 4. Standard frame: 1 cover, 2 belongs-to, 3 title, 4–25 story, 26 "The End",
   27 dedication, 28 back cover.
2. **Cast.** Every person needs a character sheet before any page is painted — it's what keeps faces identical from
   page to page. `cast-add <id> --name --role --desc "<look + fixed outfit>" --photo <photo>`. The description is
   repeated on every page prompt, so make it concrete (skin tone, hair, outfit colours). Ask Sumeet for **all**
   missing photos in one message (one clear, front-on photo each). Check the sheet with vision before using it:
   wrong skin tone and generic "East Asian" features are the usual failure for the kids — regenerate with the
   photo as the first reference. Series characters (Mac, Daniel Tiger…) are cast too: make their sheet from the
   series reference pages (`--series <id>`, no photo).
3. **Series style.** `series-add <id> --name --style "<how the art looks>" --rules "<series character rules>"
   --ref-pdf <a scanned book> --pages 5,21` (or `--ref-img`). Sumeet's scanned books are in
   `~/.hermes/data/kids-books/` (Tractor Mac: harvest/src.pdf, Tractor_Mac_Arrives_at_the_Farm.pdf). For a new
   series, use a book he sends; otherwise ask for one — a style without references comes out generic.
4. **Cover first, then two sample pages for approval.** `art <slug> 1` (cover uses the best model), then set
   `"anchor": "art/p01.png"` in story.json — every later page copies characters from the approved cover. Paint two
   representative pages (`art <slug> 5 21`), `layout`, and show Sumeet the laid-out pages. He asked to approve before
   the whole book is made; don't skip this.
5. **The rest.** `art <slug>` paints every page without art: generate → judge → retry with the judge's problems as
   fixes (max 3 tries, keeps the best). Then do your own visual QA (below) and redo pages with targeted fixes by
   putting `"fixes": [...]` on the page or rewriting its `scene`, then `art <slug> <n>`.
6. **Print files.** `layout <slug>` → `booklet <slug>` (prints IMPOSITION OK only if every half-sheet matches the page
   that belongs there) → `sheets <slug>` → send the booklet PDF on Telegram (`MEDIA:` path; under 50 MB).
   Printing: double-sided, **flip on short edge**, fold the stack, staple twice on the fold.

## Slop filter (built after Sumeet caught Tegh "at the steering wheel" perched on Mac's engine hood)

The brief judge only checks that the listed things are present, so it passed a child sitting on a hot engine. Every
page now also goes through `slop_check` (automatically inside `art`; `slop <slug>` audits finished art):
1. **Describe, then judge** (`gemini-2.5-pro`): it must first write out the literal staging — what each character
   sits/stands on, where hands and feet are, what touches what, counts of limbs/wheels — and only then list problems
   with a severity. Describing first is what makes it notice a bottom on an engine hood.
2. **Second opinion** (`claude-sonnet-5.5`, a different model family) re-checks every blocker against the picture
   and must agree it is true AND real slop (impossible, unsafe, broken anatomy, artifact, contradicts the page
   text). This removed hallucinations like "the boy has three arms" (the hand on his shoulder was Dad's) and brief
   nitpicks. On book one the filter flagged exactly 3/27 pages, all real: p22 (hood), p16 (no gap in the wall the
   text talks about), p28 (wagon not hitched to the tractor). ~2¢ per page.
3. **Write scenes with explicit physics** so there's nothing to improvise: not "Tegh sits at Mac's steering wheel"
   but "Tegh sits on Farmer Sumeet's lap ON THE TRACTOR SEAT, both behind the steering wheel, Tegh's hands on the
   wheel, his boots resting on Dad's knees". Say who holds what, what each character sits/stands on, and that
   vehicles are hitched.
4. Your own visual QA still happens, at full resolution for any page with a vehicle, an adult holding a child, or
   hands doing something — contact-sheet thumbnails are where the hood problem slipped past.

## Visual QA — what actually goes wrong (from the first book)

Look at the art contact sheets yourself (vision) in groups of ~6 with the brief for each page. Recurring problems:
- **The child drifts**: lighter skin, brown hair, bowl cut, or looks 6–8. Squinting/eyes-shut poses are the worst
  for this. Fix: describe the face explicitly in the scene, add the real photo as a page `refs` entry, prefer
  eyes-open expressions.
- **Series character off-model**: Mac grows a cab or roll bar, or loses his face (eyes in headlights + smile).
  Put the rule in the series `rules` and repeat it in the scene ("NO roll bar").
- **Actions the model can't stage**: "squeezing sideways through a narrow gap" failed 5 times; "crawling into a low
  hole, only his boots showing" worked first time. If a beat fails twice, re-stage it rather than retrying.
- **Safety images parents notice**: a child hanging out of a car window → stage the goodbye beside the car.
- **Props that clash with the cast**: a Sikh farmer "raising his cap" → empty hands raised.
- **Text contradicting art**: change the text when that's cheaper ("held one out nice and steady" instead of
  "flat on his hand").
- The judge's "visible box" complaints on spot illustrations are usually false — measure the pixels (page white
  is 254–255) before redoing anything.

## Cost control (bake-off 2026-10-23, same pages, same judge)

| model | cost/image | verdict |
|---|---|---|
| gemini-3-pro-image (2K) | $0.14 | best; use for covers |
| **gemini-3.1-flash-image (1K)** | **$0.07** | indistinguishable from Pro at 5-inch print size → default for pages |
| gemini-3.1-flash-lite-image | $0.035 | staging errors (wrong character holding the lamb) |
| gemini-2.5-flash-image | $0.04 | drops characters, draws text on the tractor |
| gemini-nano-banana-2.1 | — | constant 429s on OpenRouter's shared pool |

Flash at 2K is $0.10 — only worth it for a full-bleed page. Re-run `bake <slug> <pages> --models a,b` when new models
appear and update DEFAULTS + this table. Where the $24 went on book one: ~4.4 tries per page, from changing the cast
mid-book (redo every page with that character), painting before the cast sheets/anchor were locked, and a judge that
flagged nitpicks (jacket-cuff stripes). Lock story + cast + cover before painting; the judge prompt now ignores
trivia. `pbook.py cost` shows credit before/after; `art` prints the spend of each run.

**Judge:** `google/gemini-2.5-flash` via OpenRouter (~$0.002 per check). A free local judge on Magnus
(`gemma3:12b` via Ollama, `"judge": "local"` in config.json) was tried on 2026-10-23 and failed: it ran away into
12 KB of broken JSON and pushed Magnus (16 GB) into swap. Don't switch back unless Magnus gets more RAM or a better
small vision model appears. Re-test it with the same bake images first.

**Money:** OpenRouter credit is prepaid on Sumeet's account (1P item in `config.json`). Sumeet authorised up to $50
for book art (2026-10-23). If credit runs out, say so with the balance and ask him to top up at
openrouter.ai/settings/credits — never enter card details. Bedrock's image models (Stability Ultra/Style Guide) were
tested and can't keep characters consistent (2.5–3/10); Google AI Studio's free tier has no image quota.

## Copyright

These are private, home-printed books for the family, inspired by series the kids love — never sell, share or post
them, and say so if asked to publish one. Credit the original creator in the colophon ("Inspired by the *Tractor
Mac* books by Billy Steers").
