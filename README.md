# 3p — Three-Party Review Skill for Codex

A Codex skill that runs a **Plan → Build → Review** workflow with **Claude** and **Antigravity** as independent reviewers and **Codex** as worker/judge. Catches important/critical/blocker issues through triangulation across three models, with explicit verification, rebuttal protocol, and full audit trail. Never commits, pushes, or deploys — always stops for your approval.

---

## Should you use this?

Use `3p` when a change is important enough to justify independent model review: security-sensitive edits, refactors across several files, architecture changes, migrations, or work where a second and third model may catch plan drift or subtle regressions. It gives you:

- A structured plan/build/final-review loop inside Codex.
- Parallel Claude and Antigravity reviewer calls through PAL MCP.
- Configurable reviewer model power (`high` or `low`) with per-project overrides.
- Persistent artifacts under `.3p/<run-id>/` for every plan, review round, verdict, and final summary.
- Hard safety rails: no commits, pushes, deploys, or secret-pattern files in reviewer prompts.

Do not use it for tiny edits where the review overhead is larger than the task. It also is not standalone: you need Codex, PAL MCP, Claude CLI, and Antigravity CLI (`agy`) configured locally.

---

## For Codex: install this skill

> If you (Codex) were given this repository URL by a user and asked to install this skill, follow these steps **exactly**. Do not skip the verification step.

```bash
# 1. Clone the repository to a working location
git clone https://github.com/WhaleCastle/codex-3p.git ~/code/codex-3p
cd ~/code/codex-3p

# 2. Run the installer (honors CODEX_HOME, defaulting to ~/.codex)
./install.sh

# 3. Verify Python helper works
python3 "${CODEX_HOME:-$HOME/.codex}/skills/3p/scripts/3p.py"
# Expected: prints "Usage: 3p.py <subcommand>..." to stderr, exits with code 2

# 4. Verify PAL MCP + claude + agy (Antigravity) are available (see PAL MCP section below).
#    The skill REQUIRES these. If they are not configured, the skill will fail
#    on the first reviewer call. Confirm with the user before claiming install is complete.
```

After install, **tell the user to restart the Codex session** so `$3p` registers in the skill list and PAL MCP reloads the reviewer roles. In normal Codex usage, restarting Codex is the PAL MCP restart. If the user runs PAL MCP as a separate process, restart that process instead.

---

## Prerequisites

| Requirement | Why |
|---|---|
| Codex | The skill runs inside Codex |
| Python 3.8+ | The helper script uses stdlib only — no `pip install` needed |
| `git` | Snapshot baselines + optional audit refs in git mode |
| `diff` | File comparison during snapshot diffs |
| PAL MCP | Bridges to claude + agy (Antigravity) CLIs (see below) |
| Claude CLI | One of the two reviewers |
| Antigravity CLI (`agy`) | The other reviewer (reached via PAL `cli_name=agy`) |

---

## PAL MCP setup (most common gotcha)

This skill calls `mcp__pal__clink` to talk to Claude and Antigravity. If PAL MCP isn't installed and configured, `$3p` will appear to work until the first reviewer call, then fail.

To set up PAL MCP:

1. **Install PAL MCP server.** Follow the PAL MCP project's instructions for installation. PAL must support the `agy` cli client (it ships an `agy` parser and internal defaults).
2. **Install Claude CLI.** Verify with `which claude` (or `npx claude --version`).
3. **Install Antigravity CLI.** Verify with `which agy`. The Antigravity reviewer is reached through PAL using `cli_name=agy`; PAL runs it non-interactively and auto-injects `--dangerously-skip-permissions`, so `$3p` does not configure that flag itself.
4. **Authenticate both CLIs** on the local machine.
5. **Register PAL MCP with Codex.** Confirm by checking that `mcp__pal__clink` appears in Codex's tool list.

If `mcp__pal__clink` isn't available, the skill cannot function. There is no fallback.

---

## Smoke test

In a fresh Codex session inside any git repo:

```
$3p --list
```

Expected: an empty result (no error). This confirms the skill loaded and the Python helper executes.

Then try a trivial real task:

```
$3p add a Python function that returns 42
```

You should see Codex:
1. Write a small plan
2. Call claude + antigravity in parallel for review
3. Iterate if findings, or proceed to build
4. Stop before committing/deploying and produce a summary for you to review

If the reviewer calls fail with "tool not found" or similar, see PAL MCP setup above.

---

## Usage

