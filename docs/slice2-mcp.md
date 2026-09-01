# Slice 2: an agent puts a note on a person, and you approve it at a console

> ⛔ **A RECORD OF SLICE 2, NOT THE CURRENT DESIGN.** It is accurate about what
> slice 2 built and is kept for the reasoning it holds. Four things it says have
> since changed, and they are the ones a reader will trip on:
>
> * **"three MCP tools"** — there are now **eighteen**: thirteen live reads, three
>   proposal and approval verbs, and `tree_totals`.
> * **"the copy"** — a write no longer targets a copy only. `R4` permits the live
>   tree, blessed by hand, **with a backup taken first**; see
>   [`rulings/R4-graduation-to-the-live-tree.md`](rulings/R4-graduation-to-the-live-tree.md).
> * **"a console"** — a document write is approved in a **dialog inside Gramps**,
>   rendered from the stored graph. The console flow described here is slice 2's.
> * **an XML export** — the reads run against the **open tree**, in-process.
>
> ⭐ The trust model below — binding separated from approval, the operation never
> travelling through the agent — is unchanged and is still the argument.


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

`approve` answers every question this host can be asked in advance — can a separate console be
opened, is a copy configured and blessed, is there a Gramps runtime to launch — and **only then**
claims the proposal, an atomic rename, so two concurrent approves cannot both proceed. The claim reads
the stored file first and renames it last, so a host that cannot read it burns nothing. Then it opens
a **new console window** running `python -m gramps_live_api approve <id>`. That process:

- reads the operation from the claimed file, not from anything the agent sent;
- prints the note **in full**, nothing elided, through the existing render guard;
- prints `write this into <copy>? [y/N]` and reads a real console stdin;
- on `y`, runs the **unchanged slice 1 write and read-back**;
- prints what happened, and stays open until you press Enter.

> ⭐ **CLAIMING IS THE LAST IRREVERSIBLE STEP.** The spawn happens *inside* the claim — `approve`
> hands it to `Store.claim_then` as the follow-through — and **a claim that cannot be followed
> through is rolled back**. That is a call boundary rather than a rule about which statements sit
> between two lines, because a rule of that shape is a fact about where somebody stopped typing.

⚠️ **Your `yes` in the chat is a courtesy. The `y` in the window is the approval.** If the two
disagree — if the window shows something other than what the transcript claimed — **the window is
right**, and that is the entire point of the design.

The threat this defends against is not you lying to yourself. It is that **your tree contains text
from arbitrary sources**, an agent reads it, and injection through a source note is a real path from
*read* to *write*. The console makes the human yes unforgeable the way the sentinel makes the live
tree unwritable.

### ⭐ Why there is a window at all — and why it is load-bearing already

**What the console establishes is mechanical, and all of it is about the text and the keystroke
rather than about the reader.** The operation is rendered by a **separate process**, out of the
**claimed file on disk** rather than out of anything the agent passed to `approve`, in full through
the existing render guard, into a **console this server holds no handle on** — `new_console` returns
nothing, so no object here refers to that window — and the `y` is read from that console's own
stdin. **Nothing in the wire carries any of it:** `approve` has no parameter that could supply the
keystroke and no reply that reports it.

⚠️ **Two things it does NOT establish, and both are on the residual list below rather than being
news.** It does not establish that anybody **read** what was rendered — item 1 says exactly that,
and item 3 is an agent proposing repeatedly in the hope of it. And it is a **UI defence, not a
cryptographic one**, item 2's phrase, because the store sits inside the copy and the agent runs as
the same user — item 4's one trust domain by construction. What survives both is the bounded claim
that list closes with, and the verb in it is chosen: *one approved proposal produces at most one
write attempt, of exactly the operation whose full text was **displayed** at a console the agent
cannot write to.*

**That much is still the whole reason for the window.** Take it away and *"the human approved"*
becomes a sentence the **agent** asserts, and from outside there is no difference between the agent
calling `approve` because you said yes and calling it because something it read told it to.

⚠️ **The paragraph above states that path in the present tense, and the present tense is right.**
`list_people` reads `name` and `birth_display` **verbatim out of the export** and returns both.
`name` is every recorded part of somebody's primary name, and `birth_display` carries a `datestr`
record's `val`, which the DTD declares `CDATA` — arbitrary prose, whatever the person who wrote the
record typed. An agent reads both before it calls `propose_note`. **So tree text already reaches the
agent, today, and the *read* to *write* path is open. The console is not guarding nothing.**

