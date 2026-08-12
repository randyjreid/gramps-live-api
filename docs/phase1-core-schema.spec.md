# Phase 1 — `core/schema`

**Milestone:** `Phase 1 - core/schema` · **Tracking issue:** #19

This is the authoritative specification for Phase 1. It was drafted before the phase began, redacted,
and committed here at intake — because a specification that lives only in a scratch directory is a
specification the next reader cannot find.

⚠️ **Every path and every genealogical value in this document is described rather than spelled.** The
guard scans everything committed, and a document about an operation model that quotes genealogy
formats is exactly the kind that trips it. `docs/pii-guard-acceptance.md` is written under the same
constraint and explains why.

---

## Goal

Define the **operation model** — the vocabulary in which an agreed genealogical fact is expressed
before it is written to the tree — and validate it as far as the frozen Phase-1 rule table allows,
**without a database**.

This is the contract every later phase speaks. `core/apply` executes these; `bridge/server` accepts
them over HTTP; the MCP client emits them. Getting the vocabulary wrong is expensive later, which is
why it comes before the write path.

## Why this exists — the workflow it has to serve

A human reads a record, extracts facts, and **agrees them**. Only then is anything written. The
operation model is what "the agreed extraction" looks like in machine-readable form, so that what was
agreed and what is written are provably the same thing.

Two consequences bind the design:

1. **Every operation must be renderable as human-readable prose for review before it executes.**
   If an operation cannot be described in one sentence a person can check against a record, it is the
   wrong granularity.
2. **Every operation carries provenance.** A fact enters the tree because a specific piece of
   evidence supports it. An operation that asserts a fact with no citation is the failure mode this
   whole project exists to avoid.

---

## ⭐ The validation boundary — state it, do not blur it

Schema validation without a database is **necessarily incomplete**. The danger is a module that feels
authoritative and silently defers the real checks to `core/apply`.

- **Phase 1 validates** — shape, required fields, enum membership, type correctness, internal
  consistency (a date range whose end precedes its start), reference *syntax*, and provenance
  presence.
- **Phase 3 validates** — existence (does this handle resolve?), referential integrity, duplicate
  detection, and anything requiring tree state.

A validated operation is **well-formed, not correct.** The module docstring says so, and a test
asserts that a syntactically perfect reference to a nonexistent object passes Phase 1. The result
type is named `WellFormed`, not `Valid`, so the distinction is hard to misread.

⚠️ **This boundary is a frozen table, not prose.** *"Validate as far as is possible without a
database"* was the original wording and it has no fixed point — a reviewer can always name one more
check that is possible. Each validation rule is declared in a table mapping its id to `PHASE_1` or
`PHASE_3`, and a structural test asserts that every rule the validator can emit appears in the table
and that no `PHASE_3` rule can fire from `validate`. The exit condition is *"the table is total and
nothing outside it fires"*, which closes.

**Residual, stated rather than chased:** *which* rules belong on which side is judgement, not proof.
The table makes the classification visible and reviewable; it does not make it correct.

---

## Decisions

