# Using frontend-design on this Hermes setup (local adaptation notes)

Vendored from https://github.com/anthropics/skills/tree/main/skills/frontend-design at upstream commit `dbd4588`
(see LICENSE.txt). SKILL.md is **unmodified**; this file explains how it's wired in here.

**Standing rule (owner, 2026-10-23):** any brand, landing page, or UI design work runs through this skill. The owner
rejected generated directions as "AI slop" until it was used.

## Where it's installed
- Claude Code: `~/.claude/skills/frontend-design` is a symlink to this directory, so `claude -p` runs pick it up
  automatically. Name it in the brief anyway ("Use your frontend-design skill").
- Hermes: `~/.hermes/skills/<category>/frontend-design` is a symlink here (load with skill_view before writing a
  design brief).

## How to brief a design run
- Hermes is the manager: write the brief (subject, audience, primary job, real content, real assets) and let Claude
  Code do the two-pass plan → review → build → screenshot-critique loop the skill describes.
- Require the written design plan (tokens + ASCII wireframes + "what I changed vs the generic default") as a file
  next to the build, so the owner can see the reasoning.
- Real fonts, not system stand-ins: fetch OFL families from github.com/google/fonts and embed or self-host them.
  Mockups rendered in fallback fonts read as generic.
- Real content and real imagery from the product; placeholder art is the biggest "cheap" tell.
- Show results as images (side-by-side compare PNGs), never as prose descriptions.
- Check the result against the skill's calibration list of AI-design tells (cream + serif + terracotta, ALL-CAPS
  eyebrows, `A · B · C` meta strings, mono labels, `→` on buttons, identical rounded cards). Earlier directions here
  failed on exactly these.
