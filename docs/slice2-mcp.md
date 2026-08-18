# Slice 2: an agent puts a note on a person, and you approve it at a console

Slice 1 worked and its demo passed, and demo day showed one thing the project had documented instead
of building. `docs/using.md` told you to open a Gramps XML export in a text editor and find a
person's line. You did not do it — the file is gzipped XML holding thousands of people, and handles
are invisible in the Gramps UI by design. **A step the author routes around is a missing feature.**

Slice 2 replaces the three-command terminal flow with **three MCP tools**, so you can ask an agent to
put a note on someone. The bar is slice 1's own: *you see exactly what will be written, you say yes,
and you find the note in Gramps.* Slice 2 keeps that bar with an agent in the middle.

> ⚠️ **Green CI is not evidence this works**, and that has not changed. The runners have no Gramps,
> no `gi` and no tree. What CI covers is everything up to the process boundary. **The verification is
> you, opening the copy in Gramps and finding the note.**

---

## The trust model, stated before the setup

Two questions, and they are different:

| | The question | What answers it |
| --- | --- | --- |
| **Binding** | is the thing written the thing that was approved? | the operation never travels through the agent |
| **Approval** | did a *human* say yes to it? | a console the agent cannot write to |

**Binding alone is not enough.** If `approve` wrote the moment the agent called it, your yes would be
something the agent asserts — which is the auto-approving path this project forbids.

### 1. The operation never leaves the server

