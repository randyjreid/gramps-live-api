# Handover — the document write route

**Branch `document-write-route`, not pushed.** Two commits.

⚠️ **Gramps is running right now with a dialog waiting for you.** See *"There is a
dialog on screen"* at the bottom before you do anything else.

---

## The question that had to be answered first, and it is answered

**Can the host show a modal GTK dialog from inside a `GLib.idle_add` callback,
and does the write still land after you click?**

⭐ **Yes, measured, before anything was built on it.** `spike/dialogprobe.py`, a
throwaway plugin:

```
worker thread   -> GLib.idle_add(...)        (the worker does NOT wait)
callback        -> running on MainThread, 0.0209 s after scheduling
dialog.run()    -> a NESTED main loop, from inside the idle callback
                -> RETURNED OK after 3.936 s
DbTxn           -> committed, read back: note N0061, 62 notes total
*** THE WRITE LANDED ***
```

The dialog answered itself on a timer so no human was needed. A physical click
and `dialog.response()` reach `dialog.run()`'s return by the same path.

## What works

**All three build steps are done and verified.**

### 1–3. The graph, written in one transaction, with local ids resolved

`spike/writeprobe.py` called the real `gramps_live_api_writer.write` with a whole
invented census household and read every object back out:

| | |
| --- | --- |
| written in | **0.067 s** |
| people / events / places / families / sources / citations / notes | **+4 / +4 / +2 / +1 / +1 / +1 / +1**, exactly as proposed |
| genders | correct on all four |
| birth in the **birth slot** (not a generic event ref) | Tobias ✓ Marigold ✓ |
| **two-sided family links** | parents `as_spouse=1`, children `as_child=1` |
| **local id resolution** | `f1`'s parents resolved to Ambrose and Serafina, children to the other two |
| citations | landed on all four people and on the residence event |

⭐ **Dates are better than the fallback I wrote for them.** `1848-04-11` parsed;
`1861` became `1861-00-00`; and **`"the third of May 1854"` was kept by Gramps'
own parser as a text-only date** rather than dropped. No date parser was written.

### The route

`POST /document`, answering **202 immediately**:

```
$ post one-person.json
HTTP 202
{"ok": true, "shown": true}
```

⛔ **It does not hold the connection while you read.** `Marshal` has a
five-second timeout, so waiting for your answer would 503 in the middle of you
deciding. The agent learns **no outcome** — you find out by looking at Gramps.

### The safety rail, proved in both places

With the sentinel temporarily **moved aside** (never deleted):

- `propose_document` refused at propose time — it resolves the store through
  `apply.authorise`, so a proposal cannot even be *stored* against an unblessed
  tree;
- the route refused with **403** and a message naming the tree:
  *"…6a821852 has not been blessed for writing. Create a file named
  .gramps-live-api-copy … Nothing was touched."*

The sentinel was put back and verified present.

### The MCP chain

```
propose_document  -> proposal_id 50f8c0615db48f09
                     summary "1 people, 1 citations, 1 source"
                     preview says CREATED AS NEW
approve_document  -> {"shown": true, "status": 202}
host.log          -> document: showing 1 people, 1 citations, 1 source
```

⭐ **`approve_document` loads the server's own stored record.** The proposal id
says *which* proposal; it supplies no part of what the dialog shows. That is what
carries slice 2's approval binding across from a console the server held no
handle on to a dialog inside Gramps.

## What does NOT work, or is not done

- ⛔ **Nothing is matched against people already in your tree.** Everything is
  created new, every time. Run the same document twice and you get two families.
  The dialog says so in capitals at the top.
- ⛔ **Media is not attached.** The old spike attached the image to the source;
  the graph has no `media` collection and I did not add one.
- ⚠️ **I could not click the dialog myself**, so the two halves — dialog and
  writer — are each proved separately rather than in one run. `_present` composes
  them and is the one line of this that no probe has executed end to end. **Your
  click is that test.**
- **No test was written for the new code.** The task did not ask for one and the
  probes were faster to iterate with.

## Tests I changed, and why

