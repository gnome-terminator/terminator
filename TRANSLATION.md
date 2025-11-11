# Translation

Terminator has been translated to multiple languages and locales, but there is always
work to do, so everyone is welcome to help and contribute.

You can find all translations under the `po` directory, which will be compiled and
installed with Terminator.

Translations are managed on Transifex [transifex.com/terminator],
anyone is free to join the project and start translating.

You should read the [Getting Started as a Translator] guide.

_Questions or problems?_ Please reach out on [Gitter] or [open an issue].

## Updating POT

The POT file is the template for all translations and is generated from the Python
source code.

    cd po/
    ./genpot.sh
    git diff terminator.pot

To generate and handle POT and PO files, you will need at least `gettext` and `intltool` installed.

Usually the POT file is automatically synced to Transifex, but it can be manually pushed:

    tx push --source

## Updating Translations

Transifex is configured to automatically open a pull-request when a language has been
fully translated. A manual update is always possible and might be useful when preparing
a release.

    tx pull --all

You can also push translations changed outside of Transifex back to the service:

    tx push --translations --language XX
    
## External Documentation

* [Getting Started as a Translator]
* [Transifex CLI Client](https://docs.transifex.com/client/introduction)
* [Documentation Overview](https://docs.transifex.com/)

[Gitter]: https://gitter.im/gnome-terminator/community
[open an issue]: https://github.com/gnome-terminator/terminator/issues/new/choose
[transifex.com/terminator]: https://app.transifex.com/terminator/terminator/dashboard/
[Getting Started as a Translator]: https://docs.transifex.com/getting-started-1/translators
