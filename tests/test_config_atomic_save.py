import os, stat
from configobj import ConfigObj
from terminatorlib.config import atomic_write_config

def _parser(v):
    p = ConfigObj(); p['global_config'] = {'k': v}; return p

def test_writes_and_replaces(tmp_path):
    f = tmp_path / 'config'
    atomic_write_config(str(f), _parser('1'))
    atomic_write_config(str(f), _parser('2'))
    assert ConfigObj(str(f))['global_config']['k'] == '2'
    assert [x.name for x in tmp_path.iterdir()] == ['config']

def test_preserves_symlink_and_mode(tmp_path):
    real = tmp_path / 'dot' ; real.mkdir()
    target = real / 'config'; target.write_text('[global_config]\n')
    os.chmod(target, 0o600)
    link = tmp_path / 'config'; link.symlink_to(target)
    atomic_write_config(str(link), _parser('x'))
    assert link.is_symlink()
    assert ConfigObj(str(target))['global_config']['k'] == 'x'
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600

def test_failure_keeps_old(tmp_path):
    f = tmp_path / 'config'
    atomic_write_config(str(f), _parser('old'))
    class Bad:
        def write(self, fh):
            fh.write(b'[glob'); raise RuntimeError('boom')
    try:
        atomic_write_config(str(f), Bad())
    except RuntimeError:
        pass
    assert ConfigObj(str(f))['global_config']['k'] == 'old'
    assert [x.name for x in tmp_path.iterdir()] == ['config']