```
$3p <task description>      # Start a new run
$3p --resume <task-slug>     # Resume an interrupted run
$3p --list                   # List recent runs in this repo
$3p --clean <task-slug>      # Remove a run's artifacts + git refs
$3p --model-power            # Prompt to choose high or low reviewer models
$3p --model-power high       # Use high-power reviewer models for future runs
$3p --model-power low        # Use faster/lighter reviewer models for future runs
$3p --models                 # Show the model names mapped to low/high × reasoning/code
$3p models                   # Interactive picker: discover the latest CLI models and choose per slot
$3p --models set claude high reasoning opus
$3p --models set antigravity high code gemini-3.6-flash-high
$3p --update                 # Pull and reinstall the skill from its git checkout
$3p --config <path>          # Use a non-default config file
$3p --exclude <pattern>      # Add an extra snapshot exclusion (repeatable)
```

`--config` and `--exclude` are consumed only at the start of a new run; they are persisted into `state.resolvedConfig` so `--resume` reuses them automatically.

### Reviewer model power

`$3p` uses PAL `clink` roles to choose reviewer models. Models are selected on **two axes**: `power` (`high`/`low`) × `reviewType` (`reasoning` for plan/final, `code` for per-step build review). The installer creates a role for every (power, reviewType) pair per CLI, and each run resolves a model-specific PAL role from the model names frozen into that run's `state.resolvedConfig`.

| Power | Reviewer | `reasoning` (plan/final) | `code` (per-step) | Use when |
|---|---|---|---|---|
| `high` | Claude | `opus` | `opus` | Deep review, risky changes, architecture/security-sensitive work |
| `high` | Antigravity | `gemini-3.1-pro-high` | `gemini-3.6-flash-high` | " |
| `low` | Claude | `sonnet` | `sonnet` | Faster review for smaller or lower-risk tasks |
| `low` | Antigravity | `gemini-3.1-pro-low` | `gemini-3.6-flash-low` | " |

Claude uses the same model for both review types; Antigravity reviews reasoning (plan/final) with the Pro model and code (per-step) with the Flash model.

Run this to choose without remembering the values:

```
$3p --model-power
```

The choice is saved in `.3p/config.json` as `modelPower` and applies to new runs. Each run snapshots the resolved model power and model names at init time, so changing model power or model mappings will not silently change a run already in progress.

Advanced users can change what low/high mean:

```
$3p --models set claude high reasoning opus
$3p --models set claude low code sonnet
$3p --models set antigravity high reasoning gemini-3.1-pro-high
$3p --models set antigravity low code gemini-3.6-flash-low
```

After changing model mappings with `$3p --models set ...` or a config file, restart Codex so PAL MCP reloads the updated role arguments. If PAL MCP is running as a separate process, restart that process instead. Changing only `$3p --model-power high|low` does not require a restart after the roles have been loaded once.

---

## How it works

For one user-given task, the skill executes three phases:

**Phase A — Plan** (reasoning models)
Codex writes a numbered-step plan. Claude and Antigravity independently review the plan in parallel against the user's task. Codex verifies each finding (`accepted` / `rejected` / `ignored` with reason), revises the plan, and re-runs the review. Loops until both reviewers explicitly emit `APPROVED` in the same fully-attended round, **or** the round cap is reached (default 10).

**Phase B — Build** (code models)
For each step in the approved plan: Codex implements the step, runs the step's test command (if declared), and submits the step's diff + test output to Claude + Antigravity for independent review. Same verify-loop-and-revise pattern as Phase A but with a tighter severity bar (logic bugs, security, plan-drift only).

**Phase C — Final review** (reasoning models)
The cumulative diff across all steps + consolidated test output is sent to Claude + Antigravity for whole-task integration review. After that loop exits, the skill writes a comprehensive `summary.md` and **stops**, waiting for the user to review and approve before any commit or deploy.

Throughout all phases, Codex keeps you informed in chat — each reviewer finding is surfaced with its severity, title, and Codex's verdict (accepted/rejected/ignored) plus a one-line reason, along with what Codex changed in response — so you can follow the back-and-forth without digging into the round files.

### Hard safety guarantees

- Never runs `git commit`, `git push`, `git tag`, deploy, or publish.
- Never modifies existing git branches/tags/refs (only writes to `refs/3p/<run-id>/*`).
- Hardcoded secret-pattern list (`.env`, `*.pem`, `*.key`, `id_rsa*`, `**/.aws/credentials`, `**/credentials.json`, etc.) is non-overridable — those files NEVER enter reviewer prompts.
- All file artifacts go under `<repo>/.3p/<run-id>/` (auto-`.gitignore`d).

### Audit trail

Every reviewer round writes a per-reviewer file: `plan-round-N-<reviewer>.md`, `step-M-round-N-<reviewer>.md`, `final-round-N-<reviewer>.md`. Each file contains findings, Codex's verdicts with reasons, and any rebuttal exchanges. A final `summary.md` consolidates everything plus a per-round reviewer-availability log.

---

## Configuration

Built-in defaults can be overridden by a `.3p/config.json` file at your repo root, or via `--config <path>`:

