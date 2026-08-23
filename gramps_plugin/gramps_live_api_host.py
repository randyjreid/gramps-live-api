"""The hook Gramps fires at startup, and the smallest thing it could be.

⚠️ **Nothing here is imported at module level from ``gramps`` or ``gi``, and that
is deliberate rather than tidy.** Every Gramps-shaped line lives inside
``load_on_reg``, so this module imports on an ordinary machine and
``tests/unit/test_host_plugin.py`` exercises ``start_host`` -- the whole plugin
half except the three lines that reach ``gi`` and Gramps' signal. What CI cannot
cover is then three lines instead of a file.

⚠️ **``load_on_reg`` swallows exceptions and the all-in-one build has no
console.** R8's accepted risk 2. So this never raises: the ordinary failure goes
to ``host.log`` through ``service.start_and_report``, and the failure that
happens BEFORE the package is importable -- a wrong junction, a moved checkout --
goes through ``_last_resort_note``, which is the only reason this file computes a
path of its own.

⚠️ **The hook fires with NO TREE OPEN.** ``uistate`` is ``None`` and
``dbstate.db`` is a ``DummyDb``; the probe measured both. So the host starts in
that state and learns about a tree from ``database-changed``.

⚠️ **This source must parse on Python 3.10 and will execute on Python 3.14.** The
AIO ships 3.14.4 and this repository's gates run 3.10-3.12, so neither end is
observable from the other. The stdlib used here is deliberately ancient -- ``os``,
``sys``, ``traceback`` -- because ``mypy src`` does not reach this directory and
nothing else would catch a call that arrived after the floor.
"""

import os
import sys
import traceback
import uuid

DIRECTORY_NAME = "gramps-live-api"
LOG_FILE = "host.log"
"""⚠️ Duplicated from ``gramps_live_api.host.paths`` ON PURPOSE, and pinned by
test. The one failure this file exists to make visible is the one where that
module cannot be imported, so the last-resort writer cannot ask it where to
write. ``tests/unit/test_host_plugin.py`` asserts the two answers agree, which is
what stops the copy drifting into a second directory nobody looks in."""

NAME_FILE = "name.txt"
"""What Gramps calls a tree, read as a FILE rather than through the database.

⛔ This module may not touch ``dbstate.db`` -- it is host code by the rule in
``tests/fixtures/host_sources.py`` -- so the backup directory is named from the
tree's own ``name.txt``, which is an ordinary file read.

⚠️ **This constant was missing at first and the failure was invisible.**
``_tree_name`` referenced it, raised ``NameError``, and the broad ``except``
below returned the fallback -- so every backup would have landed in a directory
called ``tree``. A test asserting the POSITIVE case caught it; one asserting only
the fallback would have passed."""

_IN_FLIGHT = {"present": False}
"""Whether an approval is already on screen. ⛔ One at a time.

⚠️ **This is a bound on a class, not a fix for an instance.** Four review rounds
found four different consequences of two approvals interleaving; see ``_present``
for the list. A GTK modal spins a nested main loop, so *"it runs on the main
thread"* has never meant *"nothing else runs"*."""

_RUNNING = {}
"""The started host, kept so a later slice has something to stop. Gramps' exit
takes the daemon thread with it, so nothing here needs to."""


def load_on_reg(dbstate, uistate=None, plugin=None, *rest):
    """Gramps' startup hook. Runs on the main thread, before any tree is open.

    Never raises. There is nowhere for an exception to go: the caller prints a
    traceback into a console the all-in-one build does not have, and startup
    carries on as though the plugin were fine.

    ⚠️ **The trailing parameters are defaulted and open-ended deliberately.** A
    signature mismatch raises in GRAMPS' code, before this body -- so the
    ``try`` below cannot catch it, ``host.log`` never gets a line, and the whole
    slice fails in the one way nothing here can report. Nothing on this machine
    can check what Gramps actually passes, so the call is made impossible to get
    wrong instead of being got right by guessing. ``uistate`` is ``None`` at this
    point anyway, which the probe measured.
    """
    try:
        _put_the_package_on_the_path()

        # gi is imported HERE rather than at module level so this file stays
        # importable, and therefore testable, on a machine with no GTK.
        from gi.repository import GLib

        started = start_host(dbstate, GLib.idle_add, uistate)
        if started is not None:
            from gramps_live_api.host import service

            # ⚠️ ``*ignored`` for the reason load_on_reg's signature is open:
            # Gramps' Callback.emit unpacks whatever the emitter passed, and a
            # handler that disagreed about the count would raise inside the
            # signal rather than anywhere this can report. The argument is not
            # wanted in any case -- the accessor reads dbstate live.
            dbstate.connect(
                "database-changed",
                lambda *ignored: service.database_changed(started),
            )
    except Exception:
        traceback.print_exc()
        _last_resort_note(traceback.format_exc())


