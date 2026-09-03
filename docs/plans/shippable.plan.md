# Plan — a stranger can install this and use it

**Written 2026-09-03.** ⛔ **Not built. This page is the deliverable.**

## Goal

**A stranger with Gramps and an MCP-capable agent installs this in one action —
two at most — and makes a working `tree_name` call in under ten minutes.**

⚠️ **Written on the recommendation that the note flow is retired.** What changes
if it is kept is flagged at each point with **[if kept]**.

---

## What today costs, measured

Walked on a fresh clone and a fresh virtual environment, timed. ⛔ Not Gramps.

| step | time |
| --- | --- |
| clone (local, `--depth 1`) | **3 s** |
| `python -m venv .venv` | **19 s** |
| `pip install -e ".[mcp]"` | **63 s** |
| **to a runnable server** | **85 s** |

⭐ **The time is not the problem.** The problem is the count.

**Eight user actions**, from `README.md` and `docs/using.md`:

1. obtain the checkout · 2. create a virtual environment · 3. install the extra ·
4. register the server with the agent host · 5. make a junction from Gramps'
plugin folder to the checkout · 6. make a copy of the tree and bless it by hand ·
7. write `copy_path` — **[if kept]** and `export_path` — into
`%APPDATA%\gramps-live-api\config.json` · 8. restart Gramps so the plugin loads.

**Guesses a stranger meets, each verified against the source:**

- ⛔ **`gramps60` was hardcoded** in `docs/using.md:77` — anyone not on 6.0 would
  create the junction in a folder Gramps never reads. ⭐ **Fixed since this was
  measured**: the snippet now finds the newest `gramps*` folder containing a
  `plugins` directory, the same shape `check` already used.
- which Python — the Microsoft Store alias trap is documented, but they must
  notice they hit it.
- where `config.json` lives and which keys it takes (`copy_path`,
  `gramps_runtime`, **[if kept]** `export_path`).
- whether a restart is needed. It is; nothing says so at the point of the junction.
- ⛔ **which agent.** Every install line in the repository says `claude mcp add`
  and nothing states whether anything else works.

⚠️ **One thing I could not measure and will not pretend to.** `check` run from a
fresh clone reported `ok` for runtime, plugin, source and copy — because it reads
the **owner's user-level config**, not the checkout, and its `source:` pointed at
a different checkout entirely. **A stranger's `check` cannot be measured on a
machine that already has one configured.**

---

## The two architectures

### (a) bundle everything in the addon

The `.addon.tgz` carries `src/` — host **and** MCP server — so one install puts
both on disk. The user then registers the server with their agent host once.

⭐ **How the package gets onto Gramps' Python is answered, and it is one line.**
From `gramps_plugin/gramps_live_api_host.py:809–835`:

> ⚠️ Gramps `exec`s a plugin rather than importing it, so the plugin folder is
> **NOT** on `sys.path` and a sibling module cannot be imported by name.

The plugin therefore puts itself on the path, trying `GRAMPS_LIVE_API_SRC`, then
`dirname(here)/src`, then `here` — where `here = dirname(realpath(__file__))`.

⛔ **That does not carry over unchanged.** Today the plugin folder is a junction
into the checkout, so `realpath` follows it and `dirname(here)/src` lands on the
checkout's `src`. In a bundled tarball there is no link to follow: `src/` would
sit at **`here/src`**, which is not in the candidate list. **One candidate must be
added.** That is a change to `gramps_plugin/`, and it is its own piece of work.

#### ⛔ And putting `src/` in the tarball does NOT produce a runnable server

**Raised by the PR bot on this page, and reproduced.** `server.py:56` does
`from mcp.server import MCPServer`, and `mcp` is an **optional** dependency
installed only through the `.[mcp]` extra. Installed without it:

```
File "src/gramps_live_api_mcp/server.py", line 56, in <module>
    from mcp.server import MCPServer
ModuleNotFoundError: No module named 'mcp'
```

⚠️ **The extra pulls 31 packages** into the environment — measured on this machine.

⭐ **So "install the addon, paste one line" is false as written**: the line the
user pastes starts a process that cannot import its own SDK. **Four ways out, and
only one keeps the action count:**

| | what it costs |
| --- | --- |
| **vendor the SDK and its 30 dependencies into the tarball** | a Gramps addon carrying a wheelhouse; ⛔ platform-specific wheels make it not one artifact |
| **ship a self-contained executable** | a build pipeline per platform, and this project has only ever run on one |
| **keep a dependency-install action** | honest, and the count becomes **three** actions |
| ⭐ **publish to PyPI and run it with `uvx`** | the runtime is fetched and isolated on first run, so the SDK touches neither the addon nor the user's Python — ⛔ **but see the three things it needs first** |

