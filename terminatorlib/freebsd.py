#!/usr/local/bin/python
#
# Use sysctl() to retrieve the cwd of an arbitrary process on FreeBSD.
# Tested on FreeBSD 7-STABLE/amd64 from April 11 2008.
#
# Be prepared for excitement if the structs are changed.
#
# Blame: Thomas Hurst <tom@hur.st>
#

from ctypes import *

# This is padded awkwardly, see /usr/include/sys/socket.h
class sockaddr_storage(Structure):
  _fields_ = [
    ('ss_len',     c_char),
    ('ss_family',  c_char),       # /usr/include/sys/_types.h; _uint8_t
    ('__ss_pad1',  c_char * 6),   # (sizeof(int64) - sizeof(char) - sizeof(ss_family_t))
    ('__ss_align', c_longlong),
    ('__ss_pad2',  c_char * 112), # (128(maxsize) - sizeof(char) - sizeof(ss_family_t) -
                                  # sizeof(ss_pad1) - sizeof(int64))
  ]

# struct kinfo_file, defined in /usr/include/sys/user.h
class kinfo_file(Structure):
  _fields_ = [
      ('kf_structsize',    c_int),
      ('kf_type',          c_int),
      ('kf_fd',            c_int),
      ('kf_ref_count',     c_int),
      ('kf_flags',         c_int),
      ('kf_offset',        c_long), # this is a off_t, a pointer
      ('kf_vnode_type',    c_int),
      ('kf_sock_domain',   c_int),
      ('kf_sock_type',     c_int),
      ('kf_sock_protocol', c_int),
      ('kf_path',          c_char * 1024), # PATH_MAX
      ('kf_sa_local',      sockaddr_storage),
      ('kf_sa_peer',       sockaddr_storage),
  ]

libc = CDLL('libc.so')

len = c_uint(sizeof(c_uint))
ver = c_uint(0)

if (libc.sysctlbyname('kern.osreldate', byref(ver), byref(len), None, 0) < 0):
  raise OSError, "sysctlbyname returned < 0"

# kern.proc.filedesc added for procstat(1) after these __FreeBSD_versions
if ver.value < 700104 and ver.value < 800019:
  raise NotImplementedError, "cwd detection requires a recent 7.0-STABLE or 8-CURRENT"

def get_process_cwd(pid):
  # /usr/include/sys/sysctl.h
  # CTL_KERN, KERN_PROC, KERN_PROC_FILEDESC
  oid = (c_uint * 4)(1, 14, 14, pid)

  if libc.sysctl(oid, 4, None, byref(len), None, 0) < 0:
    return None

  buf = c_char_p(" " * len.value)
  if libc.sysctl(oid, 4, buf, byref(len), None, 0) < 0:
    return None

  kifs = cast(buf, POINTER(kinfo_file))
  for i in range(0, len.value / sizeof(kinfo_file)):
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