def start_host(dbstate, schedule, uistate=None):
    """Hand Gramps' possessions to the package and start listening.

    ``dbstate`` goes straight into the accessor -- the one module allowed to
    spell the database -- and ``schedule`` is ``GLib.idle_add``, which is how
    anything gets back onto this thread. Returns the running host, or ``None``
    if it did not start, in which case ``host.log`` says why.

    ⭐ **``present`` is the third possession and the newest.** The package can
    validate a graph and render it as prose, but it cannot show a window: the
    Gtk classes live here. So the host is handed a callable that takes a graph,
    puts it in front of the owner, and writes it if he says yes.
    """
    from gramps_live_api.host import accessor, service

    accessor.bind(dbstate)
    host = service.start_and_report(
        schedule=schedule,
        environ=os.environ,
        present=lambda graph: _present(dbstate, uistate, graph),
    )
    _RUNNING["host"] = host
    return host


def _present(dbstate, uistate, graph):
    """Show what would be written, and write it if the owner says so.

    ⚠️ **Runs on the GTK main thread, inside a ``GLib.idle_add`` callback**, and
    ``confirm`` spins a nested main loop there. ``spike/dialogprobe.py`` measured
    that working before anything was built on it: dialog shown from inside the
    callback, answer returned after 3.9 s, ``DbTxn`` committed and read back.

    ⭐ **The preview is rendered from the graph that arrived**, which the MCP
    server loaded from its own stored record -- never from anything an agent
    passed at approval time. That is what carries the approval binding across
    from the console to this dialog.

    Never raises. It is reached from a hook whose exceptions go nowhere, so
    everything lands in ``host.log`` instead.
    """
    from gramps_live_api.host import document

    host = _RUNNING.get("host")

    def note(level, message):
        if host is not None:
            host.note(level, message)

    # ⛔ ONE APPROVAL IN FLIGHT AT A TIME. A second is REFUSED, not queued.
    #
    # ⚠️ **There is no "synchronous" in a GTK application with modal dialogs.**
    # ``writer.confirm`` spins a NESTED main loop, so other ``GLib.idle_add``
    # callbacks -- including another ``_present`` -- run inside it. Moving the
    # backup off its worker shortened the window and **serialised nothing.**
    #
    # ⭐ Four rounds of review found four different consequences of that one
    # missing requirement: two documents snapshotting the same database so the
    # second's backup restored away the first's write · a cancelled preview
    # evicting the pre-write backup · re-entry through the dialog's nested loop ·
    # an interleaved completion truncating the intent journal. **They are not
    # four defects. They are one, seen four times**, which is why this is a bound
    # rather than a fourth patch.
    #
    # ⛔ Refused rather than queued, and no dialog: a second modal stacked on the
    # one the owner is reading is worse than the refusal it announces. The route
    # answers 202 before any of this and reports no outcome anyway, so the log is
    # where a refusal belongs.
    if _IN_FLIGHT["present"]:
        note(
            "ERROR",
            "document: REFUSED -- another document is already awaiting approval. "
            "Finish or cancel that dialog before proposing again. Nothing was "
            "written for this one.",
        )
        return False

    _IN_FLIGHT["present"] = True
    try:
        import gramps_live_api_writer as writer

        parsed = document.parse(graph)

        # ⭐ The names in the dialog are read from the TREE, not from the graph.
        # If the model picked the wrong Gramps ID the owner sees the wrong
        # person and cancels, and that is the only check there is. Resolving
        # here rather than trusting what the route resolved keeps the lookup
        # adjacent to the rendering it feeds.
        from gramps_live_api.host import accessor

        resolution = accessor.resolve_nodes(graph)
        # ⛔ ``refusal()`` and not ``missing``. This re-resolve happens AFTER the
        # route's, so a target can have become private in between -- and checking
        # ``missing`` alone reported it as absent, losing ruling 1's second
        # enforcement point to a call-site convention. The order lives in the
        # method now, so this site cannot get it wrong.
        refusal = resolution.refusal()
        if refusal is not None:
            note("ERROR", "document: refusing: " + refusal)
            writer.tell(uistate, "Nothing was written", refusal)
            return

        note("INFO", "document: showing " + document.summary(parsed))

        # ⛔ The blessing is checked BEFORE the backup. A tree that may not be
        # written does not get copied.
        #
        # ⚠️ Through the ACCESSOR, not through ``dbstate.db``. This file is host
        # code by the rule in ``tests/fixtures/host_sources.py`` -- it imports the
        # host package -- so reaching the database here is exactly the trespass
        # the boundary test refuses, and it caught this on the first run.
        from gramps_live_api.host import accessor

        outcome = accessor.blessing()
        if not outcome.blessed:
            note("ERROR", "document: refused before backup: " + outcome.message)
            writer.tell(uistate, "Nothing was written", outcome.message)
            return

        # ⭐ Counted IMMEDIATELY before the copy, on this thread, with nothing
        # able to run in between.
        #
        # ⚠️ These numbers are what the restore procedure tells the owner to check
        # against after replacing the file, so they have to describe **the
        # snapshot**, not some earlier moment. While the backup ran on a worker
        # they described a database version that could already have moved on --
        # a check whose numbers come from a different instant than the thing it
        # names, which is this project's most common defect class.
        totals = accessor.tree_totals()

        # ⛔ THE BACKUP RUNS HERE, ON THIS THREAD, BEFORE THE DIALOG.
        #
        # ⚠️ **It used to run on a worker with the result marshalled back**, to
        # respect R8's cap on work inside one ``GLib.idle_add`` callback. That
        # design produced three correctness defects the synchronous one cannot
        # have -- two documents snapshotting the same pre-A database so the
        # second's backup restored away the first's write · a dialog rendering a
        # resolution taken before the copy while the writer resolved live · totals
        # counted at a moment unrelated to the snapshot they name. **Every one of
        # them needed an interval, and there is no longer an interval.**
        #
        # ⭐ **The measured cost it avoided was 108 ms** on the owner's real tree
        # (24 MB, 5,894 pages, one page each, zero restarts) -- against the
        # **343-402 ms** of main-thread cost this project already accepts for a
        # name search, once, immediately before a dialog he is about to read.
        # **The trade was wrong and is reversed.**
        taken = _take_backup(outcome.message, note)
        if not taken.ok:
            # ⛔ Refuse-to-arm, in the ruling's own words: it does not fall back
            # to an export, it does not write without a backup, and it does not
            # continue quietly. ⭐ And NO DIALOG -- one that opened and then said
            # "the backup failed" would already have spent his attention on a
            # decision that could not be honoured.
            note("ERROR", "document: REFUSED TO ARM -- " + taken.message)
            # ⛔ Discard here too. A refusal is a pre-write exit like any other,
            # and a partially-successful backup -- copied, but with a directory
            # entry that could not be flushed -- has a path on disk that would
            # otherwise survive to consume a retention slot, evicting a real one.
            _discard_quietly(taken, note)
            writer.tell(
                uistate,
                "Nothing was written -- no backup",
                taken.message + "\n\nThe write path refuses to arm without a backup. "
                "Nothing in your tree was touched.",
            )
            return

        # ⛔ **Nothing between a live backup and the function that owns its
        # lifecycle.** The "backup ok" line is logged inside ``_write_after_backup``,
        # within the try whose ``finally`` discards -- not here.
        #
        # ⚠️ Any statement in this interval is outside every discard path: it
        # would leak an ok backup with no discard, consuming a retention slot per
        # occurrence, which is the exact eviction the bound was built to end.
        # Today nothing here can realistically raise, and *today* is not a
        # property -- a later edit inherits the gap silently.
        return _write_after_backup(
            dbstate,
            uistate,
            graph,
            parsed,
            resolution,
            taken,
            totals,
            note,
            backed_up_tree=outcome.message,
        )

    except Exception:
        note("ERROR", "document: the write failed: " + traceback.format_exc())
        try:
            import gramps_live_api_writer as writer

            writer.tell(uistate, "The document could not be written", traceback.format_exc()[:2000])
        except Exception:
            pass
    finally:
        # ⛔ In a ``finally``, so every exit clears it -- refusals, cancellation,
        # a raise inside the nested loop. A flag left set would refuse every
        # later proposal for the lifetime of the process, which is a worse
        # failure than the one it prevents.
        _IN_FLIGHT["present"] = False


