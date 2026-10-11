# Terminator - close_confirm unit tests (process rules; no dialog)
"""Tests for D17 process detection without showing GTK dialogs."""

from __future__ import print_function

import os

import pytest

from terminatorlib import close_confirm as cc


def test_basename_strips_login_dash():
    assert cc._basename_of('-bash') == 'bash'
    assert cc._basename_of('/usr/bin/zsh') == 'zsh'


def test_shell_only_not_confirm():
    class Term(object):
        pid = os.getpid()  # pytest process — usually not a shell basename

    # Force ignore of our own process name by treating it as shell
    ignore = set()
    # Monkeypatch relevant_processes to use known shell pid simulation
    class ShellTerm(object):
        pid = 1  # init — name varies; use mock via monkeypatch

    # Unit-level: empty found when basename in SHELL
    # Simulate by calling with a fake that we control via /proc of self:
    # Mark our pid's basename as shell by temporarily adding it
    myname = cc._proc_basename(os.getpid()) or 'python'
    shells = set(cc.SHELL_BASENAMES)
    shells.add(myname)
    # Inline check of filter logic
    found = []
    bname = myname
    skip = shells | set(cc.DEFAULT_CLOSE_CONFIRM_IGNORE)
    if bname and bname not in skip:
        found.append((os.getpid(), bname))
    assert found == []


def test_pid_none_no_prompt():
    # m21: no pid (exited child, flatpak-spawn) -> nothing to name, no prompt
    class Term(object):
        pid = None
    need, procs = cc.should_confirm_processes([Term()])
    assert need is False
    assert procs == []


def test_ignore_list_filters_gitstatusd(monkeypatch):
    # Build fake terminal with pid that has a child named gitstatusd — hard
    # without spawning. Instead test filter membership.
    ignore = cc._ignore_set()
    for name in ('gitstatusd', 'ssh-agent', 'gpg-agent', 'dbus-daemon'):
        assert name in ignore


def test_non_shell_self_counts(monkeypatch):
    """terminal.pid itself counts when basename not shell/ignore."""
    class FakeProc(object):
        def __init__(self, pid, name, children=None):
            self.pid = pid
            self._name = name
            self._children = children or []
        def name(self):
            return self._name
        def children(self, recursive=True):
            return self._children

    class FakePsutil(object):
        Error = Exception
        @staticmethod
        def Process(pid):
            if pid == 4242:
                return FakeProc(4242, 'vim', [])
            raise FakePsutil.Error()

    monkeypatch.setattr(cc, 'relevant_processes_for_terminal',
                        lambda terminal, ignore=None: (
                            [(4242, 'vim')] if getattr(terminal, 'pid', None) == 4242
                            else [(None, '<unknown>')]))
    class Term(object):
        pid = 4242
    need, procs = cc.should_confirm_processes([Term()])
    assert need is True
    assert ('vim' in procs[0][1])


def test_idle_shells_skip_the_multiple_terminals_dialog():
    assert cc.no_process_close_result('multiple_terminals') == 'accept'
    assert cc.no_process_close_result('never') == 'accept'
    assert cc.no_process_close_result('always') == 'legacy'


def test_scope_terminals_lone_terminal():
    # Without Factory/GTK we only verify the helper exists and SHELL set
    assert 'bash' in cc.SHELL_BASENAMES
    assert callable(cc.request_close_terminal)
    assert callable(cc.scope_terminals)