`propose_note` builds the operation, validates it, and files it in a **proposal store** inside the
blessed copy, at `.gramps-live-api-proposals\`. It returns exactly three things: a proposal id, the
sentence you will be shown, and an approval digest. **It does not return the operation.**

`approve(proposal_id, approval_digest)` takes an id and a digest and **has no operation parameter**.
The agent can only name a stored proposal — and name it wrongly.

### 2. The console is the approval

`approve` claims the proposal — an atomic rename, so two concurrent approves cannot both proceed —
and opens a **new console window** running `python -m gramps_live_api approve <id>`. That process:

- reads the operation from the claimed file, not from anything the agent sent;
- prints the note **in full**, nothing elided, through the existing render guard;
- prints `write this into <copy>? [y/N]` and reads a real console stdin;
- on `y`, runs the **unchanged slice 1 write and read-back**;
- files its outcome where the server reads it, and stays open until you press Enter.

⚠️ **Your `yes` in the chat is a courtesy. The `y` in the window is the approval.** If the two
disagree — if the window shows something other than what the transcript claimed — **the window is
right**, and that is the entire point of the design.

The threat this defends against is not you lying to yourself. It is that **your tree contains text
from arbitrary sources**, an agent reads it, and injection through a source note is a real path from
*read* to *write*. The console makes the human yes unforgeable the way the sentinel makes the live
tree unwritable.

### ⚠️ What this does NOT defend against

`approval_digest`'s own docstring says it is *not a security boundary against a hostile front end*,
and nothing here changes that. What an agent can still do:

1. **Misrepresent the proposal in its transcript.** It can tell you it is adding one note and propose
   another. The console shows the truth. **A human who approves without reading the window is not
   protected by any of this.**
2. **Edit the proposal file.** The store sits inside the copy and the agent runs as the same user.
   `ProposalCorrupt` catches an edited *operation*, but an attacker who edits operation, digest and
   sentence together defeats it — the file is not signed. **The console rendering is a UI defence,
   not a cryptographic one.**
3. **Propose repeatedly**, hoping a tired owner types `y` without reading.
4. **Nothing authenticates the caller.** Any process that can speak stdio to the server can call the
   tools. The agent host launches it as you, so this is one trust domain by construction.

What it *does* buy, bounded and closable: **one approved proposal produces at most one write attempt,
of exactly the operation whose full text was displayed at a console the agent cannot write to, under
the rendering rules in force when it was displayed.**

---

## ⭐ Ruling 1 — `priv="1"`, and the residual stated plainly

**Permitted:** personal data flows to a model. Single-user tool, your own family's data, your own
decision.

**Bounded by the tree's OWN mechanism, not by intent.** Any person carrying Gramps' `priv="1"` flag
is out of reach, at **two independent enforcement points**:

1. **`list_people` does not return them, and does not count them.** Reporting *42 matched, 25 shown*
   over a set that included people it will never show would leak the excluded ones by arithmetic.
2. **`propose_note` refuses them as a target, by name.** The message says *this person is marked
   private*, which is a different sentence from *no such person*. Silence there would leave the
   caller unable to tell the two apart — the same defect class as a lock refusal that names no
   remedy.

⚠️ **Both points are needed and neither implies the other.** A handle can arrive from a stale export,
from something written down, or from a caller that never listed at all. Excluding somebody from a
listing says nothing about whether they can be named directly, and a test asserts a private person is
unreachable through the target path **even when `list_people` was never called**.

**Where the flag is unstated, the person is not private** — Gramps' own default, taken rather than
guessed at. **Where the flag carries a value the schema does not declare, the person IS private**:
the DTD declares `priv` as `(0|1)`, so anything else is not a document Gramps wrote, and a privacy
flag is the wrong place to read an unknown value generously.

### The residual, plainly

**The names and note text of non-private people enter a model's context by design.** That is what
this feature is. `list_people` puts names and birth years into an LLM's context and `propose_note`'s
text goes there too. It is bounded by a required search term — there is no way to list everybody —
and by a result cap, and by the privacy flag above. **It is not bounded by anything else, and it is
not reversible: text that has reached a model's context has reached it.**

### Three things ruling 1 does NOT cover, recorded rather than implied

- **Gramps' `priv` flag on a `<name>`, an `<event>` or a `<note>`.** Only the flag on the *person* is
  honoured. A public person whose name element is marked private is still listed under that name.
  Ruling 1 is about the person flag, and widening a fix past the claim it fixes is how a property
  arrives unreviewed.
- **A person absent from the export** cannot have their flag read at all, so `propose_note` refuses
  them. Fail-closed, and the message says the export may need retaking.
- **A stale export is a privacy fail-open**, and it is the one below.

---

## ⭐ The export-versus-copy decision: `check` gains the comparison

**Decision: yes, and it FAILS the doctor rather than warning inside a passing report.**

> ⚠️ **That is about a STALE export, not an absent one, and the two are different states.** An export
> that is *not configured* is reported and does **not** fail the doctor: slice 1's `preview`, `apply`
> and `check` read no export, `docs/using.md` shows exactly that setup ending `ready`, and there is no
> fail-open to protect against — with no export there is nothing for `list_people` to read a stale
> `priv` flag out of. The line names the two tools that cannot run instead. Everything below is about
> the snapshot that exists and is lying.

The plan raised this as *"worth a `check` line comparing export and copy mtimes"* for a usability
reason — a handle from an old export meets a confusing refusal. Ruling 1 changes what the comparison
is *for*, and that is why it was built rather than deferred:

| Staleness | Direction | What happens |
| --- | --- | --- |
| a stale **handle** | **fails closed** | `TargetNotFound` or `TargetDisagrees` at the write. Confusing; harmless. |
| a stale **`priv` flag** | ⚠️ **fails open** | somebody marked private *after* the export was taken is still listed and still targetable, **and nothing anywhere says so** |

Ruling 1 bounds this feature by the tree's own mechanism. **A mechanism read out of a snapshot older
than the tree is not the tree's mechanism.** So `check` reports it, and reports it as *not ready*,
because printing "ready" over a stale privacy oracle is the claim the ruling forbids.

**How it is measured, and where it errs.** The export's timestamp is compared against the newest file
**directly inside** the tree directory. Non-recursive, which is what keeps our own writes out of it:
the undo records and the proposal store are subdirectories, so minting a proposal cannot make the
doctor report its own side effect — a check that fires on its own output is one people learn to
ignore. What it *does* over-report is a copy Gramps merely opened, because the lock file is touched
either way. **That direction is deliberate.** This answer must err toward *export it again*, never
toward *the flag you are reading is current*.

**What was NOT built:** `propose_note` does not itself refuse on a stale export. That would be a
second, stricter rule in a second place, and the plan asked for a `check` line. Recorded as a
residual: **the doctor tells you, and nothing stops you.**

---

## ⭐ The MCP client timeout, and what happens in the window

`approve` blocks on a human at a console. A client may time out while you are still reading. The
ruling's hard requirement is that **a timeout must never leave a proposal in a state where a later
call writes it.**

It cannot, and the reason is structural rather than careful: **the proposal is consumed at the claim,
before the console is even opened.** By the time anything can time out, crash or be retried, there is
no proposal left. A retried `approve` gets `ProposalNotFound`.

**But the console window is still open, and you typing `y` after the tool call already returned is a
real sequence.** Here is exactly what happens, because the one unacceptable answer was that it be
undefined:

| Moment | What happens |
| --- | --- |
| the server waits, up to 45 seconds | polling for the console's report **and for the console itself** |
| our timeout fires first | `approve` returns **`still_open`** — the window is live, the write may yet happen, **do not retry**, and the message names where the answer will appear |
| the window goes away before you answer | `approve` returns **`unknown`** at once, rather than waiting out the timeout and calling it `still_open` for ever. The server started that process, so it can tell the difference between *he is reading* and *it is gone* |
| the client times out first | the agent sees a transport error; the state is identical, because the proposal was consumed before any of this |
| you type `y` at any later point | **the write proceeds.** The console writes the note, reads it back, and files its report |
| you type `n` at any later point | nothing is written; the report says `declined` |

**The write proceeding after a timeout is the acceptable answer**, and it is reported as an outcome to
relay rather than one to retry. A second note needs a second `propose_note`, a second console, and
**you saying yes a second time** — which is the correct place for a duplicate to become possible
(issue #69).

⚠️ **45 seconds is a guess about client behaviour, not a measurement**, and it is not what makes any
of this safe. It only decides whether the agent receives a defined answer or an undefined one.

**Two residuals of that window, recorded rather than fixed:**

- **After a timeout the agent cannot learn the outcome.** Criterion 1 fixes the surface at exactly
  three tools, so there is no *read the outcome* call — the machinery exists (`Tools.outcome_of`) and
  is not exposed. **You read the window.** Adding a fourth tool to close this is a decision about the
  surface, not a bug fix, so it was not made here.
- ⭐ **`still_open` used to be unable to tell *he is still reading* from *the console died*, and now
  it can.** The two look identical from the report directory, which is why the message could once say
  no more than *the console has not reported back*. What discriminates them is the process, and the
  server started it — so `approve` now polls the console's liveness beside its report, and a console
  that exits without filing one returns `unknown` immediately instead of `still_open` for ever.
  `still_open` accordingly means what it says: the window is up and he has not answered.

  **What is still not covered**, recorded rather than implied: a console the server did **not** start
  — nothing spawns one today, and a spawner that hands back no handle falls back to the old timeout
  behaviour. And `unknown` is honest rather than precise: killed before the answer nothing was
  written, killed after a `y` a note may be in the tree, and nothing here can tell which. **Only you,
  looking at the person in Gramps, can.**

---

## The eight refusals

Six are about naming a stored proposal wrongly; two are about the target. **Distinct types, distinct
messages, distinct tests** — and a test asserts *private* and *not found* do not produce the same
message.

| Refusal | When | What it says |
| --- | --- | --- |
| `ProposalNotFound` | the id names nothing awaiting approval — a retry, an id already consumed, or an id that is not the shape the store mints | *no proposal is awaiting approval under that name. One approve consumes one proposal, so a retry lands here — propose again.* |
| `ProposalCorrupt` | the stored file does not say what its own digest says it says | *the stored operation is not the operation this proposal's own digest covers, so the file has been edited since it was written.* |
| `ApprovalRulesChanged` | the rules that render and serialise an operation have moved since it was proposed | *the operation is unchanged; the rules that render and serialise it are not.* Names both fingerprints and both tool versions, and says: *propose it again and read the new sentence.* |
| `ProposalFromAnotherSession` | it was minted by a different run of the server | *nothing here can vouch for what was shown. Propose it again.* |
| `ProposalExpired` | it is older than the 15-minute TTL | *it was minted at `<time>` and stands for `<ttl>`. Propose it again.* |
| `ApprovalMismatch` | the digest supplied is not this proposal's digest | *the proposal being approved and the proposal being named are not the same thing. Nothing was written.* |
| `TargetIsPrivate` | the person carries `priv="1"` | *this person is marked private in the tree… **This is not 'no such person'** — they exist and are deliberately out of reach.* |
| `TargetNotInExport` | the export holds no person with that Gramps ID | *…if this person was added to the tree after the export was taken, export it again — until then nothing here can read their privacy flag, and this refuses rather than guess.* |

### Two orderings inside those eight, and both are the design

**1. The claim happens before any check.** The rename *is* the mutual exclusion; checking first and
renaming after leaves a window in which two concurrent callers are both still valid. The price is
stated rather than hidden: **any claim consumes the proposal, a refused one included.** A wrong digest
burns it and the agent must propose again — which costs you a second reading, and cannot cost you an
unapproved write.

**2. `ApprovalRulesChanged` is checked before `ProposalFromAnotherSession`.** The plan says the rules
fingerprint goes before any digest comparison, which is right and is not enough. Changing a rendering
rule means changing code, which means the server was restarted, which means the session id moved too
— so checking the session first would make `ApprovalRulesChanged` **structurally unreachable**,
reporting the restart (a symptom) in place of the rule change (the cause). There is a mechanical half
as well: under changed rules the stored operation may not be readable at all, so the integrity check
could raise rather than refuse.

### The rules fingerprint is measured, not remembered

A persisted digest is version-bound, and the premise that made slice 1's digest safe — both ends
computing it in one invocation, from one checkout — is gone the moment a proposal outlives the call
that minted it.

So a `rules_fingerprint` is stored beside every proposal. It is a digest over what a **fixed committed
probe operation** actually produces: its approval digest, its elided one-line preview, its full
display — plus every registered operation type's declared field names and the record layout's
version. Any change to `to_dict`, to a renderer, to `_PREVIEW_TEXT_LIMIT`, or to a dataclass's fields
moves the probe's answers and so moves the fingerprint. **Nothing has to be maintained by hand**,
which is the only version binding that stays true.

---

## What is NOT in this slice

- ⛔ **#66** (the 32,767-character Windows environment block). The operation still rides in
  `GRAMPS_LIVE_API_OP`, so **the MCP path inherits the cap**. It fails closed — Gramps does not
  launch, nothing is written — and the tool returns the underlying error for the agent to relay as
  *your note is too long on this machine*. Asserted by test.
- ⛔ **#59** (the plugin junction is not idempotent) — reachable; slice 2's setup still runs that step.
- ⛔ **#60** (`python` is the Store shim) — reachable, and **sidestepped rather than fixed** by
  registering an absolute interpreter path below.
- ⛔ **#62** (a lock refusal names the condition, not the remedy) — reachable, **and worse**, because
  the message now reaches an agent that will paraphrase it. Not fixed; `approve` relays the
  underlying message **verbatim**, asserted by test.
- ⛔ **#63** (`op.json` not ignored) — not reachable. The MCP path has no `op.json`.
- ⛔ **#72** (the verify run discards the plugin's error) — **filed, not fixed, and now reachable.**
  It makes exactly the failure an agent will report wrongly.
- ⛔ **#69** is closed *for the MCP path only*, as the bounded claim: *one approved proposal produces
  at most one write attempt.* Not *duplicates are impossible*. The CLI `apply op.json` path keeps
  #69's residual untouched.
- ⛔ Any operation type beyond `add_note`. No date model (#21) — `birth_year` is a label for
  recognising a person, and `birth_display` carries the record's own shape so a range stays a range.
  No identity operations (#22). No HTTP endpoint. No unattended or auto-approving path.

---

## ⭐ The SDK is an OPTIONAL EXTRA, and here is what it costs

**Ruling, 2026-08-16: the MCP server is not the core.** The core keeps `dependencies = []` — the
schema, the write path, the CLI console and `pii_guard` run on the standard library alone — and the
official SDK moves behind an extra named `mcp`. Somebody who wants slice 1's console installs nothing.
Somebody who wants an agent in front of it installs the extra, knowingly.

**CI enforces both halves rather than believing them**, because a dependency that arrived some other
way would leave a green board saying nothing:

| Leg | Installs | Proves |
| --- | --- | --- |
| **core** | `.[dev]` | `mcp` is **not importable**, and this distribution declares **no unconditional requirement**. Then lint, format, `mypy src/gramps_live_api`, `pytest -rs`. |
| **mcp** | `.[dev,mcp]` | `mypy src` — the whole tree against the real SDK — and then, from the JUnit report, that `tests/unit/test_mcp_server.py` **contributed test cases and none of them skipped**. |
| **pii-guard** | **nothing at all** | unchanged, and deliberately so: installing would write build artefacts into the checkout it exists to scan. |

⚠️ **The MCP leg's last step is the one that matters, and it is not a formality.** Making the SDK
optional means those tests skip when it is absent — and *skip when absent* silently becomes *never run
anywhere* the moment that leg stops installing the extra. **A skipped test reads exactly like a passing
one**, and this repository has already paid for that once (#31). So the assertion is on the
machine-readable report and it fails the job. It carries **no expected count**, on purpose: a number
here would be a count of a file rather than of a property, and it would go stale the next time somebody
adds a test.

### The dependency record, measured

Measured **2026-08-17** by resolving `mcp>=2.0.0` into an empty environment, `mcp 2.0.0`, `uv 0.11.12`.
**Re-derive it rather than trusting this table** — it is a property of one resolution on one day:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe "mcp>=2.0.0"
uv pip list --python .venv\Scripts\python.exe
```

