"""r11 plugin fixes. Fakes only: no Remote(), no menu-plugin instances, no right-click."""

import io
import os
import shlex
from contextlib import redirect_stderr

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

import pytest
from gi.repository import Gtk

from terminatorlib.plugins.custom_commands import (
    LAST_CMD_POLL_MS,
    LAST_CMD_TIMEOUT_MS,
    build_custom_cmd_list,
    last_cmd_directory,
    last_cmd_shell_command,
    last_cmd_poll_action,
    last_exe_cmd_dialog_vars,
    make_last_cmd_path,
    read_last_cmd_text,
)
from terminatorlib.plugins.logger import Logger
from terminatorlib.plugins.remote import ContainerSession
from terminatorlib.plugins.run_cmd_on_match import build_run_cmd_list
from terminatorlib.util import get_config_dir

try:
    gi.require_version('Handy', '1')
    from gi.repository import Handy
except (ImportError, ValueError):
    Handy = None

needs_handy = pytest.mark.skipif(Handy is None, reason='Handy not importable')


class _Proc:
    def __init__(self, argv):
        self._argv = list(argv)

    def cmdline(self):
        return list(self._argv)


class _MemFile:
    def __init__(self):
        self.parts = []
        self.closed = False

    def write(self, data):
        self.parts.append(data)

    def close(self):
        self.closed = True

    def getvalue(self):
        return ''.join(self.parts)


class _RangeVte:
    def __init__(self, ranges, cursor=(0, 0)):
        self.ranges = ranges
        self.cursor = cursor
        self.disconnected = None

    def get_text_range(self, row_start, col_start, row_end, col_end, *args):
        return (self.ranges[(row_start, col_start, row_end, col_end)], None)

    def get_cursor_position(self):
        return self.cursor

    def disconnect(self, handler_id):
        self.disconnected = handler_id


class _TermWrap:
    def __init__(self, vte):
        self._vte = vte

    def get_vte(self):
        return self._vte


def _logger():
    plugin = Logger()
    plugin.vte_version = 68
    return plugin


def test_write_content_keeps_non_newline_ending():
    plugin = _logger()
    vte = _RangeVte({(0, 0, 0, 5): 'hello'})
    fd = _MemFile()
    plugin.loggers[vte] = {'fd': fd, 'col': 0, 'row': 0}
    plugin.write_content(vte, 0, 0, 0, 5)
    assert fd.getvalue() == 'hello'
    assert plugin.loggers[vte]['col'] == 5
    assert plugin.loggers[vte]['row'] == 0


def test_write_content_keeps_trailing_newline():
    plugin = _logger()
    vte = _RangeVte({(0, 0, 1, 0): 'ab\n'})
    fd = _MemFile()
    plugin.loggers[vte] = {'fd': fd, 'col': 0, 'row': 0}
    plugin.write_content(vte, 0, 0, 1, 0)
    assert fd.getvalue() == 'ab\n'
    assert plugin.loggers[vte]['col'] == 0
    assert plugin.loggers[vte]['row'] == 1


def test_write_content_second_range_keeps_first_last_char():
    plugin = _logger()
    vte = _RangeVte({
        (0, 0, 0, 5): 'hello',
        (0, 5, 1, 1): 'XYZ\n!',
    })
    fd = _MemFile()
    plugin.loggers[vte] = {'fd': fd, 'col': 0, 'row': 0}
    plugin.write_content(vte, 0, 0, 0, 5)
    plugin.write_content(
        vte,
        plugin.loggers[vte]['row'],
        plugin.loggers[vte]['col'],
        1,
        1,
    )
    assert fd.getvalue() == 'helloXYZ\n!'
    assert 'o' in fd.getvalue()


def test_stop_logger_keeps_last_char_when_cursor_moved():
    plugin = _logger()
    vte = _RangeVte({(0, 0, 0, 5): 'hello'}, cursor=(5, 0))
    fd = _MemFile()
    plugin.loggers[vte] = {
        'fd': fd, 'col': 0, 'row': 0, 'handler_id': 7,
    }
    plugin.stop_logger(None, _TermWrap(vte))
    assert fd.getvalue() == 'hello'
    assert fd.closed
    assert vte.disconnected == 7


