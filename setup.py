#!/usr/bin/env python

from setuptools import setup, Distribution, Command

from distutils.command.install_data import install_data
from distutils.command.build import build
from distutils.dep_util import newer
from distutils.log import warn, info, error
from distutils.errors import DistutilsFileError

import glob
import os
import sys
import subprocess
import platform

from terminatorlib.version import APP_NAME, APP_VERSION

GETTEXT_SOURCE = 'po'
GETTEXT_DOMAIN = 'terminator'
GETTEXT_TARGET = os.path.join('share', 'locale')
CSS_DIR = os.path.join('terminatorlib', 'themes')

if sys.version_info < (3, 0):
    PYTEST_VERSION = '<5'
    BABELGLADE_VERSION = '< 0.7'
else:
    PYTEST_VERSION = '>0'
    BABELGLADE_VERSION = '> 0'


class TerminatorDist(Distribution):
  global_options = Distribution.global_options + [
    ("build-documentation", None, "Build the documentation"),
    ("install-documentation", None, "Install the documentation"),
    ("without-icon-cache", None, "Don't attempt to run gtk-update-icon-cache")]

  def __init__ (self, *args):
    self.without_icon_cache = False
    Distribution.__init__(self, *args)


class CustomBuild(build):
    """
    Custom build extensions to build
    """

    def run(self):
        build.run(self)
        self.build_i18n()

    def build_i18n(self):
        """
        Compiling files for gettext from *.po to *.mo with the proper target path
        """
        info('compiling i18n files')
        from babel.messages.frontend import compile_catalog
        compiler = compile_catalog(self.distribution)
        compiler.domain = [GETTEXT_DOMAIN]

        for po in glob.glob(os.path.join(GETTEXT_SOURCE, '*.po')):
            lang = os.path.basename(po[:-3])
            mo = os.path.join(self.build_base, GETTEXT_TARGET, lang, 'LC_MESSAGES', 'terminator.mo')

            directory = os.path.dirname(mo)
            if not os.path.exists(directory):
                os.makedirs(directory)

            if newer(po, mo):
                compiler.input_file = po
                compiler.output_file = mo
                compiler.run()


class Uninstall(Command):
  description = "Attempt an uninstall from an install --record file"

  user_options = [('manifest=', None, 'Installation record filename')]

  def initialize_options(self):
    self.manifest = None

  def finalize_options(self):
    pass

  def get_command_name(self):
    return 'uninstall'

  def run(self):
    f = None
    self.ensure_filename('manifest')
    try:
      try:
        if not self.manifest:
            raise DistutilsFileError("Pass manifest with --manifest=file")
        f = open(self.manifest)
        files = [file.strip() for file in f]
      except IOError as e:
        raise DistutilsFileError("unable to open install manifest: %s", str(e))
    finally:
      if f:
        f.close()

    for file in files:
      if os.path.isfile(file) or os.path.islink(file):
        info("removing %s" % repr(file))
        if not self.dry_run:
          try:
            os.unlink(file)
          except OSError as e:
            warn("could not delete: %s" % repr(file))
      elif not os.path.isdir(file):
        info("skipping %s" % repr(file))

    dirs = set()
    for file in reversed(sorted(files)):
      dir = os.path.dirname(file)
      if dir not in dirs and os.path.isdir(dir) and len(os.listdir(dir)) == 0:
        dirs.add(dir)
        # Only nuke empty Python library directories, else we could destroy
        # e.g. locale directories we're the only app with a .mo installed for.
        if dir.find("site-packages/") > 0:
          info("removing %s" % repr(dir))
          if not self.dry_run:
            try:
              os.rmdir(dir)
            except OSError as e:
              warn("could not remove directory: %s" % str(e))
        else:
          info("skipping empty directory %s" % repr(dir))


class InstallData(install_data):
  def run (self):
    self.data_files.extend (self._find_css_files ())
    self.data_files.extend(self._find_mo_files())
    install_data.run (self)
    if not self.distribution.without_icon_cache:
      self._update_icon_cache ()

  # We should do this on uninstall too
  def _update_icon_cache(self):
    info("running gtk-update-icon-cache")
    try:
      subprocess.call(["gtk-update-icon-cache", "-q", "-f", "-t", os.path.join(self.install_dir, "share/icons/hicolor")])
    except Exception as e:
      warn("updating the GTK icon cache failed: %s" % str(e))

  def _find_mo_files(self):
    """
    search for gettext files built during build step
    """
    data_files = []

    build_base = self.distribution.command_obj['build'].build_base
    for mo in glob.glob(os.path.join(build_base, GETTEXT_TARGET, '*', 'LC_MESSAGES', '*.mo')):
        dest = mo.lstrip(build_base + os.sep)
        data_files.append((dest, [mo]))

    return data_files

  def _find_css_files (self):
    data_files = []

    for css_dir in glob.glob (os.path.join (CSS_DIR, '*')):
       srce = glob.glob (os.path.join(css_dir, 'gtk-3.0', 'apps', '*.css'))
       dest = os.path.join('share', 'terminator', css_dir, 'gtk-3.0', 'apps')
       data_files.append((dest, srce))

    return data_files


