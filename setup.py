#!/usr/bin/env python

from distutils.core import setup
from distutils.command.install_data import install_data
from distutils.command.build import build
from distutils.dep_util import newer
from distutils.log import info
import glob
import os
import sys

def import_terminator():
  from types import ModuleType
  module = ModuleType('terminator')
  module_file = open('terminator', 'r')
  exec module_file in module.__dict__
  return module

APP_VERSION = import_terminator().APP_VERSION

PO_DIR = 'po'
MO_DIR = os.path.join('build', 'mo')

class BuildData(build):
  def run (self):
    build.run (self)

    if sys.platform == 'win32':
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
        if os.system(cmd) != 0:
          raise SystemExit('Error while running msgfmt')


class InstallData(install_data):
  def run (self):
    self.data_files.extend (self._compile_po_files ())
    install_data.run (self)

  def _compile_po_files (self):
    data_files = []

    # Don't install language files on win32
    if sys.platform == 'win32':
      return data_files

    for mo in glob.glob (os.path.join (MO_DIR, '*.mo')):
      lang = os.path.basename(mo[:-3])
      dest = os.path.dirname(os.path.join('share', 'locale', lang, 'LC_MESSAGES', 'terminator.mo'))
      data_files.append((dest, [mo]))

    return data_files


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
                  ('share/man/man1', ['doc/terminator.1']),
                  ('share/man/man5', ['doc/terminatorrc.5']),
                  ('share/pixmaps', ['data/icons/48x48/apps/terminator.png']),
                  ('share/icons/hicolor/scalable/apps', glob.glob('data/icons/scalable/apps/*.svg')),
                  ('share/icons/hicolor/16x16/apps', glob.glob('data/icons/16x16/apps/*.png')),
                  ('share/icons/hicolor/22x22/apps', glob.glob('data/icons/22x22/apps/*.png')),
                  ('share/icons/hicolor/24x24/apps', glob.glob('data/icons/24x24/apps/*.png')),
                  ('share/icons/hicolor/48x48/apps', glob.glob('data/icons/48x48/apps/*.png')),
                 ],
      py_modules=['terminatorconfig'],
      cmdclass={'build': BuildData, 'install_data': InstallData}
     )

