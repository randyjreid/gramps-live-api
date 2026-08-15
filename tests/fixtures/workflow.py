"""Read the CI workflow, so tests can drive what CI runs instead of restating it.

Hand-parsed by indentation rather than with a YAML library, for the reason
``test_repository_hygiene`` gives at every one of its own parsers: the guard job
deliberately installs nothing, and this repository has no runtime dependency to
add one to.

⚠️ **This module is the single reader.** Its step-level helpers were moved here
from ``tests/integration/test_repository_hygiene.py`` so that the tests which
*execute* the workflow's steps and the tests which *read* their shape share one
idea of what a step is. Two parsers would be two ideas, which is the defect this
module has recorded against duplicated matchers repeatedly.

``shell_bodies`` stays in that file on purpose: it answers a different question
-- every line of every ``run:`` block, with line numbers, across both jobs and
including unnamed steps -- and it exists to scan for interpolation rather than to
execute anything.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
"""Defined here because this is where the workflow file is resolved from."""

WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"

GUARD_MODULE = "gramps_live_api.core.pii_guard"

# The workflow's steps are indented by six spaces, so this is where one begins.
STEP_SEPARATOR = "      - name: "


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def step_blocks() -> list[str]:
    """Every step of the workflow, as text. The first chunk is the file header."""
    return workflow_text().split(STEP_SEPARATOR)[1:]


def step_name(block: str) -> str:
    return block.splitlines()[0].strip()


def named_step(name: str) -> str:
    """The one step called ``name``.

    Exactly one, asserted rather than assumed: a renamed step must break the
    tests that drive it loudly, rather than leaving them driving nothing.
    """
    matching = [block for block in step_blocks() if step_name(block) == name]
    if len(matching) != 1:
        raise LookupError(
            f"expected exactly one step named {name!r}, found "
            f"{[step_name(block) for block in step_blocks()]}"
        )
    return matching[0]


def guard_invocation(block: str) -> str:
    """The block's ``run:`` line if it runs the guard, otherwise the empty string."""
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("run:") and GUARD_MODULE in stripped:
            return stripped
    return ""


def scan_steps() -> list[str]:
    return [block for block in step_blocks() if guard_invocation(block)]


def _active_lines(block: str) -> list[str]:
    """The block's lines with comments dropped.

    This workflow explains itself at length and its commentary quotes its own
    keys, so a parser that reads commented lines reads prose as settings -- the
    fail-open ``test_a_comment_cannot_stand_in_for_an_active_fetch_depth``
    records, facing this way.
    """
    return [line for line in block.splitlines() if not line.strip().startswith("#")]


def _nested(lines: list[str], index: int) -> list[str]:
    """The lines belonging to the block opened at ``index``: those indented further."""
    indent = len(lines[index]) - len(lines[index].lstrip())
    nested = []
    for line in lines[index + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        nested.append(line)
    return nested


def _dedented(lines: list[str]) -> str:
    widths = [len(line) - len(line.lstrip()) for line in lines if line.strip()]
    margin = min(widths) if widths else 0
    return "\n".join(line[margin:] if line.strip() else "" for line in lines)


def step_condition(block: str) -> str:
    """The step's ``if:`` expression, or the empty string when it is unconditional.

    Both spellings this workflow uses: the inline one, and the folded ``>-``
    block whose continuation lines join with spaces.
    """
    lines = _active_lines(block)
    for index, line in enumerate(lines):
        if not line.strip().startswith("if:"):
            continue
        tail = line.strip()[len("if:") :].strip()
        if tail in (">", ">-", "|", "|-"):
            return " ".join(nested.strip() for nested in _nested(lines, index) if nested.strip())
        return tail
    return ""


def step_environment(block: str) -> dict[str, str]:
    """The step's ``env:`` mapping: variable name to the text it is given."""
    lines = _active_lines(block)
    for index, line in enumerate(lines):
        if line.strip() != "env:":
            continue
        environment = {}
        for nested in _nested(lines, index):
            key, separator, value = nested.strip().partition(":")
            if separator:
                environment[key.strip()] = value.strip()
        return environment
    return {}


def step_shell_body(block: str) -> str:
    """The step's ``run:`` script, dedented and ready to be handed to a shell.

    ⚠️ **Read from the RAW lines, comments and all.** The other readers here drop
    comments, because a commented-out setting must not be able to satisfy a
    check. This one must not: what is handed to the shell has to be what CI
    hands it, and a reader that silently deletes lines from a script is a
    transcription of the step wearing the extraction's clothes. The ``run:``
    line itself is still located among the active lines, so a commented one
    cannot introduce a body.
    """
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if line.strip().startswith("#") or not line.strip().startswith("run:"):
            continue
        tail = line.strip()[len("run:") :].strip()
        if tail in ("|", "|-", ">", ">-"):
            return _dedented(_nested(lines, index)) + "\n"
        return tail + "\n"
    raise LookupError(f"the step {step_name(block)!r} has no run: block to execute")


# ---------------------------------------------------------------------------
# Which step an event reaches.
# ---------------------------------------------------------------------------


class UnreadableCondition(Exception):
    """The condition uses something this evaluator does not implement.

    Raised rather than guessed. An evaluator that answered *true* to a construct
    it does not understand would make every routing assertion vacuously green --
    the same shape as a check written as a list of the known-bad answers, which
    admits every answer nobody has thought of yet.
    """


_TRANSLATIONS = (("&&", " and "), ("||", " or "))


def runs_for(condition: str, event: Mapping[str, str]) -> bool:
    """Whether a step carrying ``condition`` runs for ``event``.

    ``event`` maps whole context references -- ``github.event_name`` and the
    like -- to their values. A reference the event does not define raises: a
    missing value must not quietly compare unequal to everything.

    The expression is translated into Python's operators and parsed with ``ast``
    so that precedence and parentheses come from a real parser rather than from
    another hand-rolled one. The walk below then accepts a whitelist of node
    types and raises on everything else.
    """
    if not condition:
        return True

    values: dict[str, str] = {}
    expression = condition
    for reference in sorted(event, key=len, reverse=True):
        name = f"_ref_{len(values)}"
        if reference in expression:
            expression = expression.replace(reference, name)
            values[name] = event[reference]
    for source, target in _TRANSLATIONS:
        expression = expression.replace(source, target)

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise UnreadableCondition(f"{condition!r} is not an expression this can read") from error
    return _evaluate(tree.body, values, condition)


def _evaluate(node: ast.AST, values: Mapping[str, str], condition: str) -> bool:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
        results = [_evaluate(value, values, condition) for value in node.values]
        return all(results) if isinstance(node.op, ast.And) else any(results)
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        operator = node.ops[0]
        if isinstance(operator, (ast.Eq, ast.NotEq)):
            left = _value(node.left, values, condition)
            right = _value(node.comparators[0], values, condition)
            return left == right if isinstance(operator, ast.Eq) else left != right
    raise UnreadableCondition(
        f"{condition!r} uses {type(node).__name__}, which this evaluator does not implement"
    )


def _value(node: ast.AST, values: Mapping[str, str], condition: str) -> str:
    """One side of a comparison: a context reference, or a string literal.

    A bare context reference in boolean position never reaches here, because
    ``_evaluate`` accepts only comparisons and boolean operators -- the
    truthiness of a string is not an answer this may give.
    """
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise UnreadableCondition(
                f"{condition!r} reads a context value this event does not define"
            )
        return values[node.id]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    raise UnreadableCondition(
        f"{condition!r} compares {type(node).__name__}, which this evaluator does not implement"
    )
