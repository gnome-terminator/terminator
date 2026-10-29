"""Request Gtk 3 before pytest collects tests.

A test module that imports Gtk without gi.require_version gets Gtk 4 on
current PyGObject. terminatorlib.util then exits because Gdk 4 is already
loaded. Pytest imports this file before test modules and doctests.
"""
try:
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Vte', '2.91')
except (ImportError, ValueError):
    pass