def _take_backup(tree_dir, note):
    """Copy the tree, on THIS thread, and return the outcome.

    ⛔ **No worker, no continuation, no marshalling back.** The asynchronous
    version existed to keep one ``GLib.idle_add`` callback short; it bought 108 ms
    and cost three correctness defects that all needed the interval it created.

    Never raises -- a refusal is a result, because the caller has to tell the
    owner either way.
    """
    import datetime

    from gramps_live_api.host import backup, paths

    try:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory = os.path.join(paths.state_directory(os.environ), "backups")
        destination = backup.destination_for(
            directory, _tree_name(tree_dir), stamp, tree_dir=tree_dir
        )
        note("INFO", "document: taking a backup before writing")
        outcome = backup.take(os.path.join(tree_dir, "sqlite.db"), destination)

        # ⛔ The directory verdict is READ, and read HERE -- once, where both
        # callers already go -- rather than checked at each call site.
        #
        # ⚠️ An earlier version added ``directory_synced`` and then never looked
        # at it: a fact measured, reported, and ignored, which is worth exactly
        # as much as never measuring it. Checking it at the two call sites would
        # have been the enumeration this project keeps paying for; folding it
        # into ``ok`` means the refuse-to-arm path that already exists handles
        # it, and a third call site cannot forget.
        #
        # ⭐ **FAILED refuses. UNSUPPORTED proceeds and is recorded.** Windows
        # cannot fsync a directory at all, so refusing on ``unsupported`` would
        # refuse every write on the owner's only platform -- that is not a
        # durability guarantee, it is an outage. A genuine ``OSError`` from a
        # platform that CAN do it is a real failure and refuses.
        if outcome.ok and outcome.directory_synced == paths.FAILED:
            return backup.Outcome(
                ok=False,
                path=outcome.path,
                message=(
                    "the backup was copied but its directory entry could not be "
                    "flushed, so a power loss could lose the backup while keeping "
                    "the change"
                ),
                pages=outcome.pages,
                attempts=outcome.attempts,
                seconds=outcome.seconds,
                directory_synced=outcome.directory_synced,
                taken_utc=outcome.taken_utc,
            )
        return outcome
    except Exception:
        return backup.Outcome(
            ok=False, path=None, message="the backup raised: " + traceback.format_exc()
        )


