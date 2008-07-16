#!/usr/bin/env python

from distutils.core import setup
from distutils.dist import Distribution
from distutils.command.install_data import install_data
from distutils.command.build import build
from distutils.dep_util import newer
from distutils.log import info
import glob
import os
import sys
import subprocess
import platform

from terminatorlib.version import *

PO_DIR = 'po'
MO_DIR = os.path.join('build', 'mo')

class TerminatorDist(Distribution):
  global_options = Distribution.global_options + [
    ("without-gettext", None, "Don't build/install gettext .mo files")]

  def __init__ (self, *args):
    self.without_gettext = False
    Distribution.__init__(self, *args)


class BuildData(build):
  def run (self):
    build.run (self)

    if self.distribution.without_gettext:
      return

    for po in glob.glob (os.path.join (PO_DIR, '*.po')):
      lang = os.path.basename(po[:-3])
      mo = os.path.join(MO_DIR, lang, 'terminator.mo')

      directory = os.path.dirname(mo)
      if not os.path.exists(directory):
        info('creating %s' % directory)
        os.makedirs(directory)

      if newer(po, mo):
        info('compiling %s -> %s' % (po, mo))
        try:
          rc = subprocess.call(['msgfmt', '-o', mo, po])
          if rc != 0:
            raise Warning, "msgfmt returned %d" % rc
        except Exception, e:
          print "Building gettext files failed.  Try setup.py --without-gettext [build|install]"
          print "%s: %s" % (type(e), e)
          sys.exit(1)


class InstallData(install_data):
  def run (self):
    self.data_files.extend (self._find_mo_files ())
    install_data.run (self)


  def _find_mo_files (self):
    data_files = []

    if not self.distribution.without_gettext:
      for mo in glob.glob (os.path.join (MO_DIR, '*', 'terminator.mo')):
       lang = os.path.basename(os.path.dirname(mo))
       dest = os.path.join('share', 'locale', lang, 'LC_MESSAGES')
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
      cmdclass={'build': BuildData, 'install_data': InstallData},
      distclass=TerminatorDist
     )

