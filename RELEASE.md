Releasing Terminator
====================

Make sure you have the latest master branch, no un-committed changes, and are ready to release that state.

```
VERSION=1.92
```

## Set version in Python

```
sed -i "s/APP_VERSION =.*/APP_VERSION = '${VERSION}'/" terminatorlib/version.py
sed -i -e "s/@@VERSION@@/${VERSION}/" terminatorlib/preferences.glade
```

## Generate the changelog

For the changelog we are using [github-changelog-generator](https://github.com/github-changelog-generator/github-changelog-generator)

```
github_changelog_generator --future-release "v$VERSION"
# Fix CHANGELOG CRLF
dos2unix CHANGELOG.md
```

Check and review CHANGELOG.md for the expected result.

## Review and update translations

Check for open pull-requests by Transifex or pull the files manually.

See [TRANSLATION](TRANSLATION.md).

## Update AUTHORS

This will make sure we mention everyone that has contributed to Terminator.

```
git log --use-mailmap | grep ^Author: | cut -f2- -d' ' | grep -v ^Launchpad | sort | uniq | sed 's/^/* /' | cat .authors.header - .authors.footer > AUTHORS
```

Make sure to review the list, and update `.mailmap` when it is necessary.

## Git Tag

Commit these changes to the "master" branch:

```
git add terminatorlib/version.py CHANGELOG.md RELEASE.md
git commit -v -m "Release version $VERSION"
git push origin master
```

And tag it with a signed tag:

```
git tag -s -m "Version $VERSION" v$VERSION
```

Push the tag.

```
git push --tags
```

## Signed artifacts

To provide a signed tarball for distributions we use sdist and gpg:

```
VERSION=$(git describe --tags | sed s/^v//)
GPGKEY=$(git config --get user.email)

mkdir -p dist

git archive HEAD --prefix terminator-${VERSION}/ -o dist/terminator-${VERSION}.tar.gz

gpg -u ${GPGKEY} --armor \
  --output dist/terminator-${VERSION}.tar.gz.asc \
  --detach-sig dist/terminator-${VERSION}.tar.gz
```

## GitHub Release

Now update the tag to a release on GitHub, and add the artifacts:
https://github.com/gnome-terminator/terminator/releases

Make sure to add the proper section from CHANGELOG.md as description to the release.
