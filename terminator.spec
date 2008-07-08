Summary: Terminator, The robot future of terminals
Name: terminator
Version: 0.9
Release: 1.fc9.rb
License: GPLv2+
Group: Terminals
URL: http://www.tenshu.net/terminator/

Source: http://code.launchpad.net/terminator/trunk/%{version}/+download/terminator_%{version}.tar.gz
BuildRoot: %{_tmppath}/%{name}-%{version}-%{release}-root
BuildArch: noarch
BuildRequires: python-devel
Requires: vte, gnome-python2-gconf, GConf2
Packager: Emmanuel Bretelle <chantra AatT rpm-based DdOoTt org>

%description
Multiple GNOME terminals in one window
This is a project to produce an efficient way of filling a
large area of screen space with terminals. This is done by
splitting the window into a resizeable grid of terminals. As
such, you can  produce a very flexible arrangements of terminals
for different tasks.

%prep
%setup -q -n %{name}-%{version}

%build
%__python setup.py build

%install
%__rm -rf %{buildroot}
%__python setup.py install --root=%{buildroot} --record=FILELIST.tmp
grep -v man/man FILELIST.tmp > FILELIST

%clean
%__rm -rf %{buildroot}

%files -f FILELIST
%defattr(-,root,root)
%doc README COPYING ChangeLog
%doc %{_mandir}/man1/terminator.*
%doc %{_mandir}/man5/terminator_config.*

%post
touch --no-create  %{_datadir}/icons/hicolor ||:
gtk-update-icon-cache -q %{_datadir}/icons/hicolor &> /dev/null ||:
update-desktop-database &> /dev/null ||:

%postun
touch --no-create  %{_datadir}/icons/hicolor ||:
gtk-update-icon-cache -q %{_datadir}/icons/hicolor &> /dev/null ||:
update-desktop-database &> /dev/null ||:

%changelog
* Fri Jul 08 2008 - chantra AatT rpm-based DdOoTt org 0.9.fc9.rb
- New upstream release
* Sat May 17 2008 - chantra AatT rpm-based DdOoTt org 0.8.1.fc9.rb
- Initial release for Fedora 9.