def _tree_name(tree_dir):
    """The tree's own name, read from ``name.txt``. ⛔ A file read, never the database."""
    try:
        with open(os.path.join(tree_dir, NAME_FILE), encoding="utf-8") as handle:
            return handle.read().strip() or "tree"
    except Exception:
        return "tree"


def _record_intent(document, outcome, parsed, approved, taken, totals, note):
    """Write the backup mapping BEFORE the transaction. ``None`` means refuse.

    ⛔ **This is A4's durability**, and it is why it runs first: *the backup's age
    relative to the write is visible without archaeology* is only true if the
    link survives the write failing to be recorded.
    """
    import datetime

    from gramps_live_api.host import paths

    try:
        stamped = datetime.datetime.now(datetime.timezone.utc)
        record = document.journal_record(
            parsed,
            {},
            {},
            tree_dir=outcome.message,
            written_utc="",
            approved_preview=approved,
            backup_path=taken.path or "",
            backup_utc=taken.taken_utc,
            totals_before=totals,
        )
        record["write_confirmed"] = False
        path, verdict = document.write_journal(
            outcome.message,
            record,
            # ⛔ A collision-free suffix, the SAME bound the backup's filename
            # already uses. Two runs in one UTC second produced one stem, so a
            # completion could name an existing intent file -- and
            # ``write_journal`` opens with "w". **The already-fsynced backup
            # mapping was truncated after the database had committed.** Second
            # location, same defect: bound rather than patched.
            stem=stamped.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8] + "-document",
        )
        # ⛔ The journal's OWN directory verdict, read for the same reason. An
        # earlier version called ``sync_directory`` and discarded the answer.
        if verdict == paths.FAILED:
            note("ERROR", "document: the journal's directory entry could not be flushed")
            return None
        note("INFO", "document: backup recorded before writing: " + path)
        return path
    except Exception:
        note("ERROR", "document: could not record the backup: " + traceback.format_exc())
        return None


