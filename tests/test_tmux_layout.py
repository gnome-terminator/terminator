"""Tests for terminatorlib.tmux.layout"""

import unittest
from terminatorlib.tmux.layout import (
    parse_tmux_layout, layout_to_terminator, build_terminator_layout,
    get_pane_ids, find_pane_parent, find_pane_node, LayoutNode,
)


class TestParseTmuxLayout(unittest.TestCase):
    """Test tmux layout string parsing."""

    def test_single_pane(self):
        """Single pane layout: checksum,WxH,X,Y,PANE_ID"""
        node = parse_tmux_layout('a1b2,80x24,0,0,0')
        self.assertTrue(node.is_leaf)
        self.assertEqual(node.width, 80)
        self.assertEqual(node.height, 24)
        self.assertEqual(node.x_off, 0)
        self.assertEqual(node.y_off, 0)
        self.assertEqual(node.pane_id, '%0')

    def test_vertical_split(self):
        """Vertical split: two panes stacked."""
        layout = 'a1b2,80x24,0,0[80x12,0,0,0,80x11,0,13,1]'
        node = parse_tmux_layout(layout)
        self.assertFalse(node.is_leaf)
        self.assertEqual(node.orientation, 'v')
        self.assertEqual(len(node.children), 2)
        self.assertEqual(node.children[0].pane_id, '%0')
        self.assertEqual(node.children[1].pane_id, '%1')
        self.assertEqual(node.children[0].height, 12)
        self.assertEqual(node.children[1].height, 11)

    def test_horizontal_split(self):
        """Horizontal split: two panes side by side."""
        layout = 'a1b2,80x24,0,0{40x24,0,0,0,39x24,41,0,1}'
        node = parse_tmux_layout(layout)
        self.assertFalse(node.is_leaf)
        self.assertEqual(node.orientation, 'h')
        self.assertEqual(len(node.children), 2)
        self.assertEqual(node.children[0].pane_id, '%0')
        self.assertEqual(node.children[1].pane_id, '%1')

    def test_nested_layout(self):
        """Nested splits: vertical with horizontal inside."""
        layout = 'a1b2,80x24,0,0[80x12,0,0,0,80x11,0,13{40x11,0,13,1,39x11,41,13,2}]'
        node = parse_tmux_layout(layout)
        self.assertEqual(node.orientation, 'v')
        self.assertEqual(len(node.children), 2)
        # First child is a leaf
        self.assertTrue(node.children[0].is_leaf)
        self.assertEqual(node.children[0].pane_id, '%0')
        # Second child is a horizontal split
        child = node.children[1]
        self.assertEqual(child.orientation, 'h')
        self.assertEqual(len(child.children), 2)
        self.assertEqual(child.children[0].pane_id, '%1')
        self.assertEqual(child.children[1].pane_id, '%2')

    def test_three_way_vertical(self):
        """Three-way vertical split."""
        layout = 'sum,80x24,0,0[80x8,0,0,0,80x7,0,9,1,80x7,0,17,2]'
        node = parse_tmux_layout(layout)
        self.assertEqual(node.orientation, 'v')
        self.assertEqual(len(node.children), 3)
        self.assertEqual(node.children[0].pane_id, '%0')
        self.assertEqual(node.children[1].pane_id, '%1')
        self.assertEqual(node.children[2].pane_id, '%2')

    def test_complex_layout(self):
        """Complex layout with multiple levels of nesting."""
        layout = '13e1,124x26,0,0[124x6,0,0,1,124x6,0,7{62x6,0,7,5,61x6,63,7,6},124x12,0,14{62x12,0,14,3,61x12,63,14,4}]'
        node = parse_tmux_layout(layout)
        self.assertEqual(node.orientation, 'v')
        self.assertEqual(len(node.children), 3)
        # First child: leaf
        self.assertTrue(node.children[0].is_leaf)
        # Second child: horizontal split
        self.assertEqual(node.children[1].orientation, 'h')
        self.assertEqual(len(node.children[1].children), 2)
        # Third child: horizontal split
        self.assertEqual(node.children[2].orientation, 'h')
        self.assertEqual(len(node.children[2].children), 2)


