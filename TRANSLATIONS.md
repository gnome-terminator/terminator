### Translating Terminator into your language

Localized strings are available in po/<locale>.po.  These files are compiled
into .mo files by running `python setup.py build`

If you've added a new localized string to the source code, it needs to be
extracted to `po/terminator.pot` by running `python setup.py extract_messages`
