# Plan — #176: a full-name search finds nobody

**LIGHT tier.** It changes a read, not a write, and it touches no approval
surface. ⚠️ **But it is one function away from two bounds that were paid for**,
and the trade below is why the obvious route is not the one taken.

## The defect

`_name_spellings` returns the **name parts** — `first_name`, `surname`, each
surname in the surname list. `matches_term` asks whether the term is a substring
of **any one candidate**. So a term spanning given *and* surname is a substring
of neither part, and matches nothing.

Measured with the real functions: candidates `["Given", "Surname-ish"]`, term
`"Given Surname-ish"` → **False**; term `"Surname-ish"` → **True**.

⛔ **The failure direction is the whole problem.** Empty reads as *not in the
tree*, and that routes to **create** — see #177.

## ⭐ The trade: two routes, and why the obvious one is not taken

### Route 1 — split the term on whitespace, require every part to match

Obvious, and it handles arbitrary token counts and orders.

⚠️ **It changes what "contains" means for every caller of `matches_term`.** That
function serves `find_place`, `find_source` and `find_citation` as well; a place
search for `"North Street"` would begin matching a place named `"Street"` in a
region named `"North"`. Nothing asked for that.

⚠️ **It widens what matches, and the cap is downstream.** More rows match →
`RESULT_CAP` bites sooner → `withheld` rises. A search that used to return the
one right person could start returning the cap's worth of near-misses, and the
right person could be past the cap.

### Route 2 — add the JOINED spellings as candidates ⭐ **taken**

`_name_spellings` also emits `"<given> <surname>"` and `"<surname> <given>"`
beside the parts it already emits.

- **`matches_term` is untouched**, so no other caller changes.
- **Matching does not widen**: a person matches only if the term really is a
  substring of a name they hold, in one of two orders.
- **The alternate-name walk is preserved by construction** — this function
  operates inside a single `Name`, and `_person_names` still walks the primary
  and every alternate. The `Kuenkele`/`Künkele` case is untouched.
- **The privacy bound is out of reach**: `if _public(name) is None: return []`
  sits *above* this, so a private name still contributes no candidates. And
  `reads.bound` drops private rows before counting, which nothing here goes near.

⚠️ **What Route 2 does NOT do, stated rather than discovered later:** a query
carrying a middle name the tree does not store, or a comma form
(`"Surname, Given"`), still finds nobody. Route 1 would handle those. **That is
the cost of not changing `contains` for every caller**, and it is the trade being
accepted — not an oversight.

⛔ **No transliteration rules are invented.** `fold` already does NFKD +
combining-mark removal + casefold, and this change adds nothing to it.

## Bounded criteria

1. A full name in **either order** finds the person.
2. A **surname alone** still finds them, and a **given name alone** still does.
3. **Alternate spellings still match** — a person whose primary name uses one
   spelling and who carries another as an alternate is still found by the
   alternate.
4. A **private** person is still neither returned nor counted.
5. **A private NAME still contributes no searchable spelling** — the indexing
   half, which is the subtler of the two leaks.
6. The **cap applies** and `matched` stays honest.
7. **No other caller's behaviour changes**: `matches_term` is not modified.

## Falsifier

⛔ If adding joined spellings measurably widens what matches beyond the intended
full-name case — if any test shows a person matching a term they should not —
Route 2 is wrong and the question returns to whether `contains` should change at
all, which is a bigger decision than this defect warrants.
