"""Test fixtures.

Two rules, both enforced by the PII guard running over this checkout in CI:

* Fixtures use **invented surnames only**. Never a real one, not even a common one.
* A fixture that must *look like* something the guard rejects (an absolute path, a
  a GEDCOM record) is **assembled at runtime**, never committed as a
  literal -- a committed literal would be a real finding in this repository.
"""
