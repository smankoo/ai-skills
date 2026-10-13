# Using skill-creator on this Hermes setup (local adaptation notes)

Vendored from https://github.com/anthropics/skills/tree/main/skills/skill-creator at upstream commit `dbd4588`
(Apache-2.0, see LICENSE.txt). SKILL.md and scripts are **unmodified**. This file explains how the method maps onto
Hermes. Read it after SKILL.md.

**Standing rule (owner, 2026-10-13):** every new skill, and every substantial rewrite of one, goes through this
skill's process. Small patches (a pitfall line, a corrected command) can still be made directly.

## Mapping the method onto Hermes
| skill-creator says | On Hermes |
|---|---|
| Capture intent / interview | Mine the current conversation first (corrections, commands that worked, the user's verbatim rules). Ask the user only what's left. Load related skills (`skills_list`, `skill_view`) to avoid duplicates. **Improve an existing skill before creating a new one.** |
| Write SKILL.md (name, description, body) | Same frontmatter. Hermes also reads `metadata.hermes.tags` / `related_skills`. Keep the description's first ~60 chars a self-contained trigger ("Use when …"), since Hermes lists that in its skill index. Run `python3 scripts/quick_validate.py <skill-dir>`. |
| Where skills live | Repo-backed skills are symlinked into `~/.hermes/skills/`. `skill_manage` can't edit symlinked ones, so edit the repo directly, commit, push, and check that the remote matches. General-purpose skills go in the general skills repo; machine- or setup-specific ones in the setup-skills repo; throwaway or private ones in `~/.hermes/skills/<category>/` via `skill_manage`. |
| Test cases / evals (`evals/evals.json`) | Write 2–3 realistic prompts (the way the user actually talks). |
| "Spawn with-skill and baseline subagents in the same turn" | Use `delegate_task` with `tasks=[…]`: one child per eval × {with skill, without}. Give each child the skill path (with-skill) or nothing (baseline) and an output dir under `<skill>-workspace/iteration-N/eval-<id>/{with_skill,without_skill}/outputs/`. Children are leaf agents: they can't ask questions, so put everything in `context`. |
| Timing data (`timing.json`) | The delegation result reports duration and API calls. Record those. |
| Grade (`agents/grader.md`) and aggregate | Grade it yourself or with a `delegate_task` grader child following `agents/grader.md`. Then `python3 -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name <name>`. |
| Eval viewer (`eval-viewer/generate_review.py`) | No local browser display on a headless server: use `--static <out>.html`, then send the HTML to the user as a file (`MEDIA:/abs/path`) or summarise the results in chat. The user's feedback comes back as chat messages instead of `feedback.json`. Write what they say into `feedback.json` yourself so the loop stays the same. |
| Description optimisation (`run_loop.py`, `run_eval.py`, `improve_description.py`) | These shell out to `claude -p` (Claude Code). It exists on the VPS (`~/.local/bin/claude`, Bedrock auth), so they can run here, but they measure **Claude Code's** triggering, not Hermes's. Treat the result as a useful approximation. For Hermes, also sanity-check the first ~60 chars, since that's what Hermes's index shows. Optional; costs money per run. |
| Package (`package_skill.py`) | Not needed for Hermes (skills are directories). Use only when the user wants a `.skill` file. |
| Communicating with the user | Plain language, no jargon unless the user uses it. On Telegram, keep it short and give the results, not the process. |

## Proportionality
The full loop (evals + baseline + viewer + several iterations) is for skills that matter or recur. For a narrow,
obviously-scoped skill, do intent → draft → quick_validate → one realistic dry run → ship, and say that's what you did.
Don't skip writing the skill well: the writing guide (progressive disclosure, explain *why*, no ALL-CAPS walls,
examples) always applies.