⚠️ **It is narrow in WHICH FIELDS it is, and not at all in what they can carry.** Nothing caps
either string: `_name` joins the parts it read, `_qualified` carries the `val` through, and `search`
bounds the number of people and requires a term — a count and a filter, neither of them a length.
Measured against the reader itself: a `<datestr>` whose `val` holds 3,200 characters of prose comes
back as a 3,200-character `birth_display`, on a person whose *name* is the ordinary 18 characters
the search term matched. **The field carrying a payload need not be the field that was searched
for.**

⚠️ **The name widening widened this in the dimension that was ever bounded — how many fields.** The
surname's `prefix` and `connector`, plus `call`, `suffix`, `title`, `nick` and `familynick`, all
reach the agent now where `first` and `surname` alone used to — the residual recorded under ruling 1,
read for what it means here rather than for what it means to privacy.

⚠️ **What the console bounds is narrower than the injection surface, and it is stated as such.** The
console sanitises nothing and makes injection no less possible: text out of the tree can still steer
what an agent *proposes*. What that text cannot do is **supply the `y`** — the operation is rendered
by another process out of the file on disk, and the keystroke comes from a keyboard. What it can
still do is put a proposal in front of a tired owner, which is item 3, and no window closes that.

⭐ **The trigger is a WIDENING, and a smaller one than a length argument would make it look. It stays
recognisable when it arrives: any tool that returns note, source or citation text.** It does not
raise a ceiling, because the measurement above says there is none: *short* is what a name and a date
label conventionally hold, not a rule about what they may hold, and a record holding otherwise is
read out verbatim like any other. What changes is which content is **ordinary**. Note, source and
citation text is the field whose *intended* content is unbounded prose written by whoever wrote the
record; today's surface wants a doctored record or an import that mangled something. **That is a
difference in how likely the payload is, not in whether it is possible** — worth planning for on
that ground, and not on the stronger one.

**So, to whoever builds that slice: the guarantee is already here, and it is the bounded one
above.** Do not invent a weaker one — an
approval flag in the reply, an outcome token, a `confirmed` argument the agent supplies — and **do
not delete this.** It is guarding a live path today, not a hypothetical one, and the tool you are
about to add widens that path rather than creating it. The reason is written down rather than left
implicit, because a guard whose reason is unrecorded is a guard somebody later removes.


⭐ **The trigger above has FIRED and been RULED.** R3 was decided on 2026-08-21 — **D + A**: injected text may influence what the agent proposes, the damage is bounded at the write, and structural fencing is defence in depth that closes no class of attack. The record is [`rulings/R3-injection-under-live-reads.md`](rulings/R3-injection-under-live-reads.md), and it carries the walk-through of the four mechanisms above as a named build precondition.
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

⚠️ **A name is WIDER than it was, and that widens this residual with it.** `list_people` used to put
`<first>` and `<surname>` into that context; it now puts every part of the recorded primary name that
a person would type when looking for someone — the surname's `prefix` and `connector`, plus `call`,
`suffix`, `title`, `nick` and `familynick`. **The reason is that the narrower string made #64's own
requirement false:** a person recorded as `<surname prefix="van">Ashenmoor</surname>` displayed as
`Ashenmoor`, and `list_people("van Ashenmoor")` returned nothing, so somebody could not be found by
their own recorded name — and a prefix is ordinary in genealogy, not an edge case. The claim is
stated **bounded** in `core.people._name`, over the closed set the schema declares: *every part of
the recorded name a person would type when looking for someone is searchable* — never *the name is
complete*, which has no fixed point. **Nothing new ABOUT a person reaches a model**: every part was
already in the export beside the two that were read, and the search term, the cap and the privacy
flag bound it exactly as before. What is new is that more of one person's name arrives at once.

⚠️ **`<group>` is the one part excluded on judgement rather than on kind, and it is recorded as a
residual.** It is Gramps' *group-as* override — which heading a person files under in a list — so
`Name.get_group_name` returns it **instead of** the primary surname and no Gramps name renderer emits
it. A record whose `group` differs from every surname it carries is therefore not findable by that
text. Where it is unset Gramps falls back to the surname, which is read.

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
either way. **That direction is deliberate.** This answer must err toward *this snapshot may not speak
for the copy*, never toward *the flag you are reading is current*.

⚠️ **What it must NOT do is name a remedy that cannot work, and until #77 it did.** The refusal said
*"export the tree again"*. You can only export from **inside** Gramps, and Gramps writes `sqlite.db`
and `meta_data.db` when it **closes** — 46 seconds after the export on the owner's own run — so every
export is older than the copy by the time Gramps has exited, and a second one reproduces the ordering
one cycle later:

```
export written : 20:09:44
sqlite.db      : 20:10:30      (written when Gramps CLOSED)
```

