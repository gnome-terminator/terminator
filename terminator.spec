Name:           terminator
Version:        1.91
Release:        1%{?dist}
Summary:        Store and run multiple GNOME terminals in one window

Group:          User Interface/Desktops
License:        GPLv2
URL:            https://gnometerminator.blogspot.com/p/introduction.html
Source:         http://code.launchpad.net/terminator/gtk3/1.9/+download/terminator-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python-devel gettext desktop-file-utils intltool
Requires:       vte291 python-psutil python-gobject keybinder3 desktop-file-utils

%description
Multiple GNOME terminals in one window.  This is a project to produce
an efficient way of filling a large area of screen space with
terminals. This is done by splitting the window into a resizeable
grid of terminals. As such, you can  produce a very flexible
arrangements of terminals for different tasks.


%prep
%setup -q
sed -i '/#! \?\/usr.*/d' terminatorlib/*.py
%patch -p1


%build
%{__python} setup.py build


%install
rm -rf %{buildroot}
%{__python} setup.py install -O1 --skip-build --root %{buildroot}
%find_lang %{name}
rm -f %{buildroot}/%{_datadir}/icons/hicolor/icon-theme.cache
rm -f %{buildroot}/%{_datadir}/applications/%{name}.desktop
desktop-file-install --dir=${RPM_BUILD_ROOT}%{_datadir}/applications data/%{name}.desktop


%clean
rm -rf %{buildroot}


%files -f %{name}.lang
%defattr(-,root,root)
%doc README COPYING ChangeLog
%{_mandir}/man1/%{name}.*
%{_mandir}/man5/%{name}_config.*
%{_bindir}/%{name}
%{_bindir}/remotinator
%{_bindir}/terminator.wrapper
%{python_sitelib}/*
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/*/%{name}*.png
%{_datadir}/icons/hicolor/*/*/%{name}*.svg
%{_datadir}/icons/hicolor/16x16/status/terminal-bell.png
%{_datadir}/pixmaps/%{name}.png
%{_datadir}/icons/HighContrast/*/*/%{name}*.png
%{_datadir}/icons/HighContrast/*/*/%{name}*.svg
%{_datadir}/icons/HighContrast/16x16/status/terminal-bell.png
%{_datadir}/appdata/terminator.appdata.xml

%post
gtk-update-icon-cache -qf %{_datadir}/icons/hicolor &>/dev/null || :
gtk-update-icon-cache -qf %{_datadir}/icons/HighContrast &>/dev/null || :


%postun
gtk-update-icon-cache -qf %{_datadir}/icons/hicolor &>/dev/null || :
gtk-update-icon-cache -qf %{_datadir}/icons/HighContrast &>/dev/null || :

%changelog
* Thu Nov 24 2016 Steve Boddy <stephen.j.boddy@gmail.com> 1.90-1
- Update for gtk3 release using the specfile provided
  by Matt Rose.
    Note that this specfile is untested.

* Mon Aug 22 2011 Chris Jones <cmsj@tenshu.net> 0.96-1
- Update for modern release to fix various build issues
  by borrowing the specfile that Fedora uses
    Note that this specfile is untested.

* Wed Mar 31 2010 Chris Jones <cmsj@tenshu.net> 0.91-1
- Update to fix some stupid release bugs in 0.90.
    Note that this specfile is untested.

* Tue Jan 05 2010 Chris Jones <cmsj@tenshu.net> 0.90-1
- Attempt to update for 0.90 pre-release.
    Note that this specfile is untested.

* Thu Jan 15 2009 Chris Jones <cmsj@tenshu.net> 0.12-1
- Remove patch application since this isn't a fedora build.
    Note that this specfile is untested.

* Mon Dec 08 2008 Ian Weller <ianweller@gmail.com> 0.11-3
- Patch version in terminatorlib/verison.py to the one we think it is
- Fix License tag
- Update post and postun scripts with one line

* Mon Dec 01 2008 Ian Weller <ianweller@gmail.com> 0.11-2
- Add BuildRequires: gettext
- Fix installation of .desktop file
- terminator-0.11-desktop.patch:
    Remove useless things
    Move to same category as gnome-terminal
- Uses spaces instead of tabs in the specfile because I can't stand tabs

* Mon Dec 01 2008 Ian Weller <ianweller@gmail.com> 0.11-1
- Update upstream
- Fix description to something useful
- Fix group
- Fix some specfile oddities
- Complete/restandardize file list
- Get rid of she-bangs in python_sitelib

* Sat Sep 13 2008 - Max Spevack <mspevack AT redhat DOT com> 0.10
- New upstream release.
- Tried to make sure the spec file matches guidelines on Fedora wiki.

* Fri Jul 08 2008 - chantra AatT rpm-based DdOoTt org 0.9.fc9.rb
- New upstream release

* Sat May 17 2008 - chantra AatT rpm-based DdOoTt org 0.8.1.fc9.rb
- Initial release for Fedora 9.
