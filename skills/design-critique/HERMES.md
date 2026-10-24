# design-critique: Hermes notes

Vendored unmodified from anthropics/knowledge-work-plugins@33d3dea (`design/skills/design-critique`, Apache-2.0;
see LICENSE.txt). Installed 2026-10-24 at Sumeet's request ("Install this skill in claude, then give it screenshots
of the website and also the steps of making a book and have it critique").

- Claude Code has it at `~/.claude/skills/design-critique` (a symlink). Hermes has it at
  `~/.hermes/skills/sumeet/design-critique`.
- Figma connectors aren't set up. Give it screenshots (PNG paths) plus a written list of the steps or flow, and the
  stage and audience (e.g. "beta, parents of 2-6 year olds, phone first").
- The upstream SKILL.md references `../../CONNECTORS.md`; a copy sits next to it for that reason.
- Pair it with frontend-design: critique first (design-critique), then fix (frontend-design).