```json
{
  "roundCap": 10,
  "timeoutSeconds": 120,
  "consecutiveFailuresForDowngrade": 3,
  "modelPower": "high",
  "models": {
    "claude": {
      "high": { "reasoning": "opus", "code": "opus" },
      "low": { "reasoning": "sonnet", "code": "sonnet" }
    },
    "antigravity": {
      "high": { "reasoning": "gemini-3.1-pro-high", "code": "gemini-3.6-flash-high" },
      "low": { "reasoning": "gemini-3.1-pro-low", "code": "gemini-3.6-flash-low" }
    }
  },
  "excludes": ["custom_dir/"],
  "extraExcludes": ["more_dir/"]
}
```

| Key | Default | Notes |
|---|---|---|
| `roundCap` | `10` | Max rounds per phase before cap-reached exit |
| `timeoutSeconds` | `120` | Per-reviewer call timeout |
| `consecutiveFailuresForDowngrade` | `3` | Failures before user is offered single-reviewer downgrade |
| `modelPower` | `high` | Selects high or low reviewer model mappings for new runs |
| `models.claude.<power>.<reasoning\|code>` | `opus` / `sonnet` | Claude model alias per power × review type (same model for both types by default) |
| `models.antigravity.<power>.reasoning` | `gemini-3.1-pro-high\|low` | `agy` model for plan/final review at that power |
| `models.antigravity.<power>.code` | `gemini-3.6-flash-high\|low` | `agy` model for per-step code review at that power |
| `excludes` | (default bloat list) | **Replaces** default `node_modules/`, `dist/`, etc. |
| `extraExcludes` | `[]` | **Appends** to defaults |
| `secretPatterns` | (hardcoded list) | User can extend; hardcoded patterns CANNOT be removed |

### Auto-update

If the skill was installed from a git checkout, run:

```
$3p --update
```

This fetches the latest changes, performs a fast-forward-only pull, reruns `install.sh`, and reinstalls the PAL reviewer roles. Restart Codex after updating so PAL MCP reloads those roles. If the installed skill was copied without its source git checkout, auto-update will stop with a clear message and you should reinstall from the repository.

---

## Repository layout

```
codex-3p/
├── SKILL.md                  # Runtime instructions Codex follows during $3p
├── README.md                 # This file
├── LICENSE                   # MIT
├── install.sh                # Copies skill to ~/.codex/skills/3p/
├── agents/
│   └── openai.yaml           # Codex UI metadata
├── scripts/
│   └── 3p.py                 # All deterministic logic (stdlib-only Python)
├── prompts/
│   ├── plan-review.md        # Phase A reviewer prompt template
│   ├── step-review.md        # Phase B reviewer prompt template
│   └── final-review.md       # Phase C reviewer prompt template
└── tests/
    └── test_*.py             # pytest coverage for helper and workflow state
```

Run the test suite locally:

```bash
cd /path/to/codex-3p
python3 -m pytest tests/ -v
```

---

## Troubleshooting

**`$3p` doesn't appear in Codex's skill list**
Restart your Codex session after running `./install.sh`. Skills register at session start.

**Reviewer role fails with "not one of ['codereviewer', 'default', 'planner']"**
Restart Codex so PAL MCP reloads the reviewer roles written by install/update/model changes. In normal Codex usage, this is enough. If PAL MCP is managed as a separate long-running process, restart that process instead.

**Reviewer calls fail with "tool not found" or similar**
PAL MCP, claude CLI, or agy (Antigravity) CLI is not configured. See [PAL MCP setup](#pal-mcp-setup-most-common-gotcha).

**Antigravity reviewer fails with "CLI 'antigravity' is not configured" / parser error**
PAL binds its output parser to a fixed set of cli names, so the Antigravity reviewer must be reached as `cli_name=agy` (3p does this automatically; its PAL config is written to `~/.pal/cli_clients/agy.json` with `"name": "agy"`). Confirm `which agy` resolves and that your PAL build ships the `agy` client.

**`$3p` runs the same task forever / hits round cap repeatedly**
This is expected if reviewers genuinely keep finding new issues each round. Inspect `.3p/<run-id>/plan-round-N-*.md` files to see what they're flagging. Adjust `roundCap` in `.3p/config.json` if you want stricter cap, or accept the cap-reached exit (Codex will apply all remaining `accepted` findings before stopping).

**Reviewer keeps timing out**
Increase `timeoutSeconds` in `.3p/config.json`. Default is 120s, which is enough for most reviews but large diffs may need more.

**I want to test the skill on a non-trivial real task**
Start small. The skill is most useful for tasks that benefit from multi-model triangulation (security-sensitive code, refactors touching many files, architecture decisions). For tiny tasks the overhead of multiple reviewer calls outweighs the benefit.

---

## License

MIT — see [LICENSE](LICENSE).
