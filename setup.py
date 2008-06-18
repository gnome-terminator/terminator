#!/usr/bin/env python

from distutils.core import setup
from distutils.command.install_data import install_data
from distutils.command.build import build
from distutils.dep_util import newer
from distutils.log import info
import glob
import os
import sys
import platform

from terminatorlib.version import *

PO_DIR = 'po'
MO_DIR = os.path.join('build', 'mo')
WITHOUT_NLS = sys.platform == 'win32' or os.environ.has_key("WITHOUT_NLS")

class BuildData(build):
  def run (self):
    build.run (self)

    if WITHOUT_NLS:
      return

    for po in glob.glob (os.path.join (PO_DIR, '*.po')):
      lang = os.path.basename(po[:-3])
      mo = os.path.join(MO_DIR, lang + '.mo')

      directory = os.path.dirname(mo)
      if not os.path.exists(directory):
        info('creating %s' % directory)
        os.makedirs(directory)

      if newer(po, mo):
        cmd = 'msgfmt -o %s %s' % (mo, po)
        info('compiling %s -> %s' % (po, mo))
        os.system(cmd)


class InstallData(install_data):
  def run (self):
    self.data_files.extend (self._compile_po_files ())
    install_data.run (self)

  def _compile_po_files (self):
    data_files = []

    if WITHOUT_NLS:
      return data_files

    for mo in glob.glob (os.path.join (MO_DIR, '*.mo')):
      lang = os.path.basename(mo[:-3])
      dest = os.path.dirname(os.path.join('share', 'locale', lang, 'LC_MESSAGES', 'terminator.mo'))
      data_files.append((dest, [mo]))

    return data_files


if platform.system() == 'FreeBSD':
  man_dir = 'man'
else:
  man_dir = 'share/man'

setup(name='Terminator',
      version=APP_VERSION,
      description='Terminator, the robot future of terminals',
      author='Chris Jones',
      author_email='cmsj@tenshu.net',
      url='http://www.tenshu.net/terminator/',
      license='GNU GPL v2',
      scripts=['terminator'],
      data_files=[
                  ('share/applications', ['data/terminator.desktop']),
                  (os.path.join(man_dir, 'man1'), ['doc/terminator.1']),
                  (os.path.join(man_dir, 'man5'), ['doc/terminator_config.5']),
                  ('share/pixmaps', ['data/icons/48x48/apps/terminator.png']),
                  ('share/icons/hicolor/scalable/apps', glob.glob('data/icons/scalable/apps/*.svg')),
                  ('share/icons/hicolor/16x16/apps', glob.glob('data/icons/16x16/apps/*.png')),
                  ('share/icons/hicolor/22x22/apps', glob.glob('data/icons/22x22/apps/*.png')),
                  ('share/icons/hicolor/24x24/apps', glob.glob('data/icons/24x24/apps/*.png')),
                  ('share/icons/hicolor/48x48/apps', glob.glob('data/icons/48x48/apps/*.png')),
                  ('share/icons/hicolor/16x16/actions', glob.glob('data/icons/16x16/actions/*.png')),
                 ],
      packages=['terminatorlib'],
      cmdclass={'build': BuildData, 'install_data': InstallData}
     )