class UpdateCatalogs(Command):
    """Update all gettext catalogs """
    description = __doc__
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        from babel.messages.frontend import update_catalog
        updater = update_catalog(self.distribution)
        updater.input_file = os.path.join(GETTEXT_SOURCE, 'terminator.pot')

        for po in glob.glob(os.path.join(GETTEXT_SOURCE, '*.po')):
            updater.output_file = po
            updater.run()


if platform.system() in ['FreeBSD', 'OpenBSD']:
  man_dir = 'man'
else:
  man_dir = 'share/man'

test_deps = [
    'pytest'
]

setup(name=APP_NAME,
      version=APP_VERSION,
      description='Terminator, the robot future of terminals',
      author='Chris Jones',
      author_email='cmsj@tenshu.net',
      url='https://github.com/gnome-terminator/terminator',
      license='GNU GPL v2',
      scripts=['terminator', 'remotinator'],
      data_files=[
                  ('share/applications', ['data/terminator.desktop']),
                  ('share/metainfo', ['data/terminator.metainfo.xml']),
                  (os.path.join(man_dir, 'man1'), ['doc/terminator.1']),
                  (os.path.join(man_dir, 'man5'), ['doc/terminator_config.5']),
                  ('share/pixmaps', ['data/icons/hicolor/48x48/apps/terminator.png']),
                  ('share/icons/hicolor/scalable/apps', glob.glob('data/icons/hicolor/scalable/apps/*.svg')),
                  ('share/icons/hicolor/16x16/apps', glob.glob('data/icons/hicolor/16x16/apps/*.png')),
                  ('share/icons/hicolor/22x22/apps', glob.glob('data/icons/hicolor/22x22/apps/*.png')),
                  ('share/icons/hicolor/24x24/apps', glob.glob('data/icons/hicolor/24x24/apps/*.png')),
                  ('share/icons/hicolor/32x32/apps', glob.glob('data/icons/hicolor/32x32/apps/*.png')),
                  ('share/icons/hicolor/48x48/apps', glob.glob('data/icons/hicolor/48x48/apps/*.png')),
                  ('share/icons/hicolor/16x16/actions', glob.glob('data/icons/hicolor/16x16/actions/*.png')),
                  ('share/icons/hicolor/16x16/status', glob.glob('data/icons/hicolor/16x16/status/*.png')),
                  ('share/icons/HighContrast/scalable/apps', glob.glob('data/icons/HighContrast/scalable/apps/*.svg')),
                  ('share/icons/HighContrast/16x16/apps', glob.glob('data/icons/HighContrast/16x16/apps/*.png')),
                  ('share/icons/HighContrast/22x22/apps', glob.glob('data/icons/HighContrast/22x22/apps/*.png')),
                  ('share/icons/HighContrast/24x24/apps', glob.glob('data/icons/HighContrast/24x24/apps/*.png')),
                  ('share/icons/HighContrast/32x32/apps', glob.glob('data/icons/HighContrast/32x32/apps/*.png')),
                  ('share/icons/HighContrast/48x48/apps', glob.glob('data/icons/HighContrast/48x48/apps/*.png')),
                  ('share/icons/HighContrast/16x16/actions', glob.glob('data/icons/HighContrast/16x16/actions/*.png')),
                  ('share/icons/HighContrast/16x16/status', glob.glob('data/icons/HighContrast/16x16/status/*.png')),
                 ],
      packages=[
          'terminatorlib',
          'terminatorlib.plugins',
      ],
      setup_requires=[
          'pytest-runner',
          'babel',
          'BabelGladeExtractor ' + BABELGLADE_VERSION,
      ],
      install_requires=[
          'pycairo',
          'configobj',
          'dbus-python',
          'pygobject',
          'psutil',
      ],
      tests_require=test_deps,
      extras_require={'test': test_deps},
      package_data={'terminatorlib': ['preferences.glade', 'layoutlauncher.glade']},
      cmdclass={'build': CustomBuild, 'install_data': InstallData, 'uninstall': Uninstall},
      distclass=TerminatorDist)