`Copy-Item` is the other thing that looks right and is not: it **preserves** `LastWriteTime` on
Windows, so the copy arrives stale carrying content that hashes identical to the fresh export.

**What clears it is re-stamping the export once Gramps is closed** — `(Get-Item
<path>).LastWriteTime = Get-Date` — which is honest rather than a trick: Gramps is shut, the tree has
stopped changing, and the file's content *is* the current export. ⚠️ **And it claims only that the
export is at least as new as the tree.** Nothing here opens the file, so somebody who stamps a
genuinely old export defeats the check entirely; the message says so, because prescribing a stamp
while implying it verifies the snapshot would trade one false remedy for another.

**What was NOT built:** `propose_note` does not itself refuse on a stale export. That would be a
second, stricter rule in a second place, and the plan asked for a `check` line. Recorded as a
residual: **the doctor tells you, and nothing stops you.**

---

## ⭐ What the agent can and cannot know

**It cannot learn the outcome. At all.** Not written, not declined, not failed, not unverified.
`approve` opens the window and returns; there is no token in the reply, no second tool to ask, and no
file to read. **The only route from that window to the transcript is you typing what you saw.**

The reply is exactly three keys, and a test freezes the set:

```json
{"proposal_id": "…", "console": "opened", "next": "…tell him a window has opened, and ask him what it said"}
```

| The agent learns | The agent does not learn |
| --- | --- |
| everything that happens **before the window opens** — every refusal in `core.proposals`, the platform refusal, the config, runtime and blessing refusals, a spawn failure | **anything that happens after it** — the note's Gramps ID, a decline, a refusal from inside Gramps, a read-back that disagreed |

> ⚠️ **An agent that asserts an outcome is asserting something it was not told.** Ask it what
> happened and the correct answer is *I do not know — what did the window say?* If it says the note
> was written and you did not tell it so, that is the thing to notice.

### Why this is the shape it is

The machinery that used to carry the outcome — polling, a 45-second timeout, `still_open`, `unknown`,
outcome words, a cross-process report file — **drew a review finding in four consecutive rounds**, and
each fix closed one stage of the two-process crossing while the next round found the adjacent stage.
Of the seven findings, five were that layer. **The ruling was to delete it rather than harden it: it
existed to tell an agent something a human was watching happen.**

**What stops an agent inventing an outcome?** Nothing in the wire, and this says so rather than
implying otherwise. What changes is the shape of the risk: there is no outcome word in the channel for
a fabricated one to borrow authority from, **you have just watched the window** and hold the ground
truth immediately, and the tool's own description instructs the agent to ask and relay verbatim.
It is the same residual as item 1 above — the agent can misrepresent things in its transcript — and
the same answer: **the window is right.** What was traded away is machinery that produced a *wrong*
outcome five different ways; what was traded in is a human who was already looking at the answer.

### The residuals of the deletion, recorded rather than discovered later

- ⚠️ **A real loss, accepted.** A console whose stream breaks while printing now tells **nobody**
  anything — the report used to catch part of that. The human is the only reader, and a broken
  console has no reader. What survives is the **exit code**, the handles printed before it, and the
  undo and result records inside the copy.
- **A process death between the claim and the rollback** orphans one `.pending.json`. One proposal,
  not a loop: propose again and the fresh id works. Nothing sweeps stale pending files and `check`
  does not report them — pre-existing, and more visible now that nothing polls.
- **The rollback rename can itself fail**, and then the proposal is burnt. The `OSError` is
  suppressed so that the *original* failure — the one that says why no console opened — is what
  reaches you, rather than being replaced by a rename error.
- **`BaseException` is deliberately not caught.** A `KeyboardInterrupt` landing after `CreateProcess`
  succeeded but before `Popen` returns would roll back a proposal whose console is **live** — two
  consoles for one proposal, which breaks the bounded claim below. Losing one proposal to an
  interrupt is strictly the better failure.
- **A gap between the server's pre-claim checks and the console's own.** The copy could stop being
  blessed in between. Transient, and the console refuses.

### Three more, recorded when the claim was reordered to read first

- **A Windows sharing violation can lose a claim that nothing else would have lost.** Reading the file
  before renaming it means a concurrent approve holds it open at the moment the other one renames, and
  Python's `open` omits `FILE_SHARE_DELETE`, so the rename can fail with `ERROR_SHARING_VIOLATION`.
  Transient, self-clearing on retry, and in the safe direction — nothing was renamed, so nothing was
  burnt. It could not happen under the old ordering, because nothing held the file open when the
  rename ran. **Traded knowingly** for the loop it replaces.
