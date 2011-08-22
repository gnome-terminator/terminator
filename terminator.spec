%{!?python_sitelib: %define python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Name:           terminator
Version:        0.95
Release:        1%{?dist}
Summary:        Store and run multiple GNOME terminals in one window

Group:          User Interface/Desktops
License:        GPLv2
URL:            http://www.tenshu.net/terminator
Source0:        http://code.launchpad.net/terminator/trunk/%{version}/+download/terminator_%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

BuildArch:      noarch
BuildRequires:  python-devel gettext desktop-file-utils intltool
Requires:       vte gnome-python2-gconf GConf2 gtk2 desktop-file-utils

%description
Multiple GNOME terminals in one window.  This is a project to produce
an efficient way of filling a large area of screen space with
terminals. This is done by splitting the window into a resizeable
grid of terminals. As such, you can  produce a very flexible
arrangements of terminals for different tasks.


%prep
%setup -q
sed -i '/#! \?\/usr.*/d' terminatorlib/*.py


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
%{python_sitelib}/*
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/*/%{name}*.png
%{_datadir}/icons/hicolor/*/*/%{name}*.svg
%{_datadir}/icons/hicolor/16x16/status/terminal-bell.png
%{_datadir}/pixmaps/%{name}.png


%post
gtk-update-icon-cache -qf %{_datadir}/icons/hicolor &>/dev/null || :


%postun
gtk-update-icon-cache -qf %{_datadir}/icons/hicolor &>/dev/null || :


%changelog
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