These were open questions in the draft. All are ruled; a spec carrying open questions after they are
answered is the stale-artifact defect this phase is separately fixing in `README.md` (#24).

**D1 — Dates: the Gramps dependency.** Genealogical dates are not dates. They are ranges,
approximations, spans, partial dates, dual dates, and non-Gregorian calendars, and the model must
express uncertainty rather than flatten it — the motivating case is a birth year attested by several
sources that divide evenly between two adjacent years, which a single-value model cannot hold.

Verified from package metadata: the Gramps distribution publishes a pure-Python `py3-none-any` wheel
whose only mandatory dependency is a JSON library, with the GTK bindings behind optional extras. So a
dependency in `core/` is **possible**, and "no Gramps dependency" was a choice rather than a
constraint.

**Ruled: use Gramps' `Date` model directly.** A wrong date silently written into a tree is the
expensive failure here, and a hand-rolled model mapped in `core/apply` puts a lossy translation layer
exactly where bugs live.

⚠️ **Conditional on an import check that runs first.** Metadata proves declared dependencies, not the
import graph — it does not prove the data-model module imports without GTK present. If the import
fails on any of 3.10, 3.11 or 3.12, **fall back to a hand-rolled model and record why.** The
distribution also declares no minimum Python version, so our own CI matrix is the only thing
enforcing our floor.

**D2 — References.** Gramps has internal handles (opaque and stable) and Gramps IDs (user-visible and
mutable). **Recommended, not mandated:** handles as machine identity, Gramps IDs as the
human-readable rendering, with the preview required to show the ID and never a bare handle — an
operation a person cannot check is not reviewable. The plan gate for #20 may override this with
reasoning. External identifier systems are out of scope.

**D3 — Closed or extensible operation set. Ruled: closed.** The provenance partition below is what
makes this phase's most important property assertable, and it requires a closed registry. An open set
makes that property unfalsifiable, which is the Phase 0 failure mode relocated into the vocabulary.
If extensibility is ever wanted it arrives with forced classification at registration, as a
later-phase decision.

**D4 — Delete operations. Ruled: not in Phase 1** (#25). Modelling delete is harmless in itself —
Phase 1 writes nothing — but it puts a delete operation into the vocabulary `core/apply` is expected
to implement, and the backup mechanism exists precisely to precede that. The closed registry makes
adding it later cheap.

---

## The provenance rule

**No operation may assert a genealogical fact without a citation reference.**

⚠️ **The exceptions are a partition, not a list.** The draft said *"a note or a to-do is not a
genealogical fact and is the obvious exception; name any others you find"* — an open exception list
pointed forward, which is a fail-open by construction on the one property that matters most here.

Instead: every registered operation is in **exactly one** of `FACT_ASSERTING` or `NON_FACT`. A
structural test asserts the partition is total and disjoint over the registry, so **an operation
added without being classified fails the build.**

**What this does not catch:** a misclassification — a fact-asserting operation placed in `NON_FACT`.
The partition proves totality, not correctness. Every `NON_FACT` member therefore carries a one-line
recorded rationale, and that is what review checks.

---

## The operation set

Derived from real research work rather than invented. `add_citation` is the most common single
operation: attaching evidence to an object that already exists.

| Operation | Issue | Why it is here |
| --- | --- | --- |
| `add_citation` | #20 | Attach evidence to an existing object |
| `add_note` | #20 | Research notes and to-dos, attached to any object |
| `add_event` / `update_event` | #23 | Birth, death, burial, residence, immigration — the bulk of the work |
| `add_source` | #23 | A register or record set, cited in a recognised citation style |
| `add_media_reference` | #23 | Link an evidence image already on disk |
| `add_person` | #22 | Newly discovered individuals |
| `add_place` | #22 | Places must match an external place authority's naming, not be invented |
| `update_name` | #22 | Variants, spelling corrections, and misread transcriptions |
| `link_child_to_family` / `link_spouse_to_family` | #22 | The relationships that are the actual product |
| `delete_event` | #25 | **Deferred** — see D4 |

`add_citation` and `add_note` are built first, together, because they exercise both sides of the
provenance partition while needing no date model.

---

## Acceptance criteria

**Carried by the issues, not by this document**, so that each is sized to one pass through the loop
and none carries an unbounded exit. #20 (spine) · #21 (dates) · #22 (identity-side) · #23
(evidence-side) · #24 (README) · #25 (delete, deferred).

Every one of them additionally carries the standing gates: `ruff check .`, `ruff format --check .`,
`mypy src` and `pytest` all clean; the PII guard reporting zero findings over tracked content and
over the pushed range; CI green on 3.10, 3.11 and 3.12.

Three criteria are written **structurally** — over the registry rather than over a hand-written list
of cases — for the reason `B5` in `docs/pii-guard-acceptance.md` gives: an enumeration fails on the
case nobody listed, and this module's most persistent defect shape is one spelling taught to one
matcher. Those three are the provenance partition, the rule table, and the preview.

⚠️ **One thing the criteria deliberately do not claim.** *"A sentence a person can check against a
record"* is a human judgement and is **not** an acceptance criterion — it is a reviewer checklist
item. The mechanical preview checks are proxies for it. The proxy carrying real weight is *no bare
handle*: a preview naming an opaque handle is not reviewable at all.

## Out of scope — do not build

- Any database access, any `DbTxn`, any `commit_*` — that is `core/apply`
- The HTTP layer, MCP code, GTK code
- The backup mechanism
- Existence or referential-integrity checking of any kind
- Any operation that writes
- Any delete or destructive operation
- Free-text date parsing, date arithmetic, and calendar conversion
- External identifier systems

## Stop and report rather than deciding

- Any question that cannot be answered without building the write path first
- Any need for a dependency beyond the current set — including a second Gramps-side dependency
- Any contradiction between criteria
- Any gate that cannot pass without weakening it

## Working rules

- **TDD.** Red, green, refactor, one thing at a time. No production line without a failing test that
  demanded it, and the failing test is shown with its assertion text in the commit or the review.
- A plan gate precedes every build, every fix round, and every refactor. Produce the plan and stop.
- Branch per issue off the merged default branch. Never commit to it directly.
- Conventional commits.
- Fixtures use **invented surnames only**, and no date, name or place from any real tree.
- Do not trust your own account of state: run the commands and report what they say.
