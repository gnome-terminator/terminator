#!/usr/bin/env python

from distutils.core import setup

setup(name='Terminator',
      version='0.6',
      description='Terminator, the robot future of terminals',
      author='Chris Jones',
      author_email='cmsj@tenshu.net',
      url='http://www.tenshu.net/terminator/',
      license='GPL v2',
      scripts=['terminator'],
      data_files=[
                  ('share/applications', ['terminator.desktop']),
                 ],
     )

