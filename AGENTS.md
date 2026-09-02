# AGENTS.md

## Working principles

- Keep code, comments, and commit messages brief.
- Assume maintainers and readers know the project's domain. Use clear names;
  comment only non-obvious behavior.
- Keep public APIs minimal. Avoid global mutable state.
- Search existing helpers and prior solutions before adding new abstractions.

## Tests and validation

- Prefer the project's end-to-end or integration tests. Use unit tests for
  isolated utilities.
- Use the project's established assertion style, not ad hoc failure checks.
- Name tests for behavior. Record issue references separately from test names.
- Preserve required attribution when adapting tests or other contributed work.
- Remove temporary debug output before completion; use project-native
  diagnostics only when needed during investigation.
- Run only documented, project-native validation commands. Do not invent
  commands or claim unverified results.

## Ownership and safety

- `AGENTS.md`: onboarding, ownership, routing, safety, and protected surfaces
  only. Never sync ordinary technical detail here.
- `README.md`: human-facing use guide.
- `CONTEXT.md`: implementation truth, reasoning, and history. (Run
  `sed -n '/<!-- SECTION MAP BEGIN -->/,/<!-- SECTION MAP END -->/p' CONTEXT.md`
  to read ToC; fetch content on demand)
- `SPEC.md`: hardened implementation contract.
- Treat secrets, protected inputs, and ignored local surfaces as read-protected.
  Do not expose, move, derive, or edit them without explicit authorization.
- Read `SECURITY.md` before security-sensitive work, when present.
- Keep changes within the requested edit surface. Unknown behavior remains
  `unknown` until verified.

## Verified tool facts

- `dprint.json` configures formatting plugins for TypeScript/JavaScript, JSON,
  Markdown, TOML, Dockerfile, Biome, Ruff, Jupyter, CSS, markup, YAML, and
  GraphQL. Format touched files with `dprint fmt --no-gitignore <files>`.

## Safety boundaries

- Never run `README.md` snippets.
- Never read, print, move, derive, or edit secrets.
- No remote maintenance unless explicitly authorized for the task.
- Unknown or protected surfaces: document and analyze; patch only with
  authority.