- ⚠️ **"Any claim consumes the proposal" becomes best-effort in one transient case.** The burn rename
  is suppressed like every other tidying rename, so a burn that fails now leaves the proposal at
  `.json` rather than at `.pending.json`. Better in every respect but one: a refusal is a decision
  about the *content* and so repeats identically on every retry — except `ApprovalMismatch`, the only
  refusal that depends on caller input, where a wrong-digest caller whose burn transiently fails no
  longer burns a proposal a correct approve can still claim. Same class as *the rollback rename can
  itself fail* above, in the other direction.
- ⚠️ **The loop is closed at the read and not at the rename, and that is a bound rather than a
  proof.** `ProposalUnreadable` covers a host that cannot *read* the store. A Windows ACL that denies
  DELETE on the directory while permitting create and write would instead fail the *claim rename*,
  every approve would get `ProposalNotFound`, and its *propose again* would loop — with nothing burnt
  and nothing written, so the cost is an agent retrying rather than the owner losing proposals. POSIX
  cannot produce that ACL, since rename and create need the same directory permission. **Recorded, not
  defended against**, and it is inside the claim machinery, where the standing rule is that the next
  finding is parked as a design question rather than fixed.

⭐ **The bounded claim is unchanged by all of this: one approved proposal produces at most one write
attempt.** `consume` runs before Gramps is launched, and the rollback cannot become a second route to
a claim — it runs only when the spawn *raised*, when no console exists, and a rolled-back proposal has
been shown to nobody and consumed by nothing.

---

## The nine refusals

Seven are about naming a stored proposal wrongly; two are about the target. **Distinct types, distinct
messages, distinct tests** — and a test asserts *private* and *not found* do not produce the same
message.

| Refusal | When | What it says |
| --- | --- | --- |
| `ProposalNotFound` | the id names nothing awaiting approval — a retry, an id already consumed, or an id that is not the shape the store mints. Also what the loser of a race gets, from its own rename failing: *this proposal was claimed by another approve, so this call did not get it and nothing was written.* | *no proposal is awaiting approval under that name. One approve consumes one proposal, so a retry lands here — propose again.* |
| `ProposalUnreadable` | the file is there and this host could not read it — an ACL, a sharing lock. **Nothing is consumed**, and it is deliberately not a `ProposalNotFound`: that one's whole vocabulary says *propose again*, and a fresh proposal lands in the same directory and reads the same way, which is the loop rather than a lost note | *the proposal is still here and still approvable, but this host could not read it: `<reason>`. Nothing was consumed. Fix the permission or the lock and approve the same id again — a new one would land in the same directory and read the same way.* |
| `ProposalCorrupt` | the stored file does not say what its own digest says it says | *the stored operation is not the operation this proposal's own digest covers, so the file has been edited since it was written.* |
| `ApprovalRulesChanged` | the rules that render and serialise an operation have moved since it was proposed | *the operation is unchanged; the rules that render and serialise it are not.* Names both fingerprints and both tool versions, and says: *propose it again and read the new sentence.* |
| `ProposalFromAnotherSession` | it was minted by a different run of the server | *nothing here can vouch for what was shown. Propose it again.* |
| `ProposalExpired` | it is older than the 15-minute TTL | *it was minted at `<time>` and stands for `<ttl>`. Propose it again.* |
| `ApprovalMismatch` | the digest supplied is not this proposal's digest | *the proposal being approved and the proposal being named are not the same thing. Nothing was written.* |
| `TargetIsPrivate` | the person carries `priv="1"` | *this person is marked private in the tree… **This is not 'no such person'** — they exist and are deliberately out of reach.* |
| `TargetNotInExport` | the export holds no person with that Gramps ID | *…if this person was added to the tree after the export was taken, export it again — until then nothing here can read their privacy flag, and this refuses rather than guess.* |

### Two orderings inside those nine, and both are the design

**1. The proposal is read first, and the rename is chosen once you know.** Invalid content is renamed
to `.refused.json` and then refused; valid content is renamed to `.pending.json` and then followed
through. `_claim` performs **exactly one** rename and it is its **last statement**, so everything that
can fail — the read, the parse, the six checks — happens where a failure costs nothing, because
nothing has moved yet.

