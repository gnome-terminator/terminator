"""m42: paste an image-only clipboard as a PNG path.

VTE 0.68 only requests text from the clipboard, so a screenshot or
"Copy image" used to paste nothing.  Terminator now checks the targets
first and, when there is no text, saves the pixbuf and pastes its path.
"""

import os

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Vte', '2.91')

from gi.repository import Gdk, GdkPixbuf

from terminatorlib import clipboard_image
from terminatorlib import terminal as term_mod
from terminatorlib.terminal import Terminal


class _Vte(object):
    def __init__(self, paste_text=True):
        self.pasted = []
        self.fed = []
        self.focused = 0
        if paste_text:
            self.paste_text = lambda text: self.pasted.append(('text', text))

    def paste_clipboard(self):
        self.pasted.append(('clipboard', None))

    def paste_primary(self):
        self.pasted.append(('primary', None))

    def feed_child(self, data):
        self.fed.append(data)

    def grab_focus(self):
        self.focused += 1


class _Term(object):
    def __init__(self, vte):
        self.vte = vte
        self.snapshots = 0

    def _snapshot_before_input(self):
        self.snapshots += 1

    def feed(self, text):
        self.vte.feed_child(text)


class _Clipboard(object):
    def __init__(self):
        self.targets_cb = None
        self.image_cb = None
        self.targets = []
        self.pixbuf = None

    def request_targets(self, callback, data):
        self.targets_cb = (callback, data)

    def request_image(self, callback, data):
        self.image_cb = (callback, data)

    def answer_targets(self):
        callback, data = self.targets_cb
        callback(self, self.targets, len(self.targets), data)

    def answer_image(self):
        callback, data = self.image_cb
        callback(self, self.pixbuf, data)


def _pixbuf():
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 3, 2)
    pixbuf.fill(0xff0000ff)
    return pixbuf


def _terminal(monkeypatch, tmpdir, vte=None):
    term = Terminal.__new__(Terminal)
    target = _Term(vte or _Vte())
    term.__dict__['vte'] = target.vte
    term.__dict__['clipboard'] = _Clipboard()
    term.__dict__['config'] = {'disable_mouse_paste': False}
    term.__dict__['terminator'] = type('App', (), {
        'get_target_terms': lambda self, widget: [target],
    })()
    monkeypatch.setattr(clipboard_image, 'image_dir', lambda: str(tmpdir))
    return term, target


def _targets(*names):
    return [Gdk.atom_intern(name, False) for name in names]


