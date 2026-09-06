# Status — 2026-09-03

**Where this project actually stands.** Dated, because a status page without a date is a claim with
no expiry. [`roadmap.md`](roadmap.md) is the older document and is history now; this page replaces
it as the statement of the current position.

⚠️ **This page says what is built, decided, next, and deliberately not planned.** It does not argue
any of it — the rulings do that, and the README says how the thing works.

## What works today

**Sixteen MCP tools**, in two groups. The set is asserted in the tests against what the server
actually exposes, not against a comment.

| Group | Count | The tools |
| --- | --- | --- |
| **Live reads of the open tree** | 14 | `find_people`, `find_place`, `find_source`, `find_citation`, `find_families`, `find_orphans`, `list_events`, `list_family_events`, `list_citations`, `list_associations`, `list_notes`, `tree_totals`, `tree_name`, `changed_since` |
| **Propose and approve** | 2 | `propose_document`, `approve_document` |

⛔ **It was nineteen in three groups until R9.** The third group held one tool, `list_people`, and it
read a Gramps XML **export** rather than the open tree — the only stale data path in the product. It
is retired with `propose_note` and `approve`; see *What was retired* below.

⛔ **Neither of the two reports what the owner decided.** `approve_document` answers *shown*, not
*written*.

**The document route.** An agent files a whole graph — people, families, events, places, a source,
citations, notes — and gets back an id and a preview.

⚠️ **That preview is not the one the owner reads, and the difference is deliberate.** The agent is
shown `caller_preview`, which names the Gramps IDs in the graph and **resolves no names at all** — a
preview saying *attaching to <a name>* would read as confirmation, when the only thing that can
confirm an identity is the tree, in the dialog, in front of the owner. The dialog renders a second
preview built from live tree reads, and **that** is the approval surface. The owner approves or
cancels there; a write is one transaction, and a cancel writes nothing.

⭐ The dialog's renderer is a **pure function of the graph and of what the tree answered**, which is
why the README can show a real render of it by handing it invented answers.

**Two real records have gone through it end to end.** ⚠️ That count is the owner's own, from
sessions run by hand and watched. **Nothing in this repository records them** — the contents are
personal data and the project's whole guard exists to keep them out — so the count is stated on his
authority, not demonstrated here.

**The push gate.** `scripts/hooks/pre-push` runs `pii_guard` over the range being pushed and refuses
a push that would publish personal data. CI also runs the guard, but CI runs `on: push` — by the
time its job starts GitHub already holds the objects, and on a public repository that is
publication. **CI detects; only the hook prevents.**

**The readiness script.** `python -m gramps_live_api check` reports on what can be checked from
the filesystem: the tree directory, its `.gramps-live-api-copy` sentinel, the installed runtime, the
plugin, and whether the push hook is current. ⚠️ **It cannot tell you Gramps is running with the
tree open, and does not try** — it never contacts a host, and it treats the tree's `lock` file as a
failure, because a locked tree is one Gramps is holding and this will not break that lock. **It is a
before-you-start check, run with the tree closed.** [`using.md`](using.md) says what each answer
means.

## What is decided

Four rulings are published, each recording a decision **and what it cost**.
[`rulings/`](rulings/README.md) is the index, and it is careful about one thing worth repeating:
**whether a ruling is in force and whether the code still matches it are two different questions**,
and only the first can be answered from that directory.

| | It ruled that |
| --- | --- |
| **[R3](rulings/R3-injection-under-live-reads.md)** — injection under live reads | Text in the tree may influence what the agent proposes, and that is not preventable at the read. The damage is bounded at the **write** instead. |
| **[R4](rulings/R4-graduation-to-the-live-tree.md)** — graduation to the live tree | The live tree may carry the sentinel and be written to, with a backup taken first. Recorded explicitly as a **downgrade**. |
| **[R7](rulings/R7-backup-with-gramps-open.md)** — backup with Gramps open | The backup uses SQLite's own backup against the live connection, and restore is **file replacement, not import**. |
| **[R8](rulings/R8-channel-architecture.md)** — channel architecture | The tool is a **Gramps addon inside the Gramps process**, with the MCP server a thin client holding no Gramps code. |

## What is next

**Four issues are active.** The ranking below is by what it costs to leave the issue alone —
correctness first, then hygiene.