- **`test_exactly_three_tools_are_exposed` → renamed** to
  `test_the_exposed_surface_is_exactly_what_the_server_says_it_is`, and
  `TOOL_NAMES` went from three to five. **The count was never the criterion** —
  the criterion is that the surface is enumerated from what the server actually
  exposes. ⭐ Its sibling, *"there is no second tool that could report the
  outcome"*, **still passes unchanged**, because `approve_document` answers
  *shown*, not *written*.
- **`spike/` is gitignored** rather than tracked. `pii_guard` flagged
  `writeprobe.py` as P2 genealogy data — correctly, since it holds a dense block
  of GEDCOM-X keys — and that does not belong in tracked content on a public
  repo, invented values or not. The files stay on disk so the instrument is not
  lost with the run, which is what happened to the last spike's probe.
- **The old spike tool** (`gramps_live_api_document.py` + `.gpr.py`) is
  **deleted**. Its write half lives on in `gramps_plugin/gramps_live_api_writer.py`;
  its tool registration and `claude -p` call are gone, as the brief asked.

**Everything else is green: 1504 passed, 6 skipped, ruff clean, mypy clean.**

## Two things the existing gates caught, and were right about

1. **The boundary test refused `_present` reaching `dbstate.db`** on its first
   run — correctly, since that file is host code by the `host_sources` rule. It
   now calls `accessor.blessing()`.
2. **`ModuleNotFoundError: No module named 'gramps_live_api_writer'`** on the
   first real request, with the route already answered 202 and the failure
   visible **only in `host.log`**. Gramps `exec`s plugins rather than importing
   them, so the plugin folder is not on `sys.path`. `_put_the_package_on_the_path`
   now adds it.

---

## There is a dialog on screen

I ran the chain to prove it, and **the dialog is still up** — I cannot click it,
and a modal dialog holds Gramps open, so `CloseMainWindow` did not work and
⛔ **I did not force-kill it.**

It offers to write **one invented person, "Peregrine Standlake"**, with a source
and a citation. **Either button is fine:**

- **Cancel** — writes nothing, and Gramps is yours again.
- **Write it** — you will see the whole thing work, and get one more test person.

## Then, to try it properly

1. Gramps open on **RandyReid-Testing** (the blessed copy). Branch
   `document-write-route` must be checked out — the plugin loads through the
   junction. ⛔ Never switch branches while Gramps is running.
2. ⚠️ **Restart your MCP connection.** The server gained two tools and your
   client is holding the old list.
3. Give Claude a scan in conversation and ask it to put the household in your
   tree. It should call `propose_document`, show you the preview, then
   `approve_document`.
4. **The dialog appears in Gramps. Click "Write it".**
5. Look at the People view.

**If nothing appears:** `%APPDATA%\gramps-live-api\host.log` is the only place a
failure is visible. `load_on_reg` swallows exceptions and the AIO has no console.

## Artifacts left in the blessed copy

All invented; none from any real record.

| what | ids |
| --- | --- |
| dialog probe note | **N0061** |
| write probe note | **N0062** |
| write probe people | **I0016** Ambrose · **I0017** Serafina · **I0020** Tobias · **I0021** Marigold, all "Quillfeather" |
| write probe places | **P2248** Whitmarsh Hollow · **P2249** Saint Bede under Wold |
| write probe source | **S0010** Whitmarsh Hollow census, 1861 |
| plus | 4 events, 1 family, 1 citation linking those people |

⛔ **Nothing was deleted and no `lock` file was touched.** Both trees were
lock-free before each restart.

## The single next thing I would do

**Person matching, or at least a warning.** Everything else here is honest about
its limits, but *"run it twice and you get two families"* is the one that will
bite in real use — and the moment this points at a real document, the people in
it are likely to be people you already have.

⚠️ **It needs a ruling before it needs code:** matching means the tool proposes
*changes to existing people*, which is a different act from adding new ones, and
R3's acceptance criterion — *no byte reaches the tree that was not rendered in
full to the human* — has to be re-read against a diff rather than an addition.
