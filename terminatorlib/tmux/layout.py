"""Tmux layout parsing and conversion to Terminator layout format.

Parses tmux layout strings like:
  13e1,124x26,0,0[124x6,0,0,1,124x6,0,7{62x6,0,7,5,61x6,63,7,6},124x12,0,14,3]

Where:
  - 4-hex-digit checksum
  - WxH,X,Y dimensions/position
  - {...} horizontal split container
  - [...] vertical split container
  - trailing integer = pane ID
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Union


@dataclass
class LayoutNode:
    """A node in the tmux layout tree."""
    width: int
    height: int
    x_off: int
    y_off: int
    pane_id: Optional[str] = None  # e.g. '%1' for leaf nodes
    orientation: Optional[str] = None  # 'h' or 'v' for internal nodes
    children: List['LayoutNode'] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return self.pane_id is not None

    def __hash__(self):
        if self.pane_id:
            return hash(self.pane_id)
        return hash(id(self))

    def __eq__(self, other):
        if isinstance(other, LayoutNode) and self.pane_id and other.pane_id:
            return self.pane_id == other.pane_id
        return self is other


def parse_tmux_layout(layout_string: str) -> LayoutNode:
    """Parse a tmux layout string into a LayoutNode tree.

    Format: CHECKSUM,WxH,X,Y... where the remainder describes the tree.
    """
    # Strip the 4-char hex checksum and comma
    s = layout_string
    comma = s.index(',')
    s = s[comma + 1:]
    node, _ = _parse_node(s, 0)
    return node


def _parse_node(s: str, pos: int) -> tuple:
    """Parse a single node starting at pos, return (node, next_pos)."""
    # Parse WxH,X,Y
    m = re.match(r'(\d+)x(\d+),(\d+),(\d+)', s[pos:])
    if not m:
        raise ValueError('Expected WxH,X,Y at position %d: %s' % (pos, s[pos:pos+20]))
    width = int(m.group(1))
    height = int(m.group(2))
    x_off = int(m.group(3))
    y_off = int(m.group(4))
    pos += m.end()

    # What follows?
    if pos >= len(s):
        raise ValueError('Unexpected end of layout string')

    ch = s[pos]

    if ch == '{':
        # Horizontal split container
        pos += 1  # skip '{'
        children = []
        while pos < len(s) and s[pos] != '}':
            if s[pos] == ',':
                pos += 1
            child, pos = _parse_node(s, pos)
            children.append(child)
        pos += 1  # skip '}'
        return LayoutNode(width, height, x_off, y_off,
                         orientation='h', children=children), pos

    elif ch == '[':
        # Vertical split container
        pos += 1  # skip '['
        children = []
        while pos < len(s) and s[pos] != ']':
            if s[pos] == ',':
                pos += 1
            child, pos = _parse_node(s, pos)
            children.append(child)
        pos += 1  # skip ']'
        return LayoutNode(width, height, x_off, y_off,
                         orientation='v', children=children), pos

    elif ch == ',':
        # Leaf pane: ,PANE_ID
        pos += 1  # skip ','
        m2 = re.match(r'(\d+)', s[pos:])
        if not m2:
            raise ValueError('Expected pane ID at position %d' % pos)
        pane_id = '%%%s' % m2.group(1)
        pos += m2.end()
        return LayoutNode(width, height, x_off, y_off, pane_id=pane_id), pos

    else:
        raise ValueError('Unexpected character %r at position %d' % (ch, pos))


def layout_to_terminator(node: LayoutNode, parent_name: str,
                          result: Optional[dict] = None,
                          pane_index: int = 0,
                          order: int = 0) -> tuple:
    """Convert a LayoutNode tree to Terminator's flat layout format.

    Returns (result_dict, pane_index, order).
    """
    if result is None:
        result = {}

    if node.is_leaf:
        term_name = 'terminal%s' % node.pane_id[1:]  # strip '%'
        result[term_name] = {
            'type': 'Terminal',
            'parent': parent_name,
            'order': order,
            'tmux': {
                'pane_id': node.pane_id,
                'width': node.width,
                'height': node.height,
            },
        }
        return result, pane_index, order + 1

    if len(node.children) == 1:
        return layout_to_terminator(node.children[0], parent_name,
                                     result, pane_index, order)

    # Container: create nested binary panes
    pane_type = 'VPaned' if node.orientation == 'v' else 'HPaned'
    pane_name = 'pane%d' % pane_index
    result[pane_name] = {
        'type': pane_type,
        'parent': parent_name,
        'order': order,
    }
    pane_index += 1
    order += 1

    # First child
    result, pane_index, order = layout_to_terminator(
        node.children[0], pane_name, result, pane_index, order)

    # Remaining children: if more than 2, nest them
    if len(node.children) == 2:
        result, pane_index, order = layout_to_terminator(
            node.children[1], pane_name, result, pane_index, order)
    else:
        # Create a synthetic container for remaining children
        remaining = LayoutNode(
            node.width, node.height, node.x_off, node.y_off,
            orientation=node.orientation,
            children=node.children[1:],
        )
        result, pane_index, order = layout_to_terminator(
            remaining, pane_name, result, pane_index, order)

    return result, pane_index, order


def build_terminator_layout(layout_nodes: list, total_cols: int = 0,
                             total_rows: int = 0) -> dict:
    """Build a complete Terminator layout dict from tmux layout nodes.

    Args:
        layout_nodes: list of LayoutNode trees (one per tmux window)
        total_cols: total columns for window sizing
        total_rows: total rows for window sizing
    """
    result = {}
    window_name = 'window0'
    parent_name = window_name
    result[window_name] = {'type': 'Window', 'parent': ''}
    if total_cols and total_rows:
        result[window_name]['tmux_size'] = [total_cols, total_rows]

    if len(layout_nodes) > 1:
        notebook_name = 'notebook0'
        result[notebook_name] = {'type': 'Notebook', 'parent': parent_name}
        parent_name = notebook_name

    pane_index = 0
    order = 0
    for node in layout_nodes:
        result, pane_index, order = layout_to_terminator(
            node, parent_name, result, pane_index, order)

    return result


def get_pane_ids(node: LayoutNode) -> Set[str]:
    """Extract all pane IDs from a layout tree."""
    panes = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n.is_leaf:
            panes.add(n.pane_id)
        else:
            stack.extend(n.children)
    return panes


def find_pane_parent(pane_id: str, node: LayoutNode) -> Optional[LayoutNode]:
    """Find the parent container of a pane by ID."""
    stack = [node]
    while stack:
        n = stack.pop()
        if not n.is_leaf:
            for child in n.children:
                if child.is_leaf and child.pane_id == pane_id:
                    return n
                stack.append(child)
    return None


def find_pane_node(pane_id: str, node: LayoutNode) -> Optional[LayoutNode]:
    """Find a leaf node by pane ID."""
    stack = [node]
    while stack:
        n = stack.pop()
        if n.is_leaf and n.pane_id == pane_id:
            return n
        if not n.is_leaf:
            stack.extend(n.children)
    return None
