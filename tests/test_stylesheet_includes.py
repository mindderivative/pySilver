"""Sharing a stylesheet across files.

`styles:` entries of the form `- source: theme.yaml` splice in the rules that
file names. The safety guards are the include machinery's own -- confinement to
the view directory, cycle and depth limits, `yaml.safe_load` only -- because a
stylesheet is exactly as untrusted as a view.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pysilver.spec import SpecError
from pysilver.spec.loader import load_view


def write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


VIEW = """
styles:
{rules}
root:
  name: root
  widget: Vertical
  children:
    - {{name: ok,  widget: Button, text: OK}}
    - {{name: bad, widget: Button, classes: danger, text: Delete}}
"""


def build(tmp_path: Path, rules: str) -> Path:
    return write(tmp_path, "app.yaml", VIEW.format(rules=rules))


def test_a_source_entry_splices_in_the_rules_it_names(tmp_path: Path) -> None:
    write(tmp_path, "theme.yaml", "- widget: Button\n  style: {height: 40}\n")
    view = load_view(build(tmp_path, "  - source: theme.yaml"))
    assert len(view.styles) == 1
    assert view.root.children[0].style.height.value == 40


def test_a_sheet_can_include_another(tmp_path: Path) -> None:
    write(tmp_path, "base.yaml", "- widget: Button\n  style: {height: 40}\n")
    write(tmp_path, "danger.yaml", "- classes: danger\n  style: {background: error}\n")
    write(tmp_path, "all.yaml", "- source: base.yaml\n- source: danger.yaml\n")
    view = load_view(build(tmp_path, "  - source: all.yaml"))
    assert len(view.styles) == 2
    assert view.root.children[1].style.background == "error"


def test_included_rules_land_in_document_order(tmp_path: Path) -> None:
    """Which is what makes a local override work: it comes after the import,
    so it wins the tie."""
    write(tmp_path, "theme.yaml", "- widget: Button\n  style: {height: 40}\n")
    view = load_view(
        build(tmp_path, "  - source: theme.yaml\n  - widget: Button\n    style: {height: 48}")
    )
    assert view.root.children[0].style.height.value == 48


def test_an_import_after_a_local_rule_wins_instead(tmp_path: Path) -> None:
    """The ordering is genuinely positional, not 'local always wins'."""
    write(tmp_path, "theme.yaml", "- widget: Button\n  style: {height: 40}\n")
    view = load_view(
        build(tmp_path, "  - widget: Button\n    style: {height: 48}\n  - source: theme.yaml")
    )
    assert view.root.children[0].style.height.value == 40


def test_inline_and_imported_rules_mix_freely(tmp_path: Path) -> None:
    write(tmp_path, "theme.yaml", "- widget: Button\n  style: {width: 150}\n")
    view = load_view(
        build(
            tmp_path, "  - classes: danger\n    style: {background: error}\n  - source: theme.yaml"
        )
    )
    style = view.root.children[1].style
    assert style.background == "error"
    assert style.width.value == 150


def test_every_sheet_is_registered_for_hot_reload(tmp_path: Path) -> None:
    """Editing a theme file must update a running application, which only
    happens if the watcher knows about it."""
    write(tmp_path, "base.yaml", "- widget: Button\n  style: {height: 40}\n")
    write(tmp_path, "all.yaml", "- source: base.yaml\n")
    sources: set[Path] = set()
    load_view(build(tmp_path, "  - source: all.yaml"), sources=sources)
    assert {p.name for p in sources} == {"app.yaml", "all.yaml", "base.yaml"}


def test_an_empty_sheet_contributes_nothing(tmp_path: Path) -> None:
    write(tmp_path, "empty.yaml", "")
    view = load_view(build(tmp_path, "  - source: empty.yaml"))
    assert view.styles == ()


# ------------------------------------------------------------------ errors


def test_a_sheet_that_is_not_a_list_says_so(tmp_path: Path) -> None:
    """A widget fragment included as a stylesheet must not surface as a
    confusing validation error about a file that is perfectly valid."""
    write(tmp_path, "widget.yaml", "widget: Button\nname: b\n")
    with pytest.raises(SpecError, match="must be a list of rules"):
        load_view(build(tmp_path, "  - source: widget.yaml"))


def test_a_cycle_is_rejected(tmp_path: Path) -> None:
    write(tmp_path, "a.yaml", "- source: b.yaml\n")
    write(tmp_path, "b.yaml", "- source: a.yaml\n")
    with pytest.raises(SpecError, match="cycle"):
        load_view(build(tmp_path, "  - source: a.yaml"))


def test_a_self_include_is_a_cycle(tmp_path: Path) -> None:
    write(tmp_path, "loop.yaml", "- source: loop.yaml\n")
    with pytest.raises(SpecError, match="cycle"):
        load_view(build(tmp_path, "  - source: loop.yaml"))


def test_an_include_cannot_escape_the_view_directory(tmp_path: Path) -> None:
    """A view file is untrusted input; a stylesheet reached from one is too."""
    outside = tmp_path.parent / "outside.yaml"
    outside.write_text("- widget: Button\n  style: {height: 1}\n")
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(SpecError):
        load_view(build(project, "  - source: ../outside.yaml"))


def test_a_missing_sheet_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="not found"):
        load_view(build(tmp_path, "  - source: nope.yaml"))


def test_an_include_entry_takes_only_source(tmp_path: Path) -> None:
    """Otherwise `- {source: t.yaml, widget: Button}` would silently drop the
    selector and apply the whole sheet."""
    write(tmp_path, "theme.yaml", "- widget: Button\n  style: {height: 40}\n")
    with pytest.raises(SpecError, match="only `source:`"):
        load_view(build(tmp_path, "  - source: theme.yaml\n    widget: Button"))


def test_a_malformed_rule_inside_a_sheet_still_validates(tmp_path: Path) -> None:
    write(tmp_path, "theme.yaml", "- widget: Nonexistent\n  style: {height: 40}\n")
    with pytest.raises(SpecError):
        load_view(build(tmp_path, "  - source: theme.yaml"))


def test_an_unknown_token_inside_a_sheet_fails_at_load(tmp_path: Path) -> None:
    write(tmp_path, "theme.yaml", "- widget: Button\n  style: {background: chartreuse}\n")
    with pytest.raises(SpecError):
        load_view(build(tmp_path, "  - source: theme.yaml"))