def _same_blessed_tree(backed_up_tree, note, writer, uistate):
    """The blessing, re-checked and required to name the tree that was backed up.

    Returns the blessing, or ``None`` after telling the owner why not.

    ⛔ **A backup of a different tree is not a backup.** R4's guarantee is
    *recoverable-after*, and it is only true if the copy on disk is of the tree
    that is about to change.
    """
    from gramps_live_api.host import accessor

    outcome = accessor.blessing()
    if not outcome.blessed:
        note("ERROR", "document: refused at write time: " + outcome.message)
        writer.tell(uistate, "Nothing was written", outcome.message)
        return None
    if backed_up_tree and outcome.message != backed_up_tree:
        message = (
            "the open tree changed after the backup was taken. The backup is of "
            + str(backed_up_tree)
            + " and the tree now open is "
            + str(outcome.message)
            + ". Nothing was written."
        )
        note("ERROR", "document: refused -- " + message)
        writer.tell(uistate, "Nothing was written -- the tree changed", message)
        return None
    return outcome


def _discard_quietly(taken, note):
    """Remove a backup that protects nothing. ⛔ Never fatal.

    ⚠️ This deletes **this run's own output**, on a path it just built, for a
    write that did not happen. It is never a tree file and never something the
    owner made.
    """
    from gramps_live_api.host import backup

    try:
        if taken.path:
            backup.discard(taken.path)
            note("INFO", "document: discarded a backup that preceded no write")
    except Exception:
        note("ERROR", "document: could not discard the backup: " + traceback.format_exc())


def _prune_quietly(taken, note):
    """Drop old backups. Never fatal -- the write's outcome does not depend on it."""
    from gramps_live_api.host import backup

    try:
        if taken.path:
            backup.prune(os.path.dirname(taken.path))
    except Exception:
        note("ERROR", "document: pruning old backups failed: " + traceback.format_exc())