| Platform · interpreter | Distributions installed | Besides `mcp` itself |
| --- | --- | --- |
| Windows · 3.10 | 31 | **30** |
| Windows · 3.12 | 30 | **29** |
| Linux · 3.10 | 29 | **28** |
| Linux · 3.12 | 28 | **27** |

**29 is the figure the ruling was re-affirmed at** — this machine, Windows on 3.12 — and the honest
statement is that it is between 27 and 30 depending on where you install it. It is **not** "three",
which is what an earlier note said.

What arrives, grouped by what it is for:

- **A whole HTTP and ASGI stack this project uses none of** — `starlette`, `uvicorn`, `httpx2`,
  `httpcore2`, `h11`, `sse-starlette`, `python-multipart`, `click`. The server speaks **stdio only**;
  `serve()` names the transport and a test asserts the word. The stack is installed and not reached.
- **Validation** — `pydantic`, `pydantic-core`, `annotated-types`, `typing-inspection`, `jsonschema`,
  `jsonschema-specifications`, `referencing`, `rpds-py`, `attrs`, `mcp-types`.
- **Cryptography and auth** — `cryptography`, `pyjwt`, `cffi`, `pycparser`, `truststore`. For OAuth
  flows on transports this project does not use.
- **Plumbing** — `anyio`, `idna`, `typing-extensions`, plus `colorama` and `pywin32` on Windows and
  `exceptiongroup` on 3.10.
