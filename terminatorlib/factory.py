#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""factory.py - Maker of objects"""

from borg import Borg
from util import dbg, err

# pylint: disable-msg=R0201
# pylint: disable-msg=W0613
class Factory(Borg):
    """Definition of a class that makes other classes"""
    def __init__(self):
        """Class initialiser"""
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Required by the borg, but a no-op here"""
        pass

    def isinstance(self, product, classtype):
        """Check if a given product is a particular type of object"""
        types = {'Terminal': 'terminal',
                 'VPaned': 'paned',
                 'HPaned': 'paned',
                 'Paned': 'paned',
                 'Notebook': 'notebook',
                 'Container': 'container',
                 'Window': 'window'}
        if classtype in types.keys():
            # This is quite ugly, but we're importing from the current
            # directory if that makes sense, otherwise falling back to
            # terminatorlib. Someone with real Python skills should fix
            # this to be less insane.
            try:
                module = __import__(types[classtype], None, None, [''])
            except ImportError, ex:
                module = __import__('terminatorlib.%s' % types[classtype],
                    None, None, [''])
            return(isinstance(product, getattr(module, classtype)))
        else:
            err('Factory::isinstance: unknown class type: %s' % classtype)
            return(False)

    def make(self, product, *args):
        """Make the requested product"""
        try:
            func = getattr(self, 'make_%s' % product.lower())
        except AttributeError:
            err('Factory::make: requested object does not exist: %s' % product)
            return(None)

        dbg('Factory::make: created a %s' % product)
        return(func(args))

    def make_window(self, *args):
        """Make a Window"""
        import window
        return(window.Window())

    def make_terminal(self, *args):
        """Make a Terminal"""
        import terminal
        return(terminal.Terminal())

    def make_hpaned(self, *args):
        """Make an HPaned"""
        import paned
        return(paned.HPaned())

    def make_vpaned(self, *args):
        """Make a VPaned"""
        import paned
        return(paned.VPaned())

    def make_notebook(self, *args):
        """Make a Notebook"""
        import notebook
        return(notebook.Notebook(args[0][0]))