⭐ **The fourth is the only one that keeps the goal**, and it does **not** work
against the package as it stands today.

#### ⛔ What `uvx` needs before it can start this server

**Raised by the PR bot and verified against `pyproject.toml`.** A bare
`uvx gramps-live-api-mcp` fails three ways at once:

| | |
| --- | --- |
| the distribution is named | `gramps-live-api`, not `gramps-live-api-mcp` |
| console scripts declared | ⛔ **none — there is no `[project.scripts]` section at all** |
| the SDK | behind the optional `mcp` extra, which a bare invocation does not select |

⭐ **So the plan owes an entry point.** `python -m gramps_live_api_mcp` runs
`serve()` from `gramps_live_api_mcp.server`; a console script pointing at it, plus
selecting the extra, makes the line:

```
uvx --from "gramps-live-api[mcp]" gramps-live-api-mcp
```

**Cost:** a `[project.scripts]` entry, and a test that the named script exists and
starts the same server `python -m` does — so the two entry points cannot drift.

⚠️ **Not free, and not one line in the README.** ⛔ **`uv` itself is an
installation action on a clean machine.** Criterion ① names only Gramps and an
MCP-capable agent as prerequisites, so a machine without `uv` cannot run the
pasted line at all. **Either ① explicitly requires `uv` already installed — which
narrows who the demo is for — or installing it makes this a THREE-action path.**

⭐ **Stated plainly: there is no two-action install today, and this page should
stop implying one.** The honest floor is **three** — install `uv`, install the
addon, paste one line — plus the sentinel; or **two** for a user who already has
`uv`, which is a real population but must be named rather than assumed.

**The name is free on PyPI** (open question 3).

⛔ **UNVERIFIED end to end.** Nothing has been published, so `uvx` has never been
run against this package. **The spec may not claim it works until it has**, and
criterion ① cannot close until someone has done it on a clean machine.

⭐ **So the floor, stated honestly: install `uv` · install the addon · paste one
`uvx` line after a PyPI publish · place the sentinel.** ⛔ **Three actions plus
the permission**, or two for a user who already has `uv` — and the `uvx` line
rests on a publish and an entry point that do not exist yet.

⚠️ **The goal at the top of this page is therefore NOT met by (a) as costed
here.** It is the target, not a description; saying so is the point of measuring.

### (b) Gramps hosts MCP itself

The loopback host already inside Gramps speaks MCP over HTTP. **No second process
exists.** The user points their agent at a URL.

⛔ **This is a ruling, not a detail. It reverses R8's deliberate split.**

R8 put the MCP server outside the Gramps process as a thin client holding no
Gramps code, so that the surface an agent talks to is not the surface that holds
the database. Under (b) the MCP surface moves **inside** Gramps' process, next to
the database and next to GTK.

⚠️ **What HTTP-over-loopback does and does not change.** The listener is already
inside the process and already hostile to anything that is not its own client —
`Origin` refused, bearer token required, main-thread timeout returns a refusal.
So the *transport* is not new. **What is new is who may speak it**: today only our
own thin client knows the token; under (b) any MCP-capable agent does, and the
token becomes the whole boundary rather than one of two.

⭐ **It also cannot be tested the way (a) can.** (a) is testable without Gramps —
the MCP server is a separate process. (b) is only testable with Gramps running.

### ⭐ Recommendation: **(a)**, and put (b) to the owner as the ruling it is

(a) needs no ruling, keeps R8 intact, keeps the server testable without Gramps,
and costs one added `sys.path` candidate. **(b) is a genuine simplification** —
it removes a process and a registration of a command line in favour of a URL —
and it should be decided on its own, not slipped in as packaging.

### ⚠️ Registration is the step that resists, in both

Writing another program's configuration crosses a boundary and is client-specific.
**It cannot be removed.** It can be reduced to **one copy-paste line the addon
displays**, which is honest to call one action but is not "zero".

⛔ **So the truthful claim is two actions: install the addon, paste one line** —
⚠️ **and the line only works once the package is published**, because of the
runtime hole above. Plus the sentinel, which is deliberate and stays manual —
**it is the permission**.

---

## ⭐ Client compatibility

**Stated nowhere today.** Every install line says `claude mcp add`;
`pyproject.toml` declares no Claude dependency. ⛔ **Implied, unverified,
unstated** is the worst of the three.

### Tested

| client | result |
| --- | --- |
| **Claude Code** | the tool has been used through it throughout development |
| **Codex CLI 0.146.0** | ⭐ **registered, discovered and invoked `tree_name` successfully** |

**Codex, exactly what happened.** `codex mcp add <name> -- <python> -m
gramps_live_api_mcp` registered it as `transport: stdio`. `codex exec` then
reported `mcp: gramps-ship/tree_name started` and `(completed)`, returning the
tool's own envelope — `{"ok": true, "tree": {...}}` — well-formed.

