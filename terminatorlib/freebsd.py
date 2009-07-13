#!/usr/bin/python
#
# Copyright (c) 2008, Thomas Hurst <tom@hur.st>
#
# Use of this file is unrestricted provided this notice is retained.
# If you use it, it'd be nice if you dropped me a note.  Also beer.

"""
 freebsd.get_process_cwd(pid):
  Use sysctl() to retrieve the cwd of an arbitrary process on FreeBSD
  using kern.proc.filedesc, as used by procstat(1).
  Tested on FreeBSD 7-STABLE/amd64 from April 11 2008.
"""

from ctypes import *

class sockaddr_storage(Structure):
  """struct sockaddr_storage, defined in /usr/include/sys/socket.h"""
  _fields_ = [
    ('ss_len',     c_char),
    ('ss_family',  c_char),       # /usr/include/sys/_types.h; _uint8_t
    ('__ss_pad1',  c_char * 6),   # (sizeof(int64) - sizeof(char) - sizeof(ss_family_t))
    ('__ss_align', c_longlong),
    ('__ss_pad2',  c_char * 112), # (128(maxsize) - sizeof(char) - sizeof(ss_family_t) -
                                  # sizeof(ss_pad1) - sizeof(int64))
  ]

class kinfo_file(Structure):
  """struct kinfo_file, defined in /usr/include/sys/user.h """
  _fields_ = [
      ('kf_structsize',    c_int),
      ('kf_type',          c_int),
      ('kf_fd',            c_int),
      ('kf_ref_count',     c_int),
      ('kf_flags',         c_int),
      ('kf_offset',        c_size_t), # this is a off_t, a pointer
      ('kf_vnode_type',    c_int),
      ('kf_sock_domain',   c_int),
      ('kf_sock_type',     c_int),
      ('kf_sock_protocol', c_int),
      ('kf_path',          c_char * 1024), # PATH_MAX
      ('kf_sa_local',      sockaddr_storage),
      ('kf_sa_peer',       sockaddr_storage),
  ]

libc = CDLL('libc.so')

uintlen = c_size_t(sizeof(c_uint))
ver = c_uint(0)

if (libc.sysctlbyname('kern.osreldate', byref(ver), byref(uintlen), None, 0) < 0):
  raise OSError, "sysctlbyname returned < 0"

# kern.proc.filedesc added for procstat(1) after these __FreeBSD_versions
if ver.value < 700104 and ver.value < 800019:
  raise NotImplementedError, "cwd detection requires a recent 7.0-STABLE or 8-CURRENT"


def get_process_cwd(pid):
  """Return string containing the current working directory of the given pid,
     or None on failure."""
  # /usr/include/sys/sysctl.h
  # CTL_KERN, KERN_PROC, KERN_PROC_FILEDESC
  oid = (c_uint * 4)(1, 14, 14, pid)

  if libc.sysctl(oid, 4, None, byref(uintlen), None, 0) < 0:
    return None

  buf = c_char_p(" " * uintlen.value)
  if libc.sysctl(oid, 4, buf, byref(uintlen), None, 0) < 0:
    return None

  kifs = cast(buf, POINTER(kinfo_file))
  for i in xrange(0, uintlen.value / sizeof(kinfo_file)):
    kif = kifs[i]
    if kif.kf_fd == -1: # KF_FD_TYPE_CWD
      return kif.kf_path


if __name__ == '__main__':
  import os, sys
  print " => %d cwd = %s" % (os.getpid(), get_process_cwd(os.getpid()))
  for pid in sys.argv:
    try:
      pid = int(pid)
    except:
      pass
    else:
      print " => %d cwd = %s" % (pid, get_process_cwd(pid))

