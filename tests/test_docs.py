"""Documentation coverage.

A reference that silently falls behind the code is worse than none: it is
confidently wrong. These tests make the view reference fail when the vocabulary
grows without it, which is the only thing that keeps the two together.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pysilver
from pysilver.runtime.events import HANDLER_KEYS
from pysilver.spec import WidgetKind
from pysilver.spec.models import StyleSpec, WidgetSpec

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = (ROOT / "docs/view-reference.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("kind", sorted(k.value for k in WidgetKind))
def test_every_widget_kind_is_documented(kind: str) -> None:
    assert f"`{kind}`" in REFERENCE, f"{kind} is missing from docs/view-reference.md"


@pytest.mark.parametrize("prop", sorted(StyleSpec.model_fields))
def test_every_style_property_is_documented(prop: str) -> None:
    assert f"`{prop}`" in REFERENCE, f"style.{prop} is missing from docs/view-reference.md"


@pytest.mark.parametrize("field", sorted(WidgetSpec.model_fields))
def test_every_node_field_is_documented(field: str) -> None:
    assert f"`{field}`" in REFERENCE, f"the {field} node field is undocumented"


@pytest.mark.parametrize("handler", sorted(HANDLER_KEYS.values()))
def test_every_handler_key_is_documented(handler: str) -> None:
    assert f"`{handler}`" in REFERENCE, f"{handler} is missing from docs/view-reference.md"


def test_the_readme_does_not_claim_a_stale_milestone() -> None:
    """The README described the project as pre-alpha at M0 for six milestones."""
    for stale in ("pre-alpha", "M0", "Status: pre-alpha"):
        assert stale not in README, f"README still says {stale!r}"


def test_the_readme_status_matches_the_major_version() -> None:
    """Only major.minor is pinned. Requiring the patch version would force a
    README edit on every bugfix release, which is how a README starts lying."""
    major, minor, _ = pysilver.__version__.split(".")
    assert f"v{major}.{minor}" in README


def test_readme_python_blocks_are_syntactically_valid() -> None:
    """A quickstart that does not parse is the worst possible first impression."""
    blocks = re.findall(r"```python\n(.*?)```", README, re.DOTALL)
    assert blocks, "the README has no Python examples"
    for i, block in enumerate(blocks):
        compile(block, f"<README block {i}>", "exec")


def test_reference_yaml_blocks_are_parseable() -> None:
    import yaml

    blocks = re.findall(r"```yaml\n(.*?)```", REFERENCE, re.DOTALL)
    assert blocks, "the reference has no YAML examples"
    for block in blocks:
        yaml.safe_load(block)  # raises on malformed YAML


def test_the_docs_do_not_promise_unbuilt_subsystems() -> None:
    """The reference has a "what does not exist yet" section; it must actually
    list the things that do not exist, or it is marketing."""
    tail = REFERENCE.split("## What does not exist yet")[-1]
    # Substrings, not whole phrases: the wording of each entry changes as
    # subsystems land, and a test that pins prose gets deleted rather than fixed.
    for absent in ("Motion", "IME", "without focus"):
        assert absent in tail