def _write_after_backup(
    dbstate, uistate, graph, parsed, resolution, taken, totals, note, backed_up_tree=None
):
    """Back on the MAIN THREAD, with the backup's verdict. Show, then write.

    ⛔ **Refuse-to-arm, in the ruling's own words:** *if the backup cannot be
    taken, the host refuses to arm its write path and says so. It does not fall
    back to an export, it does not write without a backup, and it does not
    continue quietly.*

    ⛔ **No dialog is shown before the backup succeeds.** A dialog that opens and
    then reports "the backup failed, nothing was written" has already spent the
    owner's attention on a decision that could not be honoured.
    """
    # ⛔ **The backup is provisional until the write is ATTEMPTED**, and this flag
    # is the whole of what says so.
    #
    # ⛔⛔ **It says "attempted", not "committed", and the difference is the whole
    # finding.** A previous version set it AFTER ``writer.write`` returned, which
    # reads as "the transaction committed" and is not the same claim. In the
    # shipped Gramps 6.0.8, ``dbapi.transaction_commit`` runs ``self.dbapi.commit()``
    # -- the SQLite COMMIT -- and only THEN emits signals, commits the undo
    # database, and calls ``_after_commit``, which invokes ``undo_callback``,
    # ``redo_callback`` and ``undo_history_callback`` **unguarded** (the real UI
    # sets these to update the Edit menu). An exception in any of them leaves
    # ``write()`` with **the tree durably changed** -- and the old flag still
    # False, so the ``finally`` deleted the only recovery point of a write that
    # had already landed. **R4's guarantee destroyed by the machinery built to
    # maintain it**, and the test asserting it encoded the false premise.
    #
    # ⭐ So the question is not *did it commit* -- which cannot be known from out
    # here -- but *do we know for certain that nothing was attempted*. Keep on
    # unknown. The worst case is one retention slot spent on a backup for a write
    # that failed early; the other way round costs the guarantee.
    #
    # ⚠️ Discarding it used to be one enumerated branch -- the owner pressing
    # Cancel. Every OTHER pre-write exit leaked it: the tree closed or swapped
    # inside ``confirm``'s nested loop, the intent record refusing to write, and
    # any exception at all. Each leaked copy is a snapshot of a tree nobody
    # changed, and because ``RETAIN`` counts FILES, each one pushes a real
    # journal-linked pre-write backup out of the window. **Enough abandoned
    # previews silently evict every recovery point that could undo a real write.**
    #
    # ⭐ The second instance of an enumerated rule standing in for a bound, in
    # this same file, this same week. Bounded rather than patched: *committed or
    # discarded*, decided in one place, with no branch able to forget.
    write_attempted = False

    try:
        # ⛔ Inside the try, so even an import failure reaches the ``finally``.
        import gramps_live_api_writer as writer

        from gramps_live_api.host import document, paths

        if not taken.ok:
            note("ERROR", "document: REFUSED TO ARM -- " + taken.message)
            # ⛔ No discard call here -- ``write_attempted`` is False, so the
            # ``finally`` at the end of this function covers this branch
            # along with every other pre-write exit.
            writer.tell(
                uistate,
                "Nothing was written -- no backup",
                taken.message + "\n\nThe write path refuses to arm without a backup. "
                "Nothing in your tree was touched.",
            )
            return False

        # ⛔ Logged HERE and only here. ⚠️ It used to be logged by ``_present``
        # as well, so every approved write produced TWO identical lines and any
        # count of them in ``host.log`` read double -- a reader trusting a
        # miscounting diagnostic is this project's most expensive habit.
        note(
            "INFO",
            f"document: backup ok in {taken.seconds:.3f} s "
            f"({taken.pages} pages, attempt {taken.attempts}, "
            f"directory {taken.directory_synced}): {taken.path}",
        )

        # ⛔ The blessing AGAIN -- and it must be the SAME TREE, not merely a
        # blessed one.
        #
        # ⚠️ **Checking only "is this blessed" reopened the hole the backup
        # exists to close.** Switch from blessed tree A to blessed tree B while
        # the worker is copying and the check passes, the write lands in B, and
        # the backup on disk is of A. **Recoverable-after is then false while
        # every individual check reads as green** -- the guarantee gone, and
        # nothing saying so.
        # ⚠️ **Redundant now, and kept deliberately.** With the backup synchronous
        # nothing can run between the blessing check in ``_present`` and this
        # line -- ``backup.take`` is plain Python and SQLite, and enters no GTK
        # loop. **It is retained because the check below it is NOT redundant**,
        # and a reader deleting this one as dead weight would be one step from
        # deleting that one too. Three lines is a cheap way to keep the pair
        # legible.
        outcome = _same_blessed_tree(backed_up_tree, note, writer, uistate)
        if outcome is None:
            return False

        if not writer.confirm(uistate, document.preview(parsed, resolution)):
            note("INFO", "document: the owner said no. Nothing was written.")
            # ⛔ DISCARD it, do not merely prune around it.
            #
            # ⚠️ **A cancelled preview's backup protects nothing** -- no write
            # happened, so it is a snapshot of a tree nobody changed. Keeping it
            # was actively harmful, not merely wasteful: ``RETAIN`` declined
            # previews create newer files that push the **journal-linked
            # pre-write backup** out of the window, leaving twenty copies and
            # none that can undo the write they were supposed to protect.
            #
            # ⭐ Counting only backups that precede a real write is what makes
            # retention a bound on RECOVERY POINTS rather than on files.
            #
            # ⛔ No ``_discard_quietly`` call here any more -- ``write_attempted``
            # is still False, so the ``finally`` below does it for this branch and
            # for every other pre-write exit alike.
            return False

        # ⛔ And AGAIN after the dialog -- **this is the one that earns its
        # keep.** ``confirm`` spins a NESTED GTK main loop, so arbitrary real
        # time passes inside that call and other idle callbacks run: the tree can
        # be closed or swapped while the owner is reading. Making the backup
        # synchronous removed the interval before the dialog; it did nothing
        # about the interval inside it.
        outcome = _same_blessed_tree(backed_up_tree, note, writer, uistate)
        if outcome is None:
            return False

        approved = document.preview(parsed, resolution)

        # ⛔ THE BACKUP MAPPING IS WRITTEN BEFORE THE TRANSACTION, and a failure
        # to write it REFUSES the write.
        #
        # ⚠️ The journal used to be written afterwards with its failure caught,
        # so a disk, permission or serialisation error left **a committed write
        # with no durable record of which backup precedes it** -- which is A4
        # defeated entirely, and recoverable-after reduced to filesystem
        # archaeology at the moment it is needed.
        #
        # ⭐ The intent record costs nothing if the write then fails: it names a
        # backup and an approved preview, and says the write was not confirmed.
        # A record of a write that did not happen is recoverable by reading it;
        # a write with no record is not.
        intent = _record_intent(document, outcome, parsed, approved, taken, totals, note)
        if intent is None:
            writer.tell(
                uistate,
                "Nothing was written",
                "the backup could not be recorded, so the write was refused. "
                "Without that record there would be no durable link between "
                "your tree and the backup that precedes it.",
            )
            return False

        # ⛔ **BEFORE the call, not after it.** Once control enters ``write`` the
        # tree may change, and from out here there is no way to learn whether it
        # did. Everything above this line is a genuine pre-write exit; nothing
        # below it is.
        write_attempted = True
        result = writer.write(dbstate, graph)
        # ⛔ Summarised HERE, from what the write actually created. The writer
        # cannot do it: importing the host package would make it host code and
        # forbid it the database access it exists for.
        summary = document.summarise_created(result["created"])
        note("INFO", "document: wrote " + summary)

        # ⛔ Journal it. Gramps' own undo is a process-local list discarded on
        # close, so without this a six-object write is unrecoverable the moment
        # Gramps quits -- which has already cost one manual cleanup.
        # ⚠️ AFTER the commit, deliberately: a record of a write that did not
        # happen is worse than no record, and the transaction has returned by here.
        # ⭐ The same file, completed with what the write actually did. The
        # mapping was already durable before the transaction; this adds the ids.
        journal = intent
        try:
            import datetime

            written_utc = datetime.datetime.now(datetime.timezone.utc)
            journal, completion_verdict = document.write_journal(
                outcome.message,
                document.journal_record(
                    parsed,
                    result["created"],
                    result["attached"],
                    tree_dir=outcome.message,
                    written_utc=written_utc.isoformat(),
                    approved_preview=approved,
                    backup_path=taken.path or "",
                    backup_utc=taken.taken_utc,
                    totals_before=totals,
                ),
                # ⛔ The intent's OWN stem, reused. Recomputing one independently
                # is what let a same-second completion truncate a different
                # record -- the completion must finish the file it started.
                stem=os.path.basename(intent)[: -len(".json")],
            )
            # ⛔ Read, not discarded -- the round-3 finding one line-fix away at
            # a second call site. ⚠️ It does NOT refuse: the write has already
            # committed, so refusing is not available and what is at risk is the
            # ids list, not the backup mapping, which was made durable before the
            # transaction. It is recorded so the log says which happened.
            note("INFO", f"document: journalled ({completion_verdict}) to {journal}")
            if completion_verdict == paths.FAILED:
                note(
                    "ERROR",
                    "document: the completed record's directory entry was not "
                    "flushed. The backup mapping written before the write is "
                    "unaffected; the list of created ids may not survive a power "
                    "loss.",
                )
        except Exception:
            # ⚠️ A failed completion must not un-write the tree, and must not be
            # silent. ⭐ Unlike before, the backup mapping is ALREADY on disk --
            # what is lost here is the list of ids, not the recovery path.
            note("ERROR", "document: the journal was not completed: " + traceback.format_exc())

        writer.tell(
            uistate,
            "Written",
            summary
            + "\n\nUndo record: "
            + journal
            + "\n\nBackup taken first: "
            + (taken.path or "(none)")
            + "\n\nEdit > Undo in Gramps also works, until Gramps closes.",
        )

        # ⛔ Pruned only AFTER a success, so a failed backup can never destroy the
        # last good copy.
        _prune_quietly(taken, note)

        # ⛔ FALSE, always. This value becomes ``_present``'s, and ``_present`` is
        # reached from a ``GLib.idle_add`` callback where a TRUTHY return
        # reschedules -- which would run the whole write again.
        return False
    except Exception:
        note("ERROR", "document: the write failed: " + traceback.format_exc())
        try:
            import gramps_live_api_writer as writer

            writer.tell(uistate, "The document could not be written", traceback.format_exc()[:2000])
        except Exception:
            pass
        return False
    finally:
        # ⛔ Every path out of this function passes here. A backup that did not
        # end up protecting a write is removed; one that did is never touched.
        if not write_attempted:
            _discard_quietly(taken, note)


