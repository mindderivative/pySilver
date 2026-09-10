"""A ViewModel for the scoping tests, in a correctly named module.

It has to live here rather than in the test file: the naming rule is enforced
at bind time, and a class defined in `test_view_models.py` is rejected -- which
is the point of the rule and is itself covered by a test.
"""

from __future__ import annotations

from pysilver import Signal, ViewModel


class Counter(ViewModel):
    def __init__(self, start: int = 0) -> None:
        self.count = Signal(start, name="count")

    def bump(self, event: object) -> None:
        self.count.update(lambda n: n + 1)