def test_container_parsers_do_not_exit():
    docker = ContainerSession('docker')
    podman = ContainerSession('podman')
    captured = io.StringIO()
    with redirect_stderr(captured):
        mysql = ['docker', 'exec', '-it', 'c', 'mysql', '-h', '127.0.0.1']
        assert docker._get_host_exec(_Proc(mysql)) == 'c'
        assert docker.GetHost(_Proc(mysql)) == 'c'
        latest = ['docker', 'exec', '-l', '-it']
        assert docker._get_host_exec(_Proc(latest)) is None
        assert docker.GetHost(_Proc(latest)) is None
        attach = ['podman', 'attach', '-l']
        assert podman._get_host_attach(_Proc(attach)) is None
        assert podman.GetHost(_Proc(attach)) is None
        shell = ['docker', 'exec', '-it', 'c', 'sh']
        assert docker._get_host_exec(_Proc(shell)) == 'c'
        assert docker.GetHost(_Proc(shell)) == 'c'
        for argv in (
            ['docker', 'exec', '--detach-keys'],
            ['docker', 'exec', '-e'],
        ):
            assert docker._get_host_exec(_Proc(argv)) is None
            assert docker.GetHost(_Proc(argv)) is None
    assert 'usage:' not in captured.getvalue()


def test_last_cmd_shell_uses_private_quoted_path():
    directory = last_cmd_directory()
    runtime = os.environ.get('XDG_RUNTIME_DIR')
    if runtime and os.path.isdir(runtime) and os.access(runtime, os.W_OK):
        assert directory == runtime
    else:
        assert directory == get_config_dir()
    path = os.path.join(directory, 'term_cmd_a b')
    command = last_cmd_shell_command(path)
    assert '/tmp/term_cmd' not in command
    assert command.startswith('fc -n -l -1 -1 > ')
    assert command.endswith('; #bookmark last cmd\n')
    target = command[len('fc -n -l -1 -1 > '):-len('; #bookmark last cmd\n')]
    assert shlex.split(target) == [path]
    first = make_last_cmd_path()
    second = make_last_cmd_path()
    try:
        assert os.path.dirname(first) == directory
        assert os.path.dirname(second) == directory
        assert first != second
        assert os.path.basename(first).startswith('term_cmd_')
        assert '/tmp/term_cmd' not in last_cmd_shell_command(first)
    finally:
        for item in (first, second):
            if os.path.exists(item):
                os.remove(item)


def test_last_cmd_poll_times_out_on_empty_file():
    assert LAST_CMD_POLL_MS == 100
    assert LAST_CMD_TIMEOUT_MS == 2000
    elapsed = 0
    previous = None
    steps = 0
    action = 'wait'
    while action == 'wait':
        elapsed += LAST_CMD_POLL_MS
        steps += 1
        assert steps < 50
        action = last_cmd_poll_action(0, previous, elapsed)
        previous = 0
    assert action == 'timeout'
    assert elapsed == LAST_CMD_TIMEOUT_MS
    assert steps == LAST_CMD_TIMEOUT_MS // LAST_CMD_POLL_MS
    assert last_cmd_poll_action(0, 0, 100) == 'wait'
    assert last_cmd_poll_action(4, None, 100) == 'wait'
    assert last_cmd_poll_action(4, 4, 100) == 'read'
    assert last_cmd_poll_action(4, 4, LAST_CMD_TIMEOUT_MS) == 'read'


def test_missing_last_cmd_dialog_fields_are_strings(tmp_path):
    present = tmp_path / 'term_cmd_sample'
    present.write_text('echo hi\n')
    assert read_last_cmd_text(str(present)) == 'echo hi'
    assert not present.exists()
    assert read_last_cmd_text(str(tmp_path / 'missing')) == ''
    dialog_vars = last_exe_cmd_dialog_vars('')
    assert dialog_vars['enabled'] is True
    assert dialog_vars['name_parse'] is False
    assert dialog_vars['name'] == ''
    assert dialog_vars['command'] == ''
    assert type(dialog_vars['name']) is str
    assert type(dialog_vars['command']) is str
    coerced = last_exe_cmd_dialog_vars(None)
    assert coerced['name'] == '' and coerced['command'] == ''
    assert type(coerced['name']) is str and type(coerced['command']) is str


def _positioned_and_free():
    return {
        'bad': {'name': 'skip'},
        'a': {
            'name': 'first', 'command': 'echo 1', 'enabled': True, 'position': 0,
        },
        'b': {
            'name': 'second', 'command': 'echo 2', 'enabled': True, 'position': 2,
        },
        'c': {'name': 'third', 'command': 'echo 3', 'enabled': True},
    }


