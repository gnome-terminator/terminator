"""DBus client printing, tab title lookup, new-tab commands, and
command-line option swap."""

import argparse
import importlib.machinery
import importlib.util
import os

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

import dbus

from terminatorlib.ipc import DBusService


def _load_remotinator():
    path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'remotinator'))
    loader = importlib.machinery.SourceFileLoader(
        'remotinator_under_test', path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _Proxy(object):
    def __init__(self):
        self.calls = []
        self.terms = ['urn:a', 'urn:b']

    def new_window(self):
        self.calls.append(('new_window',))
        return 'urn:win'

    def new_tab(self, uuid, options):
        self.calls.append(('new_tab', uuid, options))
        return 'urn:new-tab'

    def hsplit(self, uuid, options):
        self.calls.append(('hsplit', uuid, options))
        return 'urn:split'

    def get_window(self, uuid):
        self.calls.append(('get_window', uuid))
        return 'urn:window'

    def get_tab_title(self, uuid):
        self.calls.append(('get_tab_title', uuid))
        return 'Tab'

    def get_terminals(self):
        return self.terms

    def get_focused_terminal(self):
        return 'urn:focused'

    def set_tab_title(self, uuid, options):
        self.calls.append(('set_tab_title', uuid, options))
        return 'ignored'


def _patch_bus(monkeypatch, proxy):
    class Bus(object):
        def get_object(self, _name, _path):
            return proxy

    monkeypatch.setattr('terminatorlib.ipc.dbus.SessionBus', lambda: Bus())


def test_client_wrappers_return_the_proxy_value(monkeypatch, capsys):
    from terminatorlib import ipc
    proxy = _Proxy()
    _patch_bus(monkeypatch, proxy)
    assert ipc.hsplit('urn:once', {'execute': 'true'}) == 'urn:split'
    assert ipc.get_window('urn:once', {}) == 'urn:window'
    assert ipc.get_tab_title('urn:once', {}) == 'Tab'
    assert ipc.new_window({'layout': 'default'}) == 'urn:win'
    assert capsys.readouterr().out == ''
    assert proxy.calls[0] == ('hsplit', 'urn:once', {'execute': 'true'})
    assert [call[0] for call in proxy.calls].count('hsplit') == 1
    assert proxy.calls[-1] == ('new_window',)


def test_get_terminals_returns_lists_and_dbus_arrays(monkeypatch, capsys):
    from terminatorlib import ipc
    proxy = _Proxy()
    _patch_bus(monkeypatch, proxy)
    assert ipc.get_terminals({}) == ['urn:a', 'urn:b']
    proxy.terms = dbus.Array(['urn:a', 'urn:b'], signature='s')
    got = ipc.get_terminals({})
    assert got == proxy.terms
    assert capsys.readouterr().out == ''
    remote = _load_remotinator()
    remote.print_result(['urn:a', 'urn:b'])
    assert capsys.readouterr().out == 'urn:a\nurn:b\n'
    remote.print_result(dbus.String('urn:one'))
    assert capsys.readouterr().out == 'urn:one\n'


def test_print_result_does_not_add_a_none_line(monkeypatch, capsys):
    from terminatorlib import ipc
    proxy = _Proxy()
    _patch_bus(monkeypatch, proxy)
    remote = _load_remotinator()
    remote.print_result(ipc.hsplit('urn:once', {}))
    assert capsys.readouterr().out == 'urn:split\n'
    assert ipc.get_focused_terminal({}) == 'urn:focused'
    assert capsys.readouterr().out == ''
    remote.print_result(ipc.get_focused_terminal({}))
    assert capsys.readouterr().out == 'urn:focused\n'
    assert ipc.set_tab_title('urn:once', {'tab-title': 'A'}) is None
    assert capsys.readouterr().out == ''
    remote.print_result(None)
    assert capsys.readouterr().out == 'None\n'


def test_new_tab_client_forwards_options(monkeypatch, capsys):
    from terminatorlib import ipc
    proxy = _Proxy()
    _patch_bus(monkeypatch, proxy)
    options = {
        'execute': 'htop',
        'tab-title': 'Missing Tab Title! Use -t argument!',
    }
    assert ipc.new_tab('urn:once', options) == 'urn:new-tab'
    assert proxy.calls == [('new_tab', 'urn:once', options)]
    assert capsys.readouterr().out == ''


class _Label(object):
    def __init__(self):
        self.calls = []

    def set_custom_label(self, title, force=False):
        self.calls.append((title, force))


class _Page(object):
    def __init__(self, kind, terms=None):
        self.kind = kind
        self.terms = list(terms or [])
        self.label = _Label()


class _Notebook(object):
    def __init__(self, pages):
        self.pages = pages
        self.current_reads = 0

    def get_children(self):
        return list(self.pages)

    def get_tab_label(self, page):
        return page.label

    def get_current_page(self):
        self.current_reads += 1
        return 0


class _Window(object):
    def __init__(self, notebook, is_notebook=True):
        self.notebook = notebook
        self._is_notebook = is_notebook
        self.child_reads = 0

    def is_child_notebook(self):
        return self._is_notebook

    def get_children(self):
        self.child_reads += 1
        if not self._is_notebook:
            raise AssertionError('current page was read without a notebook')
        return [self.notebook]


def _patch_lookup(monkeypatch):
    import terminatorlib.ipc as ipc

    def is_terminal(widget, kind):
        return getattr(widget, 'kind', None) == kind

    def descendants(widget):
        return (None, list(widget.terms))

    monkeypatch.setattr(ipc.Factory, 'isinstance',
                        lambda self, widget, kind: is_terminal(widget, kind))
    monkeypatch.setattr(ipc, 'enumerate_descendants', descendants)


class _Term(object):
    def __init__(self, window):
        self.window = window
        self.kind = 'Terminal'
        self.label = _Label()

    def get_toplevel(self):
        return self.window


def _svc_for(mapping):
    class App(object):
        def find_terminal_by_uuid(self, uuid):
            return mapping.get(uuid)

    return type('S', (), {'terminator': App()})()


def test_set_tab_title_writes_the_page_that_holds_the_terminal(monkeypatch):
    _patch_lookup(monkeypatch)
    second_term = _Term(None)
    second = _Page('Paned', [second_term])
    first_term = _Term(None)
    # A terminal page is the terminal object itself.
    notebook = _Notebook([first_term, second])
    window = _Window(notebook)
    first_term.window = window
    second_term.window = window

    svc = _svc_for({'first': first_term, 'second': second_term})
    DBusService.set_tab_title(svc, 'second', {'tab-title': 'Logs'})
    assert second.label.calls == [('Logs', True)]
    assert first_term.label.calls == []
    assert notebook.current_reads == 0

    elsewhere = _Term(_Window(_Notebook([_Page('Paned', [])])))
    DBusService.set_tab_title(
        _svc_for({'missing': elsewhere, 'second': second_term,
                  'first': first_term}),
        'missing', {'tab-title': 'Nope'})
    assert second.label.calls == [('Logs', True)]
    assert first_term.label.calls == []
    assert elsewhere.label.calls == []

    only = _Term(None)
    one = _Notebook([only])
    only.window = _Window(one)
    DBusService.set_tab_title(
        _svc_for({'only': only}), 'only', {'tab-title': 'Solo'})
    assert only.label.calls == [('Solo', True)]
    assert one.current_reads == 0

    bare = _Window(notebook, is_notebook=False)
    outsider = _Term(bare)
    DBusService.set_tab_title(
        _svc_for({'first': outsider}), 'first', {'tab-title': 'Skip'})
    assert bare.child_reads == 0
    assert second.label.calls == [('Logs', True)]


def _pump():
    from gi.repository import Gtk
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def _service(app):
    class Svc(object):
        terminator = app
        new_terminal = DBusService.new_terminal
        get_terminals = DBusService.get_terminals

    return Svc()


def test_new_tab_execute_spawns_one_page(monkeypatch):
    from terminatorlib.factory import Factory
    from terminatorlib.notebook import Notebook
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator

    spawned = []

    def spawn(self, widget=None, respawn=False, debugserver=False,
              init_command=None):
        spawned.append(init_command)

    monkeypatch.setattr(Terminal, 'spawn_child', spawn)
    from terminatorlib import optionparse
    app = Terminator()
    old_terms = list(app.terminals)
    old_wins = list(app.windows)
    previous_options = optionparse.options
    app.terminals = []
    app.windows = []
    class _Opts(object):
        def __init__(self):
            self.command = None
            self.execute = None
            self.profile = None
            self.marker = 'keep'

        def __getattr__(self, _name):
            return None

    opts = _Opts()
    optionparse.options = opts
    app.config.options_set(opts)
    window = None
    try:
        window = Factory().make('Window')
        first = Factory().make('Terminal')
        window.add(first)
        window.show_all()
        _pump()
        DBusService.new_tab(_service(app), first.uuid.urn, {
            'execute': 'htop',
            'tab-title': 'Missing Tab Title! Use -t argument!',
        })
        _pump()
        assert spawned == ['htop']
        notebook = window.get_child()
        assert isinstance(notebook, Notebook)
        assert notebook.get_n_pages() == 2
        fresh = app.config.options_get()
        assert fresh is opts
        assert fresh.command is None and fresh.execute is None
        assert fresh.marker == 'keep'

        spawned[:] = []
        DBusService.new_tab(_service(app), first.uuid.urn, {
            'tab-title': 'Missing Tab Title! Use -t argument!',
            'title': 'SHOULD_NOT_APPLY',
        })
        _pump()
        assert spawned == [None]
        assert notebook.get_n_pages() == 3
        label = notebook.get_tab_label(notebook.get_nth_page(2))
        assert label.get_custom_label() is None

        spawned[:] = []
        DBusService.new_tab(_service(app), first.uuid.urn, {'execute': 'vim'})
        _pump()
        assert spawned == ['vim']
        assert notebook.get_n_pages() == 4
    finally:
        optionparse.options = previous_options
        app.config.options_set(previous_options)
        if window is not None:
            for term in list(app.terminals):
                top = term.get_toplevel() if hasattr(term, 'get_toplevel') else None
                if top is window:
                    app.deregister_terminal(term)
            window.destroy()
            _pump()
        app.terminals = old_terms
        app.windows = old_wins


def test_cmdline_option_swap_restores_the_namespace():
    from terminatorlib import optionparse
    from terminatorlib.config import Config

    cfg = Config()
    previous_options = optionparse.options
    previous_cfg = cfg.options_get()
    marker = ['original-list']
    ns = argparse.Namespace(maximise=False, execute=marker, command=None)
    optionparse.options = ns
    cfg.options_set(ns)
    assert optionparse.options is ns
    assert cfg.options_get() is ns

    class App(object):
        def __init__(self):
            self.config = cfg
            self.windows = []
            self.seen = []

        def create_layout(self, layout):
            opts = self.config.options_get()
            self.seen.append(layout)
            assert opts.maximise == 'True'
            opts.execute = None
            opts.command = None

        def layout_done(self):
            self.seen.append('done')

        def get_windows(self):
            return [self]

        def tab_new(self):
            opts = self.config.options_get()
            self.seen.append(('tab', opts.execute))

    app = App()
    svc = type('S', (), {'terminator': app})()
    incoming = {
        'configjson': '',
        'execute': 'htop',
        'layout': 'custom',
        'maximise': 'True',
    }
    try:
        DBusService.new_window_cmdline(svc, incoming)
        assert app.seen[:2] == ['custom', 'done']
        assert cfg.options_get() is ns
        assert ns.maximise is False
        assert ns.execute is marker
        assert incoming['execute'] == 'htop'

        ident = ns.__dict__
        try:
            DBusService.new_window_cmdline(svc, {'layout': 'x'})
        except KeyError:
            pass
        else:
            raise AssertionError('missing configjson should raise KeyError')
        assert ns.__dict__ is ident
        assert ns.maximise is False

        try:
            DBusService.new_window_cmdline(svc, {'configjson': ''})
        except Exception:
            pass
        assert cfg.options_get() is ns
        assert ns.maximise is False
        assert type(ns.maximise) is bool
        assert ns.execute is marker

        app.get_windows = lambda: [app]
        DBusService.new_tab_cmdline(svc, {'execute': 'htop', 'configjson': ''})
        assert app.seen[-1] == ('tab', 'htop')
        assert ns.execute is marker
        assert incoming['execute'] == 'htop'
    finally:
        optionparse.options = previous_options
        cfg.options_set(previous_cfg)