⚠️ **The rename is the mutual exclusion, and being valid never was.** The earlier reasoning here said
the rename had to come first or two concurrent callers would both still be valid, which conflates
*being valid* with *being permitted*. Validity is a property of the file; the exclusion token is the
rename, because `os.rename` consumes its source atomically and cannot succeed twice for one source
however much happened before it. Two readers may both read and both validate. **Exactly one rename
lands**, and the loser learns it from its own rename failing rather than from a check: on POSIX and on
Windows alike `FileNotFoundError` when the source has already moved, and on Windows also
`PermissionError` (`ERROR_SHARING_VIOLATION`) while the winner still holds the file open for its read,
because Python's `open` does not ask for `FILE_SHARE_DELETE`. **Any `OSError` out of that rename means
the claim was not obtained**, so it aborts and never follows through — suppressing it would let a
caller that renamed nothing open a console, which is two consoles for one proposal and the bounded
claim gone with no error anywhere.

Burn-on-refusal is preserved as a **chosen act** rather than as a side effect of the old ordering, and
the price is stated rather than hidden: **any claim consumes the proposal, a refused one included.** A
wrong digest burns it and the agent must propose again — which costs you a second reading, and cannot
cost you an unapproved write.

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
  launch, nothing is written — and the underlying error reaches **you, at the console**, verbatim
  rather than paraphrased. Asserted by test. ⚠️ The cap is crossed after the window has opened, so
  the tool call has already returned and the agent is not told; that is the trade above.
- ⛔ **#59** (the plugin junction is not idempotent) — reachable; slice 2's setup still runs that step.
- ⛔ **#60** (`python` is the Store shim) — reachable, and **sidestepped rather than fixed** by
  registering an absolute interpreter path below.
- ⛔ **#62** (a lock refusal names the condition, not the remedy) — reachable. Not fixed; the console
  relays the underlying message **verbatim** rather than paraphrasing it, asserted by test.
- ⛔ **#63** (`op.json` not ignored) — not reachable. The MCP path has no `op.json`.
- ⛔ **#72** (the verify run discards the plugin's error) — **filed, not fixed, and reachable.** It
  makes exactly the failure that is hardest to read correctly off the window.
- ⛔ **#69** is closed *for the MCP path only*, as the bounded claim: *one approved proposal produces
  at most one write attempt.* Not *duplicates are impossible*. The CLI `apply op.json` path keeps
  #69's residual untouched.
- ⛔ Any operation type beyond `add_note`. No date model (#21) — `birth_year` is a label for
  recognising a person, and `birth_display` carries the record's own shape so a range stays a range
  and an estimated year reads as `1856 [quality=Estimated]` rather than as `1856`. The qualifier set
  is the schema's, per shape, bound by test to the frozen DTD table — not a rendering of a date.
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

The report now carries an `export` line. **If it says the export is older than the copy, do not
export again — close Gramps and re-stamp the file** (`(Get-Item <path>).LastWriteTime = Get-Date`),
which is what the refusal itself now tells you. See the staleness section above for why another
export cannot clear it, and for the one thing the stamp does not claim.

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
| 3 | `yes` | the agent calls `approve` — **a console window opens**, and the transcript says *a console window has opened on your machine; approve there and tell me what it says.* **The agent states no outcome, because it has none** |
| 4 | **`y`** *(in the window)* | the note in full, `write this into <copy>? [y/N]`, then `note N00nn written`, both handles, and `read back from a fresh process: '…'` |
| 5 | Enter *(in the window)* | `press Enter to close this window` — the window closes. **Nothing goes back to the transcript** |
| 6 | `it said N00nn written` | the agent relays it. **This is the only route the Gramps ID takes to the chat** |
| 7 | — | **you open the copy in Gramps and find the note on that person** |

⚠️ **Step 3's `yes` is a courtesy. Step 4's `y` is the approval. Step 7 is the only step that is
evidence.**

**Break it three times on purpose**, which is worth more than the happy path:

- **Decline.** Propose again and type **`n`**. The window says *nothing was written*. Then ask the
  agent what happened — **it must say it does not know.** An agent that asserts a decline is
  asserting something it was not told.
- **The rules moved.** Change `_PREVIEW_TEXT_LIMIT` in `core/schema.py`, then approve a proposal
  minted before the change. The refusal must name the **rules**, not the operation — and it reaches
  the agent, because it happens before the window. If it says anything about the operation instead,
  the version binding is not doing its job.
- ⭐ **The invariant.** Point `gramps_runtime` at a path that does not exist and call `approve`. It
  must be **refused in the transcript with no window opening**, and **the same proposal id must still
  be approvable** once the config is fixed. That is L2 and D-1's whole class, demonstrated rather
  than argued: a deterministic host precondition answered *after* the irreversible rename consumed a
  proposal every time, forever.

⚠️ **The demo cannot exercise a real spawn failure.** The runtime step above is the closest honest
proxy for it; a genuine `CreateProcess` failure is not reproducible on demand. The rollback keys on
*the follow-through raised*, not on which failure it was, which is what makes the proxy meaningful.
