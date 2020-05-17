Development Notes
=================

Here we connect notes and howtos for development around Terminator. Feel free to extend or submit suggestions.

## Translation i18n

Tooling is based on [Babel](https://babel.pocoo.org), the configuration is stored in `babel.cfg`, `setup.cfg` and
some code in `setup.py`.

The POT file [po/terminator.pot](po/terminator.pot) contains the template for all translations and should be updated
regularly, especially when messages changed inside the source code.

```
$ python setup.py extract_messages
```

Usually catalogs are updated with external translation tools, e.g. when new translations are merged. But we can update
the catalogs here, so translators will have it more easy to pick up their work.
This is a custom extension in `setup.py`.

```
$ python setup.py update_catalogs
```

Compilation of catalogs into the binary form, from `*.po` to `*.mo` is done during `setup.py build`, and the files are
installed during `setup.py install`.