- **`opentelemetry-api`** — see below, because a privacy project shipping a telemetry package owes an
  explanation rather than a shrug.

### ⚠️ `opentelemetry-api`: an API surface that is a no-op without an exporter

`mcp` imports it in three modules (`mcp/server/_otel.py`, `mcp/shared/_otel.py`,
`mcp/shared/jsonrpc_dispatcher.py`) to open spans around the JSON-RPC dispatch. **The claim below was
verified against the installed package on 2026-08-17, not taken on trust:**

- **The spans go nowhere.** With only the API installed, `opentelemetry.trace.get_tracer_provider()`
  returns a `ProxyTracerProvider`, `get_tracer(...)` returns a `ProxyTracer`, and a started span is a
  `NonRecordingSpan` whose `is_recording()` is `False`.
- **There is no exporter, and none can be selected.** The environment advertises exactly one
  `opentelemetry_tracer_provider` entry point — `opentelemetry.trace:NoOpTracerProvider`, registered by
  the API itself — and **zero** `opentelemetry_traces_exporter` entry points. `OTEL_PYTHON_TRACER_PROVIDER`
  makes the API load a provider *by entry-point name*, so on this install the only thing it can select
  is the no-op one.
- **There is nothing in it that can open a socket.** The distribution ships 30 Python modules. Parsed
  with `ast` rather than read by eye: the one occurrence of `import requests` is inside a module
  **docstring example** and is not an import at all, and the three `urllib` imports are
  `quote_plus` / `unquote_plus` / `unquote` — percent-encoding for W3C baggage header *values*.

