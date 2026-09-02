# Status — 2026-09-02

**Where this project actually stands.** Dated, because a status page without a date is a claim with
no expiry. [`roadmap.md`](roadmap.md) is the older document and is history now; this page replaces
it as the statement of the current position.

⚠️ **This page says what is built, decided, next, and deliberately not planned.** It does not argue
any of it — the rulings do that, and the README says how the thing works.

## What works today

**Nineteen MCP tools**, in three groups. The set is asserted in the tests against what the server
actually exposes, not against a comment.

| Group | Count | The tools |
| --- | --- | --- |
| **Live reads of the open tree** | 14 | `find_people`, `find_place`, `find_source`, `find_citation`, `find_families`, `find_orphans`, `list_events`, `list_family_events`, `list_citations`, `list_associations`, `list_notes`, `tree_totals`, `tree_name`, `changed_since` |
| **Propose and approve** | 4 | `propose_document`, `approve_document`, `propose_note`, `approve` |
| **Export-backed** | 1 | `list_people` |

⛔ **None of the nineteen reports what the owner decided.** `approve_document` answers *shown*, not
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

**Eight issues are active.** The ranking below is by what it costs to leave the issue alone —
friction met in a working session first, then correctness, then hygiene.

⚠️ **This is a snapshot, and several of the eight have work open against them.** A row here means the
issue is open, not that nobody has started it. The tracker is what is current; this page says what
the ranking was on the date at the top.

| | Issue | Why it ranks here |
| --- | --- | --- |
| 1 | [#193](https://github.com/randyjreid/gramps-live-api/issues/193) — a push that only deletes files is refused | The gate that prevents publication is the one blocking ordinary work, and a gate worked around is a gate turned off. |
| 2 | [#57](https://github.com/randyjreid/gramps-live-api/issues/57) — the guard's history walk grows with the repository | Measured at 12 s over 36 commits, 34.6 s over 74, 71.8 s over 193. It gets worse every commit, and it sits in front of every push. |
| 3 | [#204](https://github.com/randyjreid/gramps-live-api/issues/204) — the rules digest can record rules that never ran | Reproduced. A same-length edit inside one second leaves a stale `.pyc` acceptable, so the old guard scans while the new source is hashed — and the anchor then licenses skipping a prefix nobody checked under those rules. |
| 4 | [#64](https://github.com/randyjreid/gramps-live-api/issues/64) — `propose_note` wants a handle only the export can give | ⚠️ **Reachable, but not from the live surface.** No live read publishes a handle; only the export-backed `list_people` does, and that is a snapshot which can be stale. The older write verb is the one thing still tied to it. |
| 5 | [#173](https://github.com/randyjreid/gramps-live-api/issues/173) — the SDK pin that holds refusal reasons open | ⚠️ **Not a live defect — an upgrade blocker.** SDK 2.1.1 discards a refusal's reason, so `private` and `not found` become one answer at the transport, and that distinction is what ruling 1 is about. A `<2.1` pin holds the floor and a test fails if it is relaxed. The pin is a stopgap; the fix is to stop depending on the SDK to carry a reason. |
| 6 | [#168](https://github.com/randyjreid/gramps-live-api/issues/168) — role and description are flattened onto the event | Gramps models role per participant; the proposal cannot say so, so two people at one event arrive indistinguishable. |
| 7 | [#76](https://github.com/randyjreid/gramps-live-api/issues/76) — duplicate eventref handles are counted twice | Produces a warning about an ambiguity that does not exist, which teaches the reader to skip warnings. |
| 8 | [#36](https://github.com/randyjreid/gramps-live-api/issues/36) — hand-maintained test counts go stale | A documented number that once matched is the worst kind of stale, because it reads as considered. |

## What is deliberately not planned

⭐ **Sixty-three of the seventy-one open issues are labelled
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
| **A three-tool MCP surface** | Nineteen: fourteen live reads, four propose-and-approve verbs, and one export-backed read. |
| **The addon as unwritten** | `gramps_plugin/` is written and loads at Gramps startup. |
| **Two handover documents** | Deleted on the owner's approval once the work they described had shipped; the README and this page carry what survived. |
| **A "still holds" column in the rulings index** | Deleted. It was written from the rulings and never checked against the source, and was wrong four times in five review rounds. |
| **[`roadmap.md`](roadmap.md) as the current plan** | This page. The roadmap still describes three tools, writes that only ever target a copy, and an unwritten addon. It is kept because the open questions it records are still the real ones. |

⚠️ **The `apply` CLI command and the older `approve` console flow still exist and still write, and
neither takes a backup.** [`restoring.md`](restoring.md) says so in its opening lines. **They are not
retired; they are simply not the route the project is built around.** `preview` is read-only — it
validates an operation and prints the sentence, loading no tree and calling no writer.
