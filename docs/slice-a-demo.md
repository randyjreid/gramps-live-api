# Slice A — the host answers

Four things to do at a keyboard with Gramps running. **No agent is involved anywhere in this**, and
nothing here writes to a tree.

⚠️ **CI cannot run any of it.** The runners have no Gramps, no `gi` and no tree; what CI proves is
listed at the bottom, and it is not this.

---

## Install it once

The plugin lives in `gramps_plugin/`, which is already the junction target `docs/using.md` sets up.
If that junction exists, the host is installed — it is a second plugin in the same folder, and
Gramps picks it up on the next launch.

```powershell
New-Item -ItemType Directory -Force "$env:APPDATA\gramps\gramps60\plugins" | Out-Null
New-Item -ItemType Junction -Path "$env:APPDATA\gramps\gramps60\plugins\gramps-live-api" -Target "$PWD\gramps_plugin"
```

⚠️ **A junction, not a copy.** The host finds its own source by resolving this link and stepping up
one level to the checkout, so a *copied* folder leaves it unable to import the package. If the
checkout is somewhere that cannot be reached that way, set `GRAMPS_LIVE_API_SRC` to the `src`
directory instead.

Then **start Gramps**. The host starts with it, before any tree is open.

## Where it wrote itself down

Three files, all in `%APPDATA%\gramps-live-api\`:

| File | What it is |
| --- | --- |
| `token` | the bearer token, minted fresh at every startup |
| `port` | the loopback port the operating system gave us |
| `host.log` | one line per startup, and the only place a failed start is visible |

```powershell
$state = "$env:APPDATA\gramps-live-api"
$token = Get-Content "$state\token"
$port  = Get-Content "$state\port"
Get-Content "$state\host.log" -Tail 3
```

The last line should read `INFO listening on 127.0.0.1:<port>; token protection=acl (…)`.

⚠️ **If there is no `port` file, read `host.log` instead of guessing.** A last line of `ERROR` means
the host started and failed, and says how. No log file at all means the plugin never ran — the
junction is wrong, or Gramps never reached the hook. `load_on_reg` swallows exceptions and the
all-in-one build has no console, so this file is the only observation there is.

---

## The four steps

### 1. With a tree open, ask for the tree

```powershell
Invoke-RestMethod "http://127.0.0.1:$port/health" -Headers @{ Authorization = "Bearer $token" }
```

Expected: `ok: True`, and a `tree` carrying `open: True`, the tree's **name** and a **person count**.

### 2. Close the tree in Gramps, and ask again

*Family Trees → Close* (leave Gramps running), then run the same command.

Expected: **200**, `ok: True`, `tree: @{ open = False }`. A clean answer, not a crash and not an
error — this is the state the host *starts* in, so a client that treated it as a fault would be
broken on every launch.

### 3. A bad token

```powershell
try {
  Invoke-RestMethod "http://127.0.0.1:$port/health" -Headers @{ Authorization = "Bearer not-the-token" }
} catch { $_.Exception.Response.StatusCode.value__ }
```

Expected: **401**.

### 4. An `Origin` header

```powershell
try {
  Invoke-RestMethod "http://127.0.0.1:$port/health" -Headers @{
    Authorization = "Bearer $token"
    Origin        = "https://example.invalid"
  }
} catch { $_.Exception.Response.StatusCode.value__ }
```

Expected: **403** — *with the correct token*, which is the point. This is what defeats
DNS-rebinding and CSRF from a page you happen to have open in a browser, and it has to shut that
door in front of the token rather than behind it.

---

## 5. The person probe — the number F3 is actually about

⭐ **Added by slice A2, and it is a measurement instrument rather than a feature.** Issue
[#89](https://github.com/randyjreid/gramps-live-api/issues/89) records why: step 1 times the HTTP and
`GLib.idle_add` hop, and `/health` reads a cached name and a table count, so **no person is read and
the quantity F3's ~2 s budget was written about does not appear in those numbers at all.** This route
fetches one `Person` out of the open tree, which is the work F3 names.

⛔ **It returns no name, no date and no other tree text — two booleans and nothing else.** R3, the
injection widening, is still owed, so *that* is what keeps this route shippable ahead of it.

With a tree open:

```powershell
$id = "I0042"   # invented -- put a Gramps ID from your own tree here
Invoke-RestMethod "http://127.0.0.1:$port/person?gramps_id=$id" -Headers @{ Authorization = "Bearer $token" }
```

Three answers, **all of them 200**:

| The state | `person` | 
| --- | --- |
| the ID names somebody you may use | `@{ found = True; private = False }` |
| the ID names somebody **marked private in Gramps** | `@{ found = True; private = True }` |
| the ID names nobody | `@{ found = False }` |

⭐ **The third row carries no `private` key at all, and that is deliberate.** A `false` there would be
a claim about the privacy of somebody the tree does not hold — an answer about a person who is not
there. The key is absent instead, so the only two things the route ever says about a real person are
*found* and *private*.

⚠️ **The middle row is the one worth checking deliberately.** Mark a person private in Gramps, ask
again, and the answer must be *found and private* — **not** *no such person*. Ruling 1's second
enforcement point is that a target is refused **by name** rather than reported absent, because
silence would leave a caller unable to tell the two apart.

⛔ **The private state has only ever been exercised against fakes.** Nobody has flagged a `priv="1"`
person in the blessed copy, so the middle row's live behaviour is untested on real data — and
flagging one is **a write**, which is why it has not been done casually. The integration tests cover
it against a stand-in database; that is not the same observation.

### Taking F3's measurement

Same shape as the step-1 timing — 25 iterations, a tree open, against a **~2000 ms** budget:

```powershell
$headers = @{ Authorization = "Bearer $token" }
$url = "http://127.0.0.1:$port/person?gramps_id=$id"
$ms = 1..25 | ForEach-Object { (Measure-Command { Invoke-RestMethod $url -Headers $headers }).TotalMilliseconds }
$sorted = $ms | Sort-Object
[pscustomobject]@{
  median = $sorted[12]
  min    = $sorted[0]
  max    = $sorted[-1]
  first  = $ms[0]
}
```

⚠️ **Report the first call separately.** It was the outlier last time — 89.9 ms against a 2.2 ms
median — and averaging it in hides both facts.

⛔ **This number has now been taken, and F3 is discharged.** Against the blessed copy, warmed loop:
median **1.63 ms**, worst **3.22 ms** — **621× inside the ~2 s budget**, and *faster* than `/health`
on the same loop. R8's F3 section carries the table and the three conditions the discharge rests on.
Re-running the block above is how you check it against your own tree, not how the falsifier gets
answered again.

---

## What the token does and does not defend

**Does:** something that can reach the socket but not your filesystem — a page in your browser,
another machine that somehow routed to loopback.

⚠️ **Does not:** a process running as you. It can read `token` and it did not need to — it could
open the tree directly. R8 accepts that residual on exactly that ground, and nothing here should be
read as a claim otherwise.

The listener binds `127.0.0.1` and never the wildcard, so nothing outside this machine reaches it at
all.

---

## What CI covers, and what only this machine can

**CI covers**, on Python 3.10, 3.11 and 3.12, with a fake `dbstate` and a fake `GLib.idle_add`:

- the four steps above **and step 5's three states**, over a real loopback socket, with the request
  made from a thread that is not the main one while the main thread drains the queue —
  `tests/integration/test_host_over_loopback.py`. That file also asserts the person route **fetched
  the person** rather than answering from an index, which is the difference between timing a read and
  timing the hop around one — but it asserts it against a stand-in, so it says nothing about the cost;
- the thread boundary, including that **every** database helper refuses a non-main thread and that
  nothing outside the accessor reaches the database at all —
  `tests/unit/test_host_thread_boundary.py`;
- the token, the `Origin` rule and the constant-time comparison — `tests/unit/test_host_auth.py`;
- that every host source would have parsed on 3.10 — `tests/unit/test_host_language_floor.py`.

⛔ **CI proves none of the following, and a green run must not be read as though it did.** What has
happened since is that some of them were answered *here*, at this keyboard, which is the only place
they could be. **Three states, and they are not interchangeable:**

### 1. Measured on this machine, and discharged

- **F1** — that `GLib.idle_add` drains while a Gramps modal dialog holds a nested main loop. **It
  does.** The dialog held the main thread for **3.004 s**; the callback fired **0.0002 s** after it
  was scheduled, **with the dialog still up**; GLib main-loop depth went **1 → 2**, so it genuinely
  ran under the nested loop.
- **The transport** — steps 1, 3 and 4 above, against the live host with a tree open.
- **F3** — whether a **single-person read** exceeds ~2 s. ⚠️ **Step 1 does not answer it and was
  wrongly recorded as doing so**: it times the hop, and `/health` walks nobody. **Step 5 is the step
  that answered it** — median **1.63 ms**, worst **3.22 ms**, 621× inside the budget. R8 carries the
  table and the three conditions it rests on.

### 2. Still open

- **F2's visible outcome** — whether a `DbTxn` write from `idle_add` refreshes a Gramps view in
  place. The write lands and the `note-add` / `person-update` signals fire on the main thread; what is
  unmeasured is whether a view that cares *repaints*. ⚠️ **The earlier run had `DashboardView`
  active, which displays neither notes nor people**, so *"nothing refreshed"* proved nothing about a
  view that would have had a reason to react. **What settles it: the same measurement with a Person
  or Note view active** at the moment the transaction commits.

### 3. What CI structurally cannot reach — unchanged

- that the plugin loads at all inside the AIO's frozen **Python 3.14.4** interpreter;
- that Gramps' real `DbState` and `DummyDb` answer `is_open()` the way the stand-in does.

⚠️ **One in-situ observation exists and it is NOT a gate.** This repository's own tests, run once by
hand on **2026-08-19** inside the AIO's frozen **3.14.4** interpreter behind a minimal `pytest`
stand-in, reported **60 passed / 0 failed / 9 skipped** — **identical 60 / 0 / 9** on the project's
own 3.12. That is a
one-off run on one machine covering only what the stand-in could reach. **It must not be read as CI
covering 3.14, because it is not**: the gates still run 3.10, 3.11 and 3.12, and the source still has
to be 3.10-compatible while executing on 3.14.

**Step 1 producing a real tree's name is the demo. Nothing else is.** Step 5 is not a demo — it is the
measurement, and it has now been taken.