class TestGetPaneIds(unittest.TestCase):
    def test_single_pane(self):
        node = parse_tmux_layout('a1b2,80x24,0,0,0')
        self.assertEqual(get_pane_ids(node), {'%0'})

    def test_multiple_panes(self):
        layout = 'a1b2,80x24,0,0[80x12,0,0,0,80x11,0,13{40x11,0,13,1,39x11,41,13,2}]'
        node = parse_tmux_layout(layout)
        self.assertEqual(get_pane_ids(node), {'%0', '%1', '%2'})


class TestFindPaneParent(unittest.TestCase):
    def test_finds_parent(self):
        layout = 'a1b2,80x24,0,0[80x12,0,0,0,80x11,0,13,1]'
        node = parse_tmux_layout(layout)
        parent = find_pane_parent('%1', node)
        self.assertIsNotNone(parent)
        self.assertEqual(parent.orientation, 'v')

    def test_root_pane_returns_none(self):
        node = parse_tmux_layout('a1b2,80x24,0,0,0')
        parent = find_pane_parent('%0', node)
        self.assertIsNone(parent)

    def test_nested_pane(self):
        layout = 'a1b2,80x24,0,0[80x12,0,0,0,80x11,0,13{40x11,0,13,1,39x11,41,13,2}]'
        node = parse_tmux_layout(layout)
        parent = find_pane_parent('%2', node)
        self.assertIsNotNone(parent)
        self.assertEqual(parent.orientation, 'h')


class TestFindPaneNode(unittest.TestCase):
    def test_finds_node(self):
        layout = 'a1b2,80x24,0,0[80x12,0,0,0,80x11,0,13,1]'
        node = parse_tmux_layout(layout)
        pane = find_pane_node('%1', node)
        self.assertIsNotNone(pane)
        self.assertEqual(pane.pane_id, '%1')
        self.assertEqual(pane.height, 11)

    def test_not_found(self):
        node = parse_tmux_layout('a1b2,80x24,0,0,0')
        pane = find_pane_node('%99', node)
        self.assertIsNone(pane)


class TestLayoutToTerminator(unittest.TestCase):
    def test_single_pane(self):
        node = parse_tmux_layout('a1b2,80x24,0,0,0')
        result, _, _ = layout_to_terminator(node, 'window0')
        self.assertIn('terminal0', result)
        self.assertEqual(result['terminal0']['type'], 'Terminal')
        self.assertEqual(result['terminal0']['parent'], 'window0')
        self.assertEqual(result['terminal0']['tmux']['pane_id'], '%0')

    def test_vertical_split(self):
        layout = 'a1b2,80x24,0,0[80x12,0,0,0,80x11,0,13,1]'
        node = parse_tmux_layout(layout)
        result, _, _ = layout_to_terminator(node, 'window0')
        # Should have a VPaned and two terminals
        pane_found = False
        for name, item in result.items():
            if item['type'] == 'VPaned':
                pane_found = True
                self.assertEqual(item['parent'], 'window0')
        self.assertTrue(pane_found)
        self.assertIn('terminal0', result)
        self.assertIn('terminal1', result)

    def test_horizontal_split(self):
        layout = 'a1b2,80x24,0,0{40x24,0,0,0,39x24,41,0,1}'
        node = parse_tmux_layout(layout)
        result, _, _ = layout_to_terminator(node, 'window0')
        pane_found = False
        for name, item in result.items():
            if item['type'] == 'HPaned':
                pane_found = True
        self.assertTrue(pane_found)


class TestBuildTerminatorLayout(unittest.TestCase):
    def test_single_window(self):
        node = parse_tmux_layout('a1b2,80x24,0,0,0')
        layout = build_terminator_layout([node], 80, 24)
        self.assertIn('window0', layout)
        self.assertEqual(layout['window0']['type'], 'Window')
        self.assertIn('terminal0', layout)

    def test_multiple_windows(self):
        node1 = parse_tmux_layout('a1b2,80x24,0,0,0')
        node2 = parse_tmux_layout('c3d4,80x24,0,0,1')
        layout = build_terminator_layout([node1, node2], 80, 24)
        self.assertIn('window0', layout)
        self.assertIn('notebook0', layout)
        self.assertEqual(layout['notebook0']['type'], 'Notebook')


if __name__ == '__main__':
    unittest.main()