**So this project does not phone home, and installing the extra does not make it start.** Emitting
telemetry anywhere would need `opentelemetry-sdk` **and** an exporter package; neither is a dependency
of `mcp`, neither is installed, and the core installs nothing at all. Bounded honestly: this is a
measurement of `opentelemetry-api 1.44.0` as pulled by `mcp 2.0.0`. It is not a promise about a version
nobody has resolved yet — re-derive it with the command above when the SDK moves.

### Why the SDK at all, stated narrowly

⚠️ **The earlier argument for using the SDK was OVERSTATED, and it is recorded here so that it is not
repeated as written.** It cited this project's *"freeze the definition from the published source"* rule.
**That rule governs checks whose meaning comes from the runtime** — `unicodedata.category` returning a
different answer on a different interpreter, `\s` meaning 26 characters where XML's `S` means 4 — where
the same code gives different verdicts on different machines and every test passes on the one that wrote
them. **Hand-rolling a protocol is not that.** A JSON-RPC loop written here would be wrong in ways our
own tests could catch, identically on every interpreter. Citing that rule here misapplies it.

**The real case is narrower and still sufficient:**

> **MCP is evolving, the SDK is its reference implementation, and slice 2's value is the product
> working — not this project owning a JSON-RPC loop.**

That is the whole argument, and it is enough. What it does **not** claim is that a hand-rolled client
would be untestable or unknowable; it claims that writing one is not what this slice is for. The
29-package cost is the price of that, paid knowingly, and the extra is where it is paid — so the cost
lands on the person who asked for an agent and on nobody else.