⚠️ **This page said eight on 2 September.** Five of those have closed and one new one was filed, which is why the count below is four again. The five: the deletion-only push gate
([#193](https://github.com/randyjreid/gramps-live-api/issues/193)), the `propose_note` handle
([#64](https://github.com/randyjreid/gramps-live-api/issues/64) — the tool it was about is now
retired), the history walk
([#57](https://github.com/randyjreid/gramps-live-api/issues/57)) and the rules-digest defect
([#204](https://github.com/randyjreid/gramps-live-api/issues/204)) — **two of those as *dropped*,
not as done** — and the hand-maintained test counts
([#36](https://github.com/randyjreid/gramps-live-api/issues/36)), closed by an outside
contribution. The one filed since is [#218](https://github.com/randyjreid/gramps-live-api/issues/218),
which is what #36's replacement does not yet check. See what was retired, below.

⚠️ **This is a snapshot.** A row means the issue is open, not that nobody has started it. The tracker
is what is current; this page says what the ranking was on the date at the top.

| | Issue | Why it ranks here |
| --- | --- | --- |
| 1 | [#173](https://github.com/randyjreid/gramps-live-api/issues/173) — the SDK pin that holds refusal reasons open | ⚠️ **Not a live defect — an upgrade blocker.** SDK 2.1.1 discards a refusal's reason, so `private` and `not found` become one answer at the transport, and that distinction is what ruling 1 is about. A `<2.1` pin holds the floor and a test fails if it is relaxed. The pin is a stopgap; the fix is to stop depending on the SDK to carry a reason. |
| 2 | [#168](https://github.com/randyjreid/gramps-live-api/issues/168) — role and description are flattened onto the event | Gramps models role per participant; the proposal cannot say so, so two people at one event arrive indistinguishable. |
| 3 | [#76](https://github.com/randyjreid/gramps-live-api/issues/76) — duplicate eventref handles are counted twice | Produces a warning about an ambiguity that does not exist, which teaches the reader to skip warnings. |
| 4 | [#218](https://github.com/randyjreid/gramps-live-api/issues/218) — the acceptance-count check does not assert every count was paired | The check that replaced the hand-maintained counts asserts that *some* counts parsed, not that every `**N tests**` statement was matched to a path. A statement written in an unrecognised shape is silently unwatched, which is the failure the check exists to prevent. |

## What is deliberately not planned

⭐ **Sixty-eight of the seventy-two open issues are labelled
[`untriggered`](https://github.com/randyjreid/gramps-live-api/issues?q=is%3Aopen+label%3Auntriggered),
and leaving them there is a decision, not a backlog that got away.**

They are review findings — real ones, each a genuine gap somebody could construct. **What none of
them has is a case where the gap actually bit.** The rule this project runs under is that hardening
work needs a defect or friction someone hit, recorded before the work starts; without that trigger
the queue fills with findings a reviewer generated and nobody ever met.

⛔ **They are not closed**, because they are not wrong. They are parked, and any one of them
graduates the moment it costs somebody something. **The evidence for doing it this way is this
repository's own:** one component once drew about 116 findings over some 27 review rounds without
converging, every finding real, against a property that had no fixed point.

## What was retired

| | What replaced it |
| --- | --- |
| **Unwritable by construction** — the live tree could not be a write target at all | R4's weaker guarantee: writes are permitted with a verified backup taken first. Recorded as a downgrade rather than presented as equally safe. |
| **A three-tool MCP surface** | Sixteen: fourteen live reads and two propose-and-approve verbs. |
| **The addon as unwritten** | `gramps_plugin/` is written and loads at Gramps startup. |
| **Two handover documents** | Deleted on the owner's approval once the work they described had shipped; the README and this page carry what survived. |
| **A "still holds" column in the rulings index** | Deleted. It was written from the rulings and never checked against the source, and was wrong four times in five review rounds. |
| **The anchored history walk** — skip the prefix a clean scan already proved | Nothing. The guard walks the whole history again, as it always did. It was built, reviewed and dropped: the skip needed a digest describing the rules actually running, and four mechanisms were each defeated by a different interpreter caching behaviour — the last by disagreeing between Python 3.10 and 3.12 on the same commit. **The ~145 s saving was real; it was not worth a guard that may trust an anchor written under rules that are not the rules that run.** [#57](https://github.com/randyjreid/gramps-live-api/issues/57), and the cost is refiled as [#207](https://github.com/randyjreid/gramps-live-api/issues/207). |
| **[`roadmap.md`](roadmap.md) as the current plan** | This page. The roadmap still describes three tools, writes that only ever target a copy, and an unwritten addon. It is kept because the open questions it records are still the real ones. |

⛔ **The note flow is retired, and this paragraph used to say the opposite.** It read *they are not
retired; they are simply not the route the project is built around*, about `propose_note`, `approve`,
`list_people` and the `preview`/`apply` CLI commands. [R9](rulings/R9-retire-the-note-flow.md) ruled
them out and the retirement has shipped, so **the document route is now the only write path an agent
can reach**, and every write path takes a backup first.

⭐ **What went with them is worth naming, because it is more than three tools.** The Gramps XML export
reader and the `export_path` setting — the only stale data path in the product; the separate-process
approval console; the `AddNote` and `AddCitation` operations; and the CLI's `preview`, `apply` and
`approve` subcommands. `check` survives, repointed at the host registration.

⚠️ **The cost, accepted rather than glossed.** The console was a window this server held no handle on
and could not type into. What remains is the modal dialog inside Gramps, which is a different trust
argument and the weaker of the two.
