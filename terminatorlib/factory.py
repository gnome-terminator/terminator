#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""factory.py - Maker of objects

>>> maker = Factory()
>>> window = maker.make_window()
>>> maker.isinstance(window, 'Window')
True
>>> terminal = maker.make_terminal()
>>> maker.isinstance(terminal, 'Terminal')
True
>>> hpaned = maker.make_hpaned()
>>> maker.isinstance(hpaned, 'HPaned')
True
>>> vpaned = maker.make_vpaned()
>>> maker.isinstance(vpaned, 'VPaned')
True

"""

from borg import Borg
from util import dbg, err, inject_uuid

# pylint: disable-msg=R0201
# pylint: disable-msg=W0613
class Factory(Borg):
    """Definition of a class that makes other classes"""
    types = {'Terminal': 'terminal',
             'VPaned': 'paned',
             'HPaned': 'paned',
             'Paned': 'paned',
             'Notebook': 'notebook',
             'Container': 'container',
             'Window': 'window'}
    types_keys = types.keys()
    instance_types = {}
    instance_types_keys = []

    def __init__(self):
        """Class initialiser"""
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Required by the borg, but a no-op here"""
        pass

    def isinstance(self, product, classtype):
        """Check if a given product is a particular type of object"""
        if classtype in self.types_keys:
            # This is now very ugly, but now it's fast :-)
            # Someone with real Python skills should fix this to be less insane.
            # Optimisations:
            # - swap order of imports, otherwise we throw ImportError
            #   almost every time
            # - cache everything we can
            try:
                type_key = 'terminatorlib.%s' % self.types[classtype]
                if type_key not in self.instance_types_keys:
                    self.instance_types[type_key] = __import__(type_key, None, None, [''])
                    self.instance_types_keys.append(type_key)
                module = self.instance_types[type_key]
            except ImportError:
                type_key = self.types[classtype]
                if type_key not in self.instance_types_keys:
                    self.instance_types[type_key] = __import__(type_key, None, None, [''])
                    self.instance_types_keys.append(type_key)
                module = self.instance_types[type_key]
            return(isinstance(product, getattr(module, classtype)))
        else:
            err('Factory::isinstance: unknown class type: %s' % classtype)
            return(False)

    def type(self, product):
        """Determine the type of an object we've previously created"""
        for atype in self.types:
            # Skip over generic types
            if atype in ['Container', 'Paned']:
                continue
            if self.isinstance(product, atype):
                return(atype)
        return(None)

    def make(self, product, **kwargs):
        """Make the requested product"""
        try:
            func = getattr(self, 'make_%s' % product.lower())
        except AttributeError:
            err('Factory::make: requested object does not exist: %s' % product)
            return(None)

        dbg('Factory::make: created a %s' % product)
        output = func(**kwargs)
        inject_uuid(output)
        return(output)

    def make_window(self, **kwargs):
        """Make a Window"""
        import window
        return(window.Window(**kwargs))

    def make_terminal(self, **kwargs):
        """Make a Terminal"""
        import terminal
        return(terminal.Terminal())

    def make_hpaned(self, **kwargs):
        """Make an HPaned"""
        import paned
        return(paned.HPaned())

    def make_vpaned(self, **kwargs):
        """Make a VPaned"""
        import paned
        return(paned.VPaned())

    def make_notebook(self, **kwargs):
        """Make a Notebook"""
        import notebook
        return(notebook.Notebook(kwargs['window']))

