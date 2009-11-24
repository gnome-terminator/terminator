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
        Borg.__init__(self)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Required by the borg, but a no-op here"""
        pass

    def make(self, product, *args):
        """Make the requested product"""
        try:
            func = getattr(self, 'make_%s' % product.lower())
        except AttributeError:
            err('Factory::make: requested object does not exist: %s' % product)
            return(None)

        dbg('Factory::make: created a %s' % product)
        return(func(args))

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