def test_custom_cmd_list_fills_lowest_free_key():
    result = build_custom_cmd_list(_positioned_and_free())
    assert sorted(result) == [0, 1, 2]
    assert result[0]['name'] == 'first'
    assert result[2]['name'] == 'second'
    assert result[2]['command'] == 'echo 2'
    assert result[1]['name'] == 'third'
    names = [result[key]['name'] for key in result]
    assert names.count('first') == 1
    assert names.count('third') == 1


def test_custom_cmd_list_second_load_does_not_grow():
    sections = {
        'a': {'name': 'first', 'command': 'echo 1', 'enabled': True},
        'b': {'name': 'second', 'command': 'echo 2', 'enabled': True},
    }
    first = build_custom_cmd_list(sections)
    second = build_custom_cmd_list(sections)
    assert len(first) == 2
    assert len(second) == 2
    assert first is not second
    assert [first[key]['name'] for key in sorted(first)] == ['first', 'second']
    assert [first[key]['name'] for key in first].count('first') == 1
    assert [second[key]['name'] for key in sorted(second)] == ['first', 'second']


def _run_sections():
    return {
        'bad': {'regexp': 'only'},
        'a': {
            'regexp': 'first', 'command': 'c1', 'enabled': True, 'position': 0,
        },
        'gap': {'command': 'nope'},
        'b': {
            'regexp': 'second', 'command': 'c2', 'enabled': True, 'position': 2,
        },
        'c': {'regexp': 'third', 'command': 'c3', 'enabled': True},
    }


def test_run_cmd_list_loads_handlers_once_on_final_map():
    seen = []

    def spy(cmd_list):
        seen.append({key: cmd_list[key]['regexp'] for key in cmd_list})

    result = build_run_cmd_list(_run_sections(), spy)
    assert sorted(result) == [0, 1, 2]
    assert result[2]['regexp'] == 'second'
    assert result[1]['regexp'] == 'third'
    assert seen == [{0: 'first', 1: 'third', 2: 'second'}]
    seen.clear()
    empty = build_run_cmd_list(
        {'a': {'regexp': 'x'}, 'b': {'foo': 1}},
        spy,
    )
    assert empty == {}
    assert seen == []


def test_run_cmd_list_second_load_does_not_grow():
    sections = {
        'a': {'regexp': 'first', 'command': 'c1', 'enabled': True},
        'b': {'regexp': 'second', 'command': 'c2', 'enabled': True},
    }
    first = build_run_cmd_list(sections)
    second = build_run_cmd_list(sections)
    assert len(first) == 2
    assert len(second) == 2
    assert first is not second
    assert [first[key]['regexp'] for key in sorted(first)] == ['first', 'second']
    assert [first[key]['regexp'] for key in first].count('first') == 1
    assert [second[key]['regexp'] for key in sorted(second)] == ['first', 'second']


class _ProfileTerm:
    def __init__(self, profile):
        self.profile = profile
        self.calls = []

    def get_profile(self):
        return self.profile

    def set_profile(self, widget, profile, force=False):
        self.calls.append((widget, profile))
        self.profile = profile

    def get_vte(self):
        return None


class _Combo:
    def __init__(self, text):
        self._text = text

    def get_active_text(self):
        return self._text


@needs_handy
def test_autotheme_callback_does_not_apply(monkeypatch):
    import terminatorlib.plugins.auto_theme as auto_theme_mod
    from terminatorlib.plugins.auto_theme import AutoTheme

    calls = []
    monkeypatch.setattr(
        AutoTheme, 'apply_theme',
        staticmethod(lambda name: calls.append(('apply', name))),
    )
    monkeypatch.setattr(
        AutoTheme, 'change_theme',
        staticmethod(lambda isdark: calls.append(('change', isdark))),
    )
    terms = [_ProfileTerm('alpha'), _ProfileTerm('beta')]
    holder = type('Holder', (), {'terminals': terms})()
    monkeypatch.setattr(auto_theme_mod.plugin, 'Terminator', lambda: holder)
    items = []
    AutoTheme.__new__(AutoTheme).callback(items, None, terms[0])
    assert len(items) == 1
    assert isinstance(items[0], Gtk.CheckMenuItem)
    assert terms[0].profile == 'alpha' and terms[0].calls == []
    assert terms[1].profile == 'beta' and terms[1].calls == []
    assert calls == []


