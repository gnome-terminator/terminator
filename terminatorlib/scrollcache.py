from bisect import bisect_left, bisect_right
from .util import dbg
from collections import deque


class ScrollCache:
    """Class implementing scroll cache functionality"""


    def __init__(self, terminal):
        """Class initialiser"""
        self.vte_offset = terminal.vte.get_cursor_position()[1]
        self.scroll_cache = []
        self.reset(terminal)


    def reset(self, terminal):
        self.scrolling = False
        self.can_restore = False

        # The scrollbar and vte desync after 'clear/reset', so need to store the offset.
        self.prev_vte_offset = self.vte_offset
        self.prev_scroll_cache = self.scroll_cache

        self.vte_offset = terminal.vte.get_cursor_position()[1]
        self.scroll_cache = []

        # Fullscreen programs like vim restore the terminal after exiting, try detect that.
        self.prev_scrollbar_value = deque(maxlen=2)
        self.prev_scrollbar_upper = deque(maxlen=2)
        self.prev_scrollbar_value.append(terminal.scrollbar.get_adjustment().get_value())
        self.prev_scrollbar_upper.append(terminal.scrollbar.get_adjustment().get_upper())


    def scroll_restored(self, terminal):
        dbg(f"{terminal.scrollbar.get_adjustment().get_value()}/{self.prev_scrollbar_value}, "
            f"{terminal.scrollbar.get_adjustment().get_upper()}/{self.prev_scrollbar_upper}")
        # Detecting the special case where a full screen application like vim has just returned control.
        return (len(self.prev_scrollbar_upper) == 2 and len(self.prev_scrollbar_value) == 2 and
            self.prev_scrollbar_value[0] == 0.0 and
            self.prev_scrollbar_upper[0] == terminal.scrollbar.get_adjustment().get_page_size() and
            terminal.scrollbar.get_adjustment().get_value() != 0.0 and
            terminal.scrollbar.get_adjustment().get_upper() != terminal.scrollbar.get_adjustment().get_page_size() and
            terminal.scrollbar.get_adjustment().get_value() - self.prev_scrollbar_value[1] <= 2 and
            terminal.scrollbar.get_adjustment().get_upper() - self.prev_scrollbar_upper[1] <= 2)


    # Calculates the scroll value accounting for any scrollback limiting
    def calculate_scroll_value(self, terminal, raw_value):
        return (terminal.scrollbar.get_adjustment().get_upper() -
                (self.get_cursor_pos(terminal) - raw_value) - 1)


    # Invert a scroll value to no longer account for scrollback limiting (such as those stored in the cache)
    def calculate_inv_scroll_value(self, terminal, value):
        return (value - terminal.scrollbar.get_adjustment().get_upper() + self.get_cursor_pos(terminal) + 1)


    def scroll_handler(self, terminal):
        # Don't try handle the scrolling we perform internally
        if self.scrolling:
            return

        if self.can_restore and self.scroll_restored(terminal):
            self.print_cache(terminal, "Scrolling restored after reset")
            self.vte_offset = self.prev_vte_offset
            self.scroll_cache = self.prev_scroll_cache
        elif (terminal.scrollbar.get_adjustment().get_value() == 0.0 and
            terminal.scrollbar.get_adjustment().get_lower() == 0.0 and
            terminal.scrollbar.get_adjustment().get_upper() == terminal.scrollbar.get_adjustment().get_page_size()):
            # Try to detect if the terminal was cleared with 'clear'
            dbg(f"Clear/reset detected, clearing cache")
            self.reset(terminal)
            self.can_restore = True
        else:
            self.prev_scrollbar_value.append(terminal.scrollbar.get_adjustment().get_value())
            self.prev_scrollbar_upper.append(terminal.scrollbar.get_adjustment().get_upper())


    # Convenience for getting 'clear/reset' safe cursor pos
    def get_cursor_pos(self, terminal):
        return terminal.vte.get_cursor_position()[1] - self.vte_offset


    def clean_cache(self, terminal):
        # Need to remove cached points that have been scrolled out
        if terminal.config['scrollback_infinite'] != True:
            while (len(self.scroll_cache) and
                (self.get_cursor_pos(terminal) - terminal.vte.get_scrollback_lines()) > self.scroll_cache[0]):
                dbg(f"Removing {self.scroll_cache[0]} from cache as it's after "
                    f"{(self.get_cursor_pos(terminal) - terminal.vte.get_scrollback_lines())}")
                self.scroll_cache.pop(0)


    def print_cache(self, terminal, when):
        scrollback = "inf" if terminal.vte.get_scrollback_lines() == 9223372036854775807 else str(terminal.vte.get_scrollback_lines())
        dbg(f"{when}: scrollback: {scrollback}, "
            f"current: {self.get_cursor_pos(terminal)}, "
            f"raw: {terminal.vte.get_cursor_position()[1]}, "
            f"offset: {self.vte_offset}, "
            f"scrollbar: {terminal.scrollbar.get_adjustment().get_value():.2f}, "
            f"cache: {self.scroll_cache}, "
            f"can restore: {self.can_restore}")


    def key_cache_scroll(self, terminal, offset):
        self.clean_cache(terminal)
        self.print_cache(terminal, "append before")

        self.can_restore = False

        scroll_pos = self.get_cursor_pos(terminal) - offset

        if len(self.scroll_cache) == 0:
            self.scroll_cache.append(scroll_pos)
        else:
            # Find where to insert (may be out of order with fullscreen apps)
            idx = bisect_left(self.scroll_cache, scroll_pos)
            if idx == len(self.scroll_cache) or self.scroll_cache[idx] != scroll_pos:
                self.scroll_cache.insert(idx, scroll_pos)

        self.print_cache(terminal, "append after")


    def key_prev_scroll(self, terminal):
        self.clean_cache(terminal)
        self.print_cache(terminal, "up before")

        if len(self.scroll_cache) > 0:
            scroll_cache_idx = bisect_left(self.scroll_cache,
                self.calculate_inv_scroll_value(terminal,
                    terminal.scrollbar.get_adjustment().get_value())) - 1

            if scroll_cache_idx >= 0:
                self.scrolling = True
                terminal.scrollbar.set_value(self.calculate_scroll_value(terminal, self.scroll_cache[scroll_cache_idx]))
                self.scrolling = False

        self.print_cache(terminal, "up after")


    def key_next_scroll(self, terminal):
        self.clean_cache(terminal)
        self.print_cache(terminal, "down before")

        scroll_cache_idx = bisect_right(self.scroll_cache,
            self.calculate_inv_scroll_value(terminal,
                terminal.scrollbar.get_adjustment().get_value()))

        self.scrolling = True
        if scroll_cache_idx >= len(self.scroll_cache):
            terminal.scrollbar.set_value(terminal.scrollbar.get_adjustment().get_upper())
        else:
            terminal.scrollbar.set_value(self.calculate_scroll_value(terminal, self.scroll_cache[scroll_cache_idx]))
        self.scrolling = False

        self.print_cache(terminal, "down after")