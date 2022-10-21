Installing Terminator
=====================

It's strongly recommended to install Terminator using your OS's package
system rather than using setup.py yourself.

Packages are known to be available under the name "terminator" under a
lot of distributions, see below for a list.

I also maintain a PPA for Ubuntu 20.04 and up that has the latest release
If you're running ubuntu 20.04 or later, you can run 

```
sudo add-apt-repository ppa:mattrose/terminator
sudo apt-get update
sudo apt install terminator
```

## Source Install

If you can't use distribution packages, make sure you satisfy Terminator's
dependencies yourself:

**Python 3.5+ recommended:** `python3` or `python37` (in FreeBSD)

**Python GTK and VTE bindings:**
     
     Fedora/CentOS: python3-gobject python3-configobj python3-psutil vte291 
                    keybinder3 intltool gettext
     Debian/Ubuntu: python3-gi python3-gi-cairo python3-psutil python3-configobj 
                    gir1.2-keybinder-3.0 gir1.2-vte-2.91 gettext intltool dbus-x11 
     FreeBSD:       py37-psutil py37-configobj keybinder-gtk3 py37-gobject3 gettext 
                    intltool libnotify vte3

If you don't care about native language support or icons, Terminator
should run just fine directly from this directory, just:

    python3 terminator --help

And go from there.  Manpages are available in the 'doc' directory.

> **Note:** Currently most distributions use `python3` as binaries for Python 3,
> make sure to update either the shebangs, call the scripts with `python3` or
> use a wrapper script.
>
> Setuptools install will update the scripts with the correct shebang.  

To install properly, run:

    python3 setup.py build
    python3 setup.py install --single-version-externally-managed --record=install-files.txt

See `--help` for an overview of the available options; e.g. `--prefix` to
install to a custom base directory, and `--without-gettext` to avoid
installing natural language support files.

setup.py supports basic uninstallation provided `--record` was used for
installation as above:

    python3 setup.py uninstall --manifest=install-files.txt

Note that uninstall will avoid removing most empty directories so it
won't harm e.g. locale or icon directories which only contain Terminator
data.  It also won't rebuild the icon cache, so you may wish to:

     gtk-update-icon-cache -q -f ${PREFIX}/share/icons/hicolor

Where ${PREFIX} is the base install directory; e.g. /usr/local.

## Distributions

[![Packaging status](https://repology.org/badge/tiny-repos/terminator.svg)](https://repology.org/project/terminator/versions)

If you maintain terminator for an OS other than these, please get in touch
or issue a PR to this file.

Distribution | Contact | Package Info | Source Code | Bug Tracker | 
-------------|---------|-----|-------------|-------------|
ArchLinux    | [@grazzolini] | [archlinux.org] | [git.archlinux.org] | [bugs.archlinux.org]
CentOS EPEL  | [@mattrose], [@dmaphy] |  | [src.fedoraproject.org/branches]
Debian       | [@lazyfrosch] | [tracker.debian.org] | [salsa.debian.org] | [bugs.debian.org]
Fedora       | [@mattrose], [@dmaphy] |  | [src.fedoraproject.org] | [bugzilla.redhat.com]
FreeBSD      |  | [freshports.org] | [svnweb.freebsd.org] | [bugs.freebsd.org]
Gentoo       | [@DarthGandalf] | [packages.gentoo.org] | [gitweb.gentoo.org] | [bugs.gentoo.org]
OpenSUSE     |  | [build.opensuse.org] |
Ubuntu       | copied from Debian | [launchpad.net/ubuntu] | | [bugs.launchpad.net]

[@lazyfrosch]: https://github.com/lazyfrosch
[tracker.debian.org]: https://tracker.debian.org/pkg/terminator
[salsa.debian.org]: https://salsa.debian.org/python-team/applications/terminator
[bugs.debian.org]: https://bugs.debian.org/cgi-bin/pkgreport.cgi?repeatmerged=no&src=terminator

[@mattrose]: https://github.com/mattrose
[@dmaphy]: https://github.com/dmaphy
[src.fedoraproject.org]: https://src.fedoraproject.org/rpms/terminator
[src.fedoraproject.org/branches]: https://src.fedoraproject.org/rpms/terminator/branches
[bugzilla.redhat.com]: https://bugzilla.redhat.com/buglist.cgi?component=terminator&product=Fedora

[launchpad.net/ubuntu]: https://launchpad.net/ubuntu/+source/terminator
[bugs.launchpad.net]: https://bugs.launchpad.net/ubuntu/+source/terminator/+bugs

[@grazzolini]: https://github.com/grazzolini
[archlinux.org]: https://www.archlinux.org/packages/community/any/terminator/
[git.archlinux.org]: https://git.archlinux.org/svntogit/community.git/tree/trunk?h=packages/terminator
[bugs.archlinux.org]: https://bugs.archlinux.org/?project=5&string=terminator

[@DarthGandalf]: https://github.com/DarthGandalf
[packages.gentoo.org]: https://packages.gentoo.org/packages/x11-terms/terminator
[gitweb.gentoo.org]: https://gitweb.gentoo.org/repo/gentoo.git/tree/x11-terms/terminator
[bugs.gentoo.org]: https://bugs.gentoo.org/buglist.cgi?quicksearch=x11-terms%2Fterminator

[build.opensuse.org]: https://build.opensuse.org/package/show/X11:terminals/terminator

[svnweb.freebsd.org]: https://svnweb.freebsd.org/ports/head/x11/terminator
[freshports.org]: https://freshports.org/x11/terminator
[bugs.freebsd.org]: https://bugs.freebsd.org/bugzilla/buglist.cgi?quicksearch=terminator

A more extensive list can be found on Repology:

[![Packaging status](https://repology.org/badge/vertical-allrepos/terminator.svg?columns=3)](https://repology.org/project/terminator/versions)

