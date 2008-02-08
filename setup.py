#!/usr/bin/env python

from distutils.core import setup
from distutils.command.install_data import install_data
from distutils.dep_util import newer
from distutils.log import info
import glob
import os
import sys

class InstallData(install_data):
  def run (self):
    self.data_files.extend (self._compile_po_files ())
    install_data.run (self)

  def _compile_po_files (self):
    data_files = []

    # Don't install language files on win32
    if sys.platform == 'win32':
      return data_files

    PO_DIR = 'po'
    for po in glob.glob (os.path.join (PO_DIR,'*.po')):
      lang = os.path.basename(po[:-3])
      mo = os.path.join('build', 'mo', lang, 'terminator.mo')

      directory = os.path.dirname(mo)
      if not os.path.exists(directory):
        info('creating %s' % directory)
        os.makedirs(directory)

      if newer(po, mo):
        # True if mo doesn't exist
        cmd = 'msgfmt -o %s %s' % (mo, po)
        info('compiling %s -> %s' % (po, mo))
        if os.system(cmd) != 0:
          raise SystemExit('Error while running msgfmt')

        dest = os.path.dirname(os.path.join('share', 'locale', lang, 'LC_MESSAGES', 'terminator.mo'))
        data_files.append((dest, [mo]))

    return data_files


setup(name='Terminator',
      version='0.7.1',
      description='Terminator, the robot future of terminals',
      author='Chris Jones',
      author_email='cmsj@tenshu.net',
      url='http://www.tenshu.net/terminator/',
      license='GPL v2',
      scripts=['terminator'],
      data_files=[
                  ('share/applications', ['terminator.desktop']),
                  ('share/man/man1', ['doc/terminator.1']),
                  ('share/pixmaps', ['data/icons/48x48/apps/terminator.png']),
                  ('share/icons/hicolor/scalable/apps', glob.glob('data/icons/scalable/apps/*.svg')),
                  ('share/icons/hicolor/16x16/apps', glob.glob('data/icons/16x16/apps/*.png')),
                  ('share/icons/hicolor/22x22/apps', glob.glob('data/icons/22x22/apps/*.png')),
                  ('share/icons/hicolor/24x24/apps', glob.glob('data/icons/24x24/apps/*.png')),
                  ('share/icons/hicolor/48x48/apps', glob.glob('data/icons/48x48/apps/*.png')),
                 ],
      cmdclass={'install_data': InstallData}
     )