def _put_the_package_on_the_path():
    """Make ``gramps_live_api`` importable inside Gramps' own frozen interpreter.

    Gramps runs on its own Python with its own ``sys.path``, and nothing this
    project installs is on it. Two answers, in order:

    ``GRAMPS_LIVE_API_SRC``
        an explicit directory, for an owner who put the checkout somewhere this
        cannot infer.
    the checkout beside this file
        the plugin directory is a hand-made junction into the checkout, so
        resolving symbolic links and stepping up one level lands on the checkout
        root. ``realpath`` is what follows the junction; ``dirname(__file__)``
        alone would land in Gramps' plugin folder, where there is no ``src``.

    ⚠️ **And this directory itself, which is the third answer and was learned
    the hard way.** Gramps ``exec``s a plugin rather than importing it, so the
    plugin folder is NOT on ``sys.path`` and a sibling module -- the writer --
    cannot be imported by name. Observed as ``ModuleNotFoundError: No module
    named 'gramps_live_api_writer'`` on the first real request, with the route
    already answered 202 and the failure visible only in ``host.log``.
    """
    named = os.environ.get("GRAMPS_LIVE_API_SRC")
    here = os.path.dirname(os.path.realpath(__file__))
    for candidate in (named, os.path.join(os.path.dirname(here), "src"), here):
        if candidate and os.path.isdir(candidate) and candidate not in sys.path:
            sys.path.insert(0, candidate)


