from __future__ import annotations

from agentask.domain.frames import FrameRegistry


def test_attach_assigns_refs_and_parent_lineage() -> None:
    reg = FrameRegistry()
    main = reg.attach("M", None)
    child = reg.attach("C", "M")
    grand = reg.attach("G", "C")
    assert main.ref != child.ref != grand.ref
    assert reg.lineage(grand.ref) == ((main.ref, 0), (child.ref, 0), (grand.ref, 0))
    assert reg.depth(grand.ref) == 2


def test_same_key_attached_again_keeps_ref() -> None:
    reg = FrameRegistry()
    first = reg.attach("M", None)
    assert reg.attach("M", None).ref == first.ref


def test_navigation_invalidates_frame_and_descendants_only() -> None:
    reg = FrameRegistry()
    reg.attach("M", None)
    c1 = reg.attach("C1", "M")
    g1 = reg.attach("G1", "C1")
    c2 = reg.attach("C2", "M")
    before = {f.ref: reg.lineage(f.ref) for f in (c1, g1, c2)}
    reg.navigated("C1")
    assert not reg.is_current(before[c1.ref])
    assert not reg.is_current(before[g1.ref])
    assert reg.is_current(before[c2.ref])


def test_detach_invalidates_subtree_and_new_attach_gets_new_ref() -> None:
    reg = FrameRegistry()
    reg.attach("M", None)
    c = reg.attach("C", "M")
    g = reg.attach("G", "C")
    lineage = reg.lineage(g.ref)
    reg.detached("C")
    assert not reg.is_current(lineage)
    assert reg.info(c.ref) is None and reg.info(g.ref) is None
    again = reg.attach("C2", "M")
    assert again.ref not in {c.ref, g.ref}


def test_tree_revision_changes_on_every_event() -> None:
    reg = FrameRegistry()
    revisions = [reg.tree_revision]
    reg.attach("M", None)
    revisions.append(reg.tree_revision)
    reg.attach("C", "M")
    revisions.append(reg.tree_revision)
    reg.navigated("C")
    revisions.append(reg.tree_revision)
    reg.detached("C")
    revisions.append(reg.tree_revision)
    assert len(set(revisions)) == 5