---

## Setting it up, once, beyond slice 1's three pieces

> **Every command here is PowerShell, run from the root of this checkout.**

### 0. Install the extra — the server does not run without it

```powershell
python -m pip install -e ".[mcp]"
```

⚠️ **The `mcp` extra is required to run the server**, and it is the only place this project has a
runtime dependency of any kind. Without it, `python -m gramps_live_api_mcp` raises
`ModuleNotFoundError: No module named 'mcp'` and `tests/unit/test_mcp_server.py` skips by name. Slice
1's console — `check`, `apply`, `approve` — needs none of it. Contributors want `".[dev,mcp]"`.

### 1. Export your tree, and tell the tool where it is

In Gramps: **Family Trees → Export** to Gramps XML. Then add the path to your configuration, beside
the two settings slice 1 already needed:

```powershell
$settings = "$env:APPDATA\gramps-live-api\config.json"
$current  = Get-Content $settings -Raw | ConvertFrom-Json
$current | Add-Member -NotePropertyName export_path -NotePropertyValue "<the .gramps file you just wrote>" -Force
$current | ConvertTo-Json | Set-Content $settings -Encoding utf8
```

Then check it:

```powershell
python -m gramps_live_api check
```

The report now carries an `export` line. **If it says the export is older than the copy, export
again** — see the staleness section above for why that is not a nag.

### 2. Register the server

```powershell
claude mcp add gramps -- "$PWD\.venv\Scripts\python.exe" -m gramps_live_api_mcp
```

⚠️ **The interpreter is named in full, deliberately.** On this machine a bare `python` is the
Microsoft Store shim, which is not this checkout's interpreter and reports a missing module (#60).

To see the three tools before an agent is involved:

```powershell
python -m gramps_live_api_mcp
```

and paste an `initialize` / `notifications/initialized` / `tools/list` exchange at it.

---

## The demo that defines done

| # | You type | You see |
| --- | --- | --- |
| 1 | `Find <a surname> in my tree.` | the agent calls `list_people`; the transcript shows a name, a birth year and a Gramps ID |
| 2 | `Add a research note to her: "…"` | the agent calls `propose_note` and shows you the returned sentence |
| 3 | `yes` | the agent calls `approve` — **a console window opens** |
| 4 | **`y`** *(in the window)* | the full sentence, `write this into <copy>? [y/N]`, then `note N00nn written` and `read back from a fresh process: '…'` |
| 5 | Enter | the window closes; the tool returns the note's Gramps ID to the transcript |
| 6 | — | **you open the copy in Gramps and find the note on that person** |

⚠️ **Step 3's `yes` is a courtesy. Step 4's `y` is the approval.** Step 6 is the only step that is
evidence.

⚠️ **Step 5 only reaches the transcript if you answer within about 45 seconds.** Take longer and the
agent is told `still_open` and told not to retry; the window is still live, your `y` still writes the
note, and step 6 still finds it. Nothing goes wrong — you just read the outcome in the window rather
than in the chat.

**Break it once on purpose**, which is worth more than the happy path: change `_PREVIEW_TEXT_LIMIT`
in `core/schema.py`, then approve a proposal minted before the change. The refusal must say plainly
that the **rules** moved and the operation did not. If it says anything about the operation instead,
the version binding is not doing its job.
