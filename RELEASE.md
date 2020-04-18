Releasing Terminator
====================

Make sure you have the latest master branch, no un-committed changes, and are ready to release that state.

```
VERSION=1.92
```

## Set version in Python

```
sed -i "s/APP_VERSION =.*/APP_VERSION = '${VERSION}'/" terminatorlib/version.py
```

## Generate the changelog

For the changelog we are using [github-changelog-generator](https://github.com/github-changelog-generator/github-changelog-generator)

```
github_changelog_generator --future-release "v$VERSION"
```

Check and review CHANGELOG.md for the expected result.

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
python setup.py sdist
gpg -u markus@lazyfrosch.de --armor \
  --output dist/terminator-${VERSION}.tar.gz.asc \
  --detach-sig dist/terminator-${VERSION}.tar.gz
```

## GitHub Release

Now update the tag to a release on GitHub, and add the artifacts:
https://github.com/gnome-terminator/terminator/releases

Make sure to add the proper section from CHANGELOG.md as description to the release.