def _patch_autotheme_monitor(monkeypatch, AutoTheme, scheme_token):
    events = []
    monitored = {'on': True}

    def teardown():
        events.append(('down', AutoTheme.change_cb))
        monitored['on'] = False

    def setup():
        events.append('up')
        monitored['on'] = True

    class StyleManager:
        def set_color_scheme(self, scheme):
            events.append(('scheme', scheme, monitored['on']))

        def get_color_scheme(self):
            return scheme_token

    monkeypatch.setattr(AutoTheme, 'teardown_theme_monitor', staticmethod(teardown))
    monkeypatch.setattr(AutoTheme, 'setup_theme_monitor', staticmethod(setup))
    monkeypatch.setattr(
        Handy.StyleManager, 'get_default', staticmethod(lambda: StyleManager()),
    )
    return events


@needs_handy
def test_autotheme_cancel_restores_profiles_and_drops_monitor(monkeypatch):
    import terminatorlib.plugins.auto_theme as auto_theme_mod
    from terminatorlib.plugins.auto_theme import (
        AutoTheme, MySettingDialog,
    )

    token = object()
    events = _patch_autotheme_monitor(monkeypatch, AutoTheme, token)
    monkeypatch.setattr(AutoTheme, 'mode', 'Dark')
    monkeypatch.setattr(AutoTheme, 'change_cb', lambda is_dark: None)
    saved = []
    monkeypatch.setattr(
        AutoTheme, 'save_config',
        classmethod(lambda cls, *args: saved.append(args)),
    )
    alive_a = _ProfileTerm('preview-a')
    alive_b = _ProfileTerm('preview-b')
    gone = _ProfileTerm('preview-c')
    holder = type('Holder', (), {'terminals': [alive_a, alive_b]})()
    monkeypatch.setattr(auto_theme_mod.plugin, 'Terminator', lambda: holder)
    dialog = type('Dialog', (), {})()
    dialog.mgr = AutoTheme
    dialog.light_combo = _Combo('LightProf')
    dialog.dark_combo = _Combo('DarkProf')
    dialog._restore_profiles = [
        (alive_a, 'alpha'), (alive_b, 'beta'), (gone, 'gamma'),
    ]
    dialog._restore_mode = 'Auto'
    dialog._restore_scheme = token
    MySettingDialog.on_dialog_response(dialog, None, Gtk.ResponseType.CANCEL)
    assert alive_a.profile == 'alpha'
    assert alive_b.profile == 'beta'
    assert alive_a.calls == [(None, 'alpha')]
    assert alive_b.calls == [(None, 'beta')]
    assert gone.profile == 'preview-c' and gone.calls == []
    assert AutoTheme.mode == 'Auto'
    assert events[0] == ('down', None)
    assert ('scheme', token, False) in events
    assert events[-1] == 'up'
    assert saved == []


@needs_handy
def test_autotheme_restore_resets_monitor_if_set_profile_fails(monkeypatch):
    import terminatorlib.plugins.auto_theme as auto_theme_mod
    from terminatorlib.plugins.auto_theme import (
        AutoTheme, restore_autotheme_preview,
    )

    token = object()
    events = _patch_autotheme_monitor(monkeypatch, AutoTheme, token)
    monkeypatch.setattr(AutoTheme, 'mode', 'Dark')

    class Boom(_ProfileTerm):
        def set_profile(self, widget, profile, force=False):
            raise RuntimeError('boom')

    term = Boom('preview')
    holder = type('Holder', (), {'terminals': [term]})()
    monkeypatch.setattr(auto_theme_mod.plugin, 'Terminator', lambda: holder)
    with pytest.raises(RuntimeError):
        restore_autotheme_preview(AutoTheme, [(term, 'alpha')], 'Auto', token)
    assert events[0][0] == 'down'
    assert ('scheme', token, False) in events
    assert events[-1] == 'up'
    assert AutoTheme.mode == 'Auto'


