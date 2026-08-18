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
| the server waits, up to 45 seconds | polling for the console's report |
| our timeout fires first | `approve` returns **`still_open`** — the window is live, the write may yet happen, **do not retry**, and the message names where the answer will appear |
| the client times out first | the agent sees a transport error; the state is identical, because the proposal was consumed before any of this |
| you type `y` at any later point | **the write proceeds.** The console writes the note, reads it back, and files its report |
| you type `n` at any later point | nothing is written; the report says `declined` |

**The write proceeding after a timeout is the acceptable answer**, and it is reported as an outcome to
relay rather than one to retry. A second note needs a second `propose_note`, a second console, and
**you saying yes a second time** — which is the correct place for a duplicate to become possible
(issue #69).

⚠️ **45 seconds is a guess about client behaviour, not a measurement**, and it is not what makes any
of this safe. It only decides whether the agent receives a defined answer or an undefined one.

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

## Setting it up, once, beyond slice 1's three pieces

> **Every command here is PowerShell, run from the root of this checkout.**

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

**Break it once on purpose**, which is worth more than the happy path: change `_PREVIEW_TEXT_LIMIT`
in `core/schema.py`, then approve a proposal minted before the change. The refusal must say plainly
that the **rules** moved and the operation did not. If it says anything about the operation instead,
the version binding is not doing its job.