def last_resort_log_path(environ, platform):
    """Where to write when ``gramps_live_api`` itself could not be imported.

    Public, and only so a test can pin it against the real one. See the note on
    ``DIRECTORY_NAME`` above for why the copy exists at all.
    """
    if platform == "win32":
        base = environ.get("APPDATA", "")
    else:
        base = environ.get("XDG_CONFIG_HOME") or os.path.join(environ.get("HOME", ""), ".config")
    return os.path.join(base, DIRECTORY_NAME, LOG_FILE)


def _inside_gramps():
    """Whether this module is really executing inside a Gramps process.

    ⛔ **``host.log`` is the ONLY place a genuinely failed start is visible.**
    ``load_on_reg`` swallows exceptions and the all-in-one build has no console
    -- R8's accepted risk 2 -- so a line in that file has to mean something
    happened to the real host.

    ⚠️ **It stopped meaning that.** The unit suite calls ``load_on_reg(None)`` to
    assert the hook never raises, which is exactly right; the hook then fails at
    ``from gi.repository import GLib`` and reported it to the PRODUCTION log.
    Sixty-eight such tracebacks accumulated against twenty-five real lines --
    **and a reader came one message from reporting the host down because of
    them.** A log that cries wolf is the same defect as a guard that fires on
    every route literal: it trains the reader to skip the one that matters.

    ``gramps`` is in ``sys.modules`` whenever Gramps' own code is running, and
    is not importable at all in this project's environment, so the check costs
    nothing and cannot be satisfied by accident. A failure that IS inside Gramps
    still reports, because Gramps got far enough to exec this file.
    """
    return "gramps" in sys.modules


def _last_resort_note(detail):
    """One ERROR line, written with nothing but built-ins. Silent if even that fails.

    ⛔ Refuses outside Gramps -- see ``_inside_gramps``. The traceback still
    reaches stderr through ``load_on_reg``, which is where a test or a probe
    should be reading it from anyway.
    """
    if not _inside_gramps():
        return
    try:
        path = last_resort_log_path(os.environ, sys.platform)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("ERROR the host plugin could not start: " + detail.strip() + "\n")
    except Exception:
        # There is genuinely nowhere left to report this, and raising would put
        # the exception back into the hook that eats it.
        pass