@needs_handy
def test_autotheme_ok_saves_without_restore(monkeypatch):
    import terminatorlib.plugins.auto_theme as auto_theme_mod
    from terminatorlib.plugins.auto_theme import AutoTheme, MySettingDialog

    token = object()
    events = _patch_autotheme_monitor(monkeypatch, AutoTheme, token)
    monkeypatch.setattr(AutoTheme, 'mode', 'Dark')
    terms = [_ProfileTerm('preview-a'), _ProfileTerm('preview-b')]
    holder = type('Holder', (), {'terminals': terms})()
    monkeypatch.setattr(auto_theme_mod.plugin, 'Terminator', lambda: holder)
    saved = []
    monkeypatch.setattr(
        AutoTheme, 'save_config',
        classmethod(lambda cls, *args: saved.append(args)),
    )
    dialog = type('Dialog', (), {})()
    dialog.mgr = AutoTheme
    dialog.light_combo = _Combo('LightProf')
    dialog.dark_combo = _Combo('DarkProf')
    dialog.mode_sel = 'Dark'
    dialog.variant_sel = 'dark'
    dialog._restore_profiles = [(terms[0], 'alpha'), (terms[1], 'beta')]
    dialog._restore_mode = 'Auto'
    dialog._restore_scheme = token
    MySettingDialog.on_dialog_response(dialog, None, Gtk.ResponseType.OK)
    assert terms[0].profile == 'preview-a' and terms[0].calls == []
    assert terms[1].profile == 'preview-b' and terms[1].calls == []
    assert AutoTheme.mode == 'Dark'
    assert saved == []
    assert not any(item[0] == 'scheme' for item in events)
    AutoTheme.finish_menu_dialog(dialog, Gtk.ResponseType.OK)
    assert saved == [('LightProf', 'DarkProf', 'Dark', 'dark')]
    AutoTheme.finish_menu_dialog(dialog, Gtk.ResponseType.CANCEL)
    assert len(saved) == 1


@needs_handy
def test_apply_saved_once_returns_false_and_init_schedules_once(monkeypatch):
    import terminatorlib.plugins.auto_theme as auto_theme_mod
    from terminatorlib.plugins.auto_theme import AutoTheme

    idles = []

    def idle_add(fn, *args):
        idles.append(fn)
        return 42

    monkeypatch.setattr(auto_theme_mod.GLib, 'idle_add', idle_add)
    monkeypatch.setattr(AutoTheme, 'load_config', classmethod(lambda cls: None))
    monkeypatch.setattr(AutoTheme, 'setup_theme_monitor', staticmethod(lambda: None))

    def refuse_change(*args, **kwargs):
        raise AssertionError('change_theme during init')

    monkeypatch.setattr(AutoTheme, 'change_theme', staticmethod(refuse_change))
    monkeypatch.setattr(AutoTheme, '_applied_once', False)
    monkeypatch.setattr(AutoTheme, '_apply_source', None)
    AutoTheme.__init__(AutoTheme.__new__(AutoTheme))
    AutoTheme.__init__(AutoTheme.__new__(AutoTheme))
    assert idles == [AutoTheme._apply_saved_once]
    assert AutoTheme._apply_source == 42
    AutoTheme._applied_once = True
    AutoTheme._apply_source = None
    AutoTheme.__init__(AutoTheme.__new__(AutoTheme))
    assert idles == [AutoTheme._apply_saved_once]

    events = []
    monkeypatch.setattr(AutoTheme, '_apply_source', 7)
    monkeypatch.setattr(AutoTheme, '_applied_once', False)
    monkeypatch.setattr(AutoTheme, 'mode', 'Auto')
    monkeypatch.setattr(AutoTheme, 'variant', 'dark')

    def is_dark():
        events.append('is_dark')
        assert AutoTheme._applied_once is True
        assert AutoTheme._apply_source is None
        return True

    monkeypatch.setattr(AutoTheme, 'is_dark_theme', staticmethod(is_dark))
    monkeypatch.setattr(
        AutoTheme, 'change_theme',
        staticmethod(lambda isdark: events.append(('change', isdark))),
    )
    monkeypatch.setattr(
        AutoTheme, 'teardown_theme_monitor',
        staticmethod(lambda: events.append('teardown')),
    )
    monkeypatch.setattr(
        AutoTheme, 'setup_theme_monitor',
        staticmethod(lambda: events.append('setup')),
    )

    class StyleManager:
        def set_color_scheme(self, scheme):
            events.append(('scheme', scheme))
            assert 'teardown' in events
            assert 'setup' not in events

    monkeypatch.setattr(
        Handy.StyleManager, 'get_default', staticmethod(lambda: StyleManager()),
    )
    assert AutoTheme._apply_saved_once() is False
    assert events == [
        'is_dark',
        ('change', True),
        'teardown',
        ('scheme', Handy.ColorScheme.FORCE_DARK),
        'setup',
    ]
    assert AutoTheme._applied_once is True
    assert AutoTheme._apply_source is None