⚠️ **Two things that finding depends on.** Under Codex's default `sandbox:
read-only` with `approval: never`, the call was **auto-denied** —
`user cancelled MCP tool call`. It succeeded only with approvals granted. **A
README must say that**, or a Codex user's first call fails and reads like a
broken server. And ⛔ **descriptions were not measured under Codex** — the
2,048-character cap in `DESCRIPTION_BUDGET` was measured against Claude Code
only, and whether Codex truncates differently is **unverified**.

⚠️ **Prompts were not exercised under Codex.** §4 adds a `getting_started`
prompt; whether Codex surfaces MCP prompts at all is **unverified**.

### By protocol, not tested

MCP's own documentation names **Claude, ChatGPT, VS Code (Copilot), Cursor and
MCPJam** as clients. This server is a **stdio** server using the official Python
SDK, so any client supporting local stdio servers should register it with its own
equivalent of one command. ⛔ **No claim is made about any of them here, because
none has been run.**

### What the README must say

A **Compatibility** section: the two tested clients **by name**, with the Codex
approval caveat; a protocol-level sentence for the rest; and ⛔ **no client named
that nobody has run.**

---

## Criteria, each must close

① ⭐ **The demo.** On a **clean machine** — a Windows box with Gramps 6.0
installed, a family tree already in it, an MCP-capable agent installed, and
nothing of this project present — a stranger following `INSTALL.md` reaches a
successful `tree_name` in **under ten minutes** with **at most two actions plus
the sentinel**. Timed, by someone who has not done it before.

② `INSTALL.md` matches the demo exactly. ⛔ No step the demo did not need.

③ The tool's guidance ships with the tool as an MCP prompt. **Built — see §4 of
the dispatch that produced this page.**

④ CI produces the release artifact on a tag.

⑤ ⭐ **Works with two named clients, tested.** Claude Code and Codex. Met for
registration and invocation; ⚠️ **not met for prompts or description length under
Codex.**

⑥ `pyproject.toml` stops lying: `version = "0.0.0"` against a `v0.1.0` tag, and
`Development Status :: 1 - Planning` for a tool with two real ingestions.

---

## Out of scope, explicitly

Any change to the dialog or the writer · cross-platform **support** · the official
Gramps addon list · automating the sentinel · **building (b)**, which is its own
milestone if it is ruled for.

---

## Open questions, each with a recommendation

**1. Does the addon carry `src/`, or does the user pip-install the package too?**
⭐ **Recommend carrying it.** Two installs is the thing the goal forbids. Cost: one
`sys.path` candidate, and the tarball grows by the package.

**2. Is the listing entry's target version fixed or derived?**
⛔ **Fixed.** The real listing Gramps 6.0 fetches carries `"g": "6.0"` as a literal
string per entry — verified against
`gramps-project/addons/master/gramps60/listings/addons-en.json`, 187 entries. Our
`.gpr.py` uses `gramps_target_version=MODULE_VERSION`, which is **derived**, and
`addons-source/make.py` **rewrites** the gpr's target as it builds. ⭐ **Recommend
a third-party listing of our own**, not the official list, which is out of scope.

**3. `gramps-live-api` on PyPI?**
⭐ **Free.** Verified via the JSON API with controls in both directions:
`requests` → 200, a nonsense name → 404, `gramps-live-api` → **404**. ⚠️ The HTML
project page returns 200 for *everything* — it is a bot-challenge page — so it
cannot be used to answer this.

**4. Does `uvx` isolation make #173 moot for a stranger?**
⚠️ **No, and it is not the mechanism people assume.** The pin `mcp>=2.0.0,<2.1`
resolves to **2.0.0** today, so any isolated install honouring the pin gets the
good version. Isolation does not *bypass* the pin — it **obeys** it. #173 stays
what it is: an upgrade blocker. ⛔ Recommend no change here.

**5. Which Gramps versions does the plugin path support?**
⛔ **`gramps60` is hardcoded in the docs.** ⭐ Recommend `INSTALL.md` derive the
path or state the version it assumes, in one visible line.

---

## Platform truth

⭐ **The host has only ever been loaded inside a Windows Gramps.**

| | claimed | tested |
| --- | --- | --- |
| **Windows** | yes | ⭐ **yes** — the plugin, the dialog and two real ingestions |
| **Linux** | the package's own tests run there in CI | ⛔ **the plugin has never been loaded in a Gramps on Linux** |
| **macOS** | nothing | ⛔ **nothing** |

⚠️ CI's three Python legs prove the **package** imports and its tests pass on
Linux. They say nothing about the addon, because CI has no Gramps.

⛔ **Recommend the README say: Windows-tested; other platforms unverified.**
Not "should work".