def test_image_only_pastes_a_quoted_png_path(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    term.clipboard.targets = _targets('image/png', 'image/jpeg')
    term.clipboard.pixbuf = _pixbuf()

    term.paste_clipboard()
    term.clipboard.answer_targets()
    term.clipboard.answer_image()

    pasted = target.vte.pasted
    assert len(pasted) == 1
    kind, text = pasted[0]
    assert kind == 'text'
    path = text.rstrip()
    assert text.endswith(' ')
    assert os.path.isfile(path)
    assert path.endswith('.png')
    assert path.startswith(str(tmpdir))
    assert GdkPixbuf.Pixbuf.new_from_file(path).get_width() == 3
    assert target.snapshots == 0
    assert term.vte.focused == 1


def test_text_targets_still_use_vte_paste(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    term.clipboard.targets = _targets('UTF8_STRING', 'image/png')
    term.clipboard.pixbuf = _pixbuf()

    term.paste_clipboard()
    term.clipboard.answer_targets()

    assert target.vte.pasted == [('clipboard', None)]
    assert target.snapshots == 1
    assert term.clipboard.image_cb is None


def test_empty_clipboard_falls_through_to_vte(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    term.clipboard.targets = []

    term.paste_clipboard()
    term.clipboard.answer_targets()

    assert target.vte.pasted == [('clipboard', None)]


def test_primary_paste_stays_text_only(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    term.clipboard.targets = _targets('image/png')

    term.paste_clipboard(primary=True)

    assert target.vte.pasted == [('primary', None)]
    assert term.clipboard.targets_cb is None


def test_disabled_mouse_paste_does_nothing(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    term.config['disable_mouse_paste'] = True

    term.paste_clipboard(mouse=True)

    assert term.clipboard.targets_cb is None
    assert target.vte.pasted == []


def test_old_vte_without_paste_text_feeds_the_path(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir, vte=_Vte(paste_text=False))
    term.clipboard.targets = _targets('image/png')
    term.clipboard.pixbuf = _pixbuf()

    term.paste_clipboard()
    term.clipboard.answer_targets()
    term.clipboard.answer_image()

    assert target.vte.pasted == []
    assert len(target.vte.fed) == 1
    assert target.vte.fed[0].endswith(' ')


def test_save_failure_reports_and_keeps_clean(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    term.clipboard.targets = _targets('image/png')
    term.clipboard.pixbuf = _pixbuf()

    def fail(*_args, **_kwargs):
        raise IOError('disk full')

    monkeypatch.setattr(clipboard_image, 'save_pixbuf', fail)
    term.paste_clipboard()
    term.clipboard.answer_targets()
    term.clipboard.answer_image()

    assert target.vte.pasted == []
    assert target.vte.fed == []
    assert tmpdir.listdir() == []


def test_paste_text_quotes_every_path():
    text = clipboard_image.paste_text(['/tmp/a b.png', "/tmp/it's.png"])
    assert text == "'/tmp/a b.png' '/tmp/it'\"'\"'s.png' "


def test_save_pixbuf_writes_a_private_file(tmpdir):
    path = clipboard_image.save_pixbuf(_pixbuf(), directory=str(tmpdir))
    assert os.path.isfile(path)
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert os.path.basename(path).startswith(clipboard_image.PREFIX)


def test_prune_removes_old_images(tmpdir):
    old = clipboard_image.save_pixbuf(_pixbuf(), directory=str(tmpdir))
    os.utime(old, (1000, 1000))
    keep = clipboard_image.save_pixbuf(_pixbuf(), directory=str(tmpdir))

    removed = clipboard_image.prune(str(tmpdir), now=10 ** 9,
                                    max_age=60, max_files=10)
    assert removed == 1
    assert not os.path.exists(old)
    assert os.path.exists(keep)


def test_prune_caps_the_number_of_files(tmpdir):
    paths = [clipboard_image.save_pixbuf(_pixbuf(), directory=str(tmpdir))
             for _ in range(4)]
    for index, path in enumerate(paths):
        os.utime(path, (1000 + index, 1000 + index))

    removed = clipboard_image.prune(str(tmpdir), now=2000,
                                    max_age=10 ** 6, max_files=2)
    assert removed == 2
    assert not os.path.exists(paths[0])
    assert not os.path.exists(paths[1])
    assert os.path.exists(paths[2])
    assert os.path.exists(paths[3])


def test_prune_ignores_other_files(tmpdir):
    other = tmpdir.join('notes.txt')
    other.write('keep me')
    os.utime(str(other), (1000, 1000))
    assert clipboard_image.prune(str(tmpdir), now=10 ** 9,
                                 max_age=60, max_files=10) == 0
    assert other.check()


def test_drop_image_saves_and_pastes(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)

    class _Selection(object):
        def get_pixbuf(self):
            return _pixbuf()

    term._drop_image(_Selection())

    assert len(target.vte.pasted) == 1
    assert target.vte.pasted[0][0] == 'text'
    assert os.path.isfile(target.vte.pasted[0][1].rstrip())


class _DragContext(object):
    def __init__(self, targets):
        self.targets = targets

    def list_targets(self):
        return self.targets


class _DropData(object):
    def __init__(self, pixbuf=None, text=None):
        self.pixbuf = pixbuf
        self.text = text

    def get_pixbuf(self):
        return self.pixbuf

    def get_data(self):
        return self.text

    def get_data_type(self):
        return 'image/png'


def _drop(monkeypatch, term, targets, data, info=0):
    monkeypatch.setattr(term_mod.Gtk, 'targets_include_text',
                        lambda atoms: any(str(a) == 'UTF8_STRING'
                                          for a in atoms))
    monkeypatch.setattr(term_mod.Gtk, 'targets_include_uri',
                        lambda atoms: any(str(a) == 'text/uri-list'
                                          for a in atoms))
    monkeypatch.setattr(term_mod.Gtk, 'targets_include_image',
                        lambda atoms, writable: any(
                            str(a).startswith('image/') for a in atoms))
    term.on_drag_data_received(None, _DragContext(targets), 0, 0, data,
                               info, 0, None)


def test_image_only_drop_saves_and_pastes(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    _drop(monkeypatch, term, _targets('image/png'), _DropData(_pixbuf()))

    assert len(target.vte.pasted) == 1
    assert os.path.isfile(target.vte.pasted[0][1].rstrip())


def test_image_file_drop_still_pastes_its_uri(monkeypatch, tmpdir):
    term, target = _terminal(monkeypatch, tmpdir)
    data = _DropData(_pixbuf(), b'file:///tmp/a%20b.png\r\n')
    _drop(monkeypatch, term, _targets('text/uri-list', 'image/png'), data)

    assert target.vte.fed == ["'/tmp/a b.png' "]
    assert target.vte.pasted == []
