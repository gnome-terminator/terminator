# Copyright (c) 2008, Thomas Hurst <tom@hur.st>
#
# Use of this file is unrestricted provided this notice is retained.
# If you use it, it'd be nice if you dropped me a note.  Also beer.

from terminatorlib.util import dbg, err, get_cache_dir
from terminatorlib.version import APP_NAME, APP_VERSION

import atexit
import os
import socket
import stat
import threading
import sys
if sys.version_info < (3, 0):
  import SocketServer as socketserver
else:
  import socketserver
import code
import readline
import rlcompleter
import re

def ddbg(msg):
  # uncomment this to get lots of spam from debugserver
  return
  dbg(msg)

class PythonConsoleServer(socketserver.BaseRequestHandler):
  env = None
  def setup(self):
    dbg('debugserver: connect from %s' % str(self.client_address))
    ddbg('debugserver: env=%r' % PythonConsoleServer.env)
    self.console = TerminatorConsole(PythonConsoleServer.env)

  def handle(self):
    ddbg("debugserver: handling")
    try:
      self.socketio = self.request.makefile(mode='rw')
      sys.stdout = self.socketio
      sys.stdin = self.socketio
      sys.stderr = self.socketio
      self.console.run(self)
    finally:
      sys.stdout = sys.__stdout__
      sys.stdin = sys.__stdin__
      sys.stderr = sys.__stderr__
      self.socketio.close()
      ddbg("debugserver: done handling")

  def finish(self):
    ddbg('debugserver: disconnect from %s' % str(self.client_address))

# rfc1116/rfc1184
LINEMODE = chr(34) # Linemode negotiation

NULL = chr(0)
ECHO = chr(1)
CR   = chr(13)
LF   = chr(10)
SE   = chr(240) # End subnegotiation
NOP  = chr(241)
DM   = chr(242) # Data Mark
BRK  = chr(243) # Break
IP   = chr(244) # Interrupt Process
AO   = chr(245) # Abort Output
AYT  = chr(246) # Are You There
EC   = chr(247) # Erase Character
EL   = chr(248) # Erase Line
GA   = chr(249) # Go Ahead
SB   = chr(250) # Subnegotiation follows
WILL = chr(251) # Subnegotiation commands
WONT = chr(252)
DO   = chr(253)
DONT = chr(254)
IAC  = chr(255) # Interpret As Command

UIAC        = '(^|[^' + IAC + '])' + IAC # Unescaped IAC
BareLF      = re.compile('([^' + CR + '])' + CR)
DoDont      = re.compile(UIAC +'[' + DO + DONT + '](.)')
WillWont    = re.compile(UIAC + '[' + WILL + WONT + '](.)')
AreYouThere = re.compile(UIAC + AYT)
IpTelnet    = re.compile(UIAC + IP)
OtherTelnet = re.compile(UIAC + '[^' + IAC + ']')

# See http://blade.nagaokaut.ac.jp/cgi-bin/scat.rb/ruby/ruby-talk/205335 for telnet bits
# Python doesn't make this an especially neat conversion :(
class TerminatorConsole(code.InteractiveConsole):
  def parse_telnet(self, data):
    odata = data
    data = re.sub(BareLF, '\\1', data)
    data = data.replace(CR + NULL, '')
    data = data.replace(NULL, '')

    bits = re.findall(DoDont, data)
    ddbg("bits = %r" % bits)
    if bits:
      data = re.sub(DoDont, '\\1', data)
      ddbg("telnet: DO/DON'T answer")
      # answer DO and DON'T with WON'T
      for bit in bits:
        self.write(IAC + WONT + bit[1])

    bits = re.findall(WillWont, data)
    if bits:
      data = re.sub(WillWont, '\\1', data)
      ddbg("telnet: WILL/WON'T answer")
      for bit in bits:
        # answer WILLs and WON'T with DON'Ts
        self.write(IAC + DONT + bit[1])

    bits = re.findall(AreYouThere, data)
    if bits:
      ddbg("telnet: am I there answer")
      data = re.sub(AreYouThere, '\\1', data)
      for bit in bits:
        self.write("Yes, I'm still here, I think.\n")

    (data, interrupts) = re.subn(IpTelnet, '\\1', data)
    if interrupts:
      ddbg("debugserver: Ctrl-C detected")
      raise KeyboardInterrupt

    data = re.sub(OtherTelnet, '\\1', data) # and any other Telnet codes
    data = data.replace(IAC + IAC, IAC) # and handle escapes

    if data != odata:
      ddbg("debugserver: Replaced %r with %r" % (odata, data))

    return data

  def raw_input(self, prompt = None):
    ddbg("debugserver: raw_input prompt = %r" % prompt)
    if prompt:
      self.write(prompt)

    buf = ''
    compstate = 0
    while True:
      data = self.server.socketio.read(1)
      ddbg('raw_input: char=%r' % data)
      if data == LF or data == '\006':
        buf = self.parse_telnet(buf + data)
        if buf != '':
          return buf
      elif data == '\004' or data == '': # ^D
        raise EOFError
      else:
        buf += data

  def write(self, data):
    ddbg("debugserver: write %r" % data)
    self.server.socketio.write(data)
    self.server.socketio.flush()

  def run(self, server):
    self.server = server

    self.write("Welcome to the %s-%s debug server, have a nice stay\n" % (APP_NAME, APP_VERSION))
    self.interact()
    try:
      self.write("Time to go.  Bye!\n")
    except:
      pass


_DEBUG_CLIENT = (
    'import os,select,socket,sys\n'
    's=socket.socket(socket.AF_UNIX);s.connect(sys.argv[1])\n'
    'inf=sys.stdin.fileno();out=sys.stdout.buffer\n'
    'while True:\n'
    ' r,_,_=select.select([s,inf],[],[])\n'
    ' if s in r:\n'
    '  d=s.recv(4096)\n'
    '  if not d: break\n'
    '  out.write(d);out.flush()\n'
    ' if inf in r:\n'
    '  d=os.read(inf,4096)\n'
    '  if not d: break\n'
    '  s.sendall(d)\n'
)

def debug_connect_argv(path):
  return [sys.executable, '-c', _DEBUG_CLIENT, path]


def _debug_directory():
  """Private directory for the debug socket, or None if none is safe.

  A non-symlink XDG_RUNTIME_DIR owned by this user with no group/other
  write is used as-is and is not chmodded. Anything else falls through
  to the cache debug directory, which is created mode 0700.
  """
  runtime = os.environ.get('XDG_RUNTIME_DIR') or ''
  if runtime and os.path.isabs(runtime):
    try:
      st = os.lstat(runtime)
    except OSError:
      st = None
    if (st is not None
        and stat.S_ISDIR(st.st_mode)
        and not stat.S_ISLNK(st.st_mode)
        and st.st_uid == os.geteuid()
        and (st.st_mode & 0o022) == 0):
      return runtime

  parent = get_cache_dir()
  directory = os.path.join(parent, 'debug')
  old_umask = os.umask(0o077)
  try:
    try:
      os.makedirs(directory, mode=0o700, exist_ok=True)
    except OSError as ex:
      err('debugserver: cannot create %s (%s)' % (directory, ex))
      return None
  finally:
    os.umask(old_umask)

  try:
    leaf_lstat = os.lstat(directory)
    if (stat.S_ISLNK(leaf_lstat.st_mode)
        or not stat.S_ISDIR(leaf_lstat.st_mode)):
      err('debugserver: %s is not a private directory' % directory)
      return None
    os.chmod(directory, 0o700)
    parent_stat = os.stat(parent)
    if (parent_stat.st_uid == os.geteuid()
        and (parent_stat.st_mode & 0o022)):
      # Drop group/other write only. Do not add any permission bits.
      os.chmod(parent, stat.S_IMODE(parent_stat.st_mode) & ~0o022)
      parent_stat = os.stat(parent)
    leaf_stat = os.stat(directory)
  except OSError as ex:
    err('debugserver: cannot secure %s (%s)' % (directory, ex))
    return None
  if (leaf_stat.st_uid != os.geteuid()
      or parent_stat.st_uid != os.geteuid()
      or (leaf_stat.st_mode & 0o077)):
    err('debugserver: refusing to listen in %s' % directory)
    return None
  return directory


class _DebugUNIXServer(socketserver.UnixStreamServer):
  """Pathname AF_UNIX server. The socket is mode 0600 before listen."""

  def server_bind(self):
    path = self.server_address
    try:
      st = os.lstat(path)
    except FileNotFoundError:
      st = None
    if st is not None:
      # Do not follow a symlink and do not delete a regular file.
      if stat.S_ISLNK(st.st_mode) or not stat.S_ISSOCK(st.st_mode):
        raise OSError('refusing to replace non-socket %s' % path)
      os.unlink(path)
    old_umask = os.umask(0o077)
    try:
      super(_DebugUNIXServer, self).server_bind()
    finally:
      os.umask(old_umask)
    os.chmod(self.server_address, 0o600)
    mode = stat.S_IMODE(os.stat(self.server_address).st_mode)
    if mode != 0o600:
      raise OSError('debug socket mode is %o, want 0600' % mode)

  def server_close(self):
    # Constructor calls this if bind fails. Only unlink a real socket;
    # a return inside finally would swallow the bind error.
    path = self.server_address
    try:
      super(_DebugUNIXServer, self).server_close()
    finally:
      _unlink_debug_socket(path)


def _unlink_debug_socket(path):
  try:
    st = os.lstat(path)
  except FileNotFoundError:
    return
  if stat.S_ISLNK(st.st_mode) or not stat.S_ISSOCK(st.st_mode):
    return
  try:
    os.unlink(path)
  except FileNotFoundError:
    pass


def _shutdown_debug_server(server):
  try:
    server.shutdown()
  except Exception:
    pass
  try:
    server.server_close()
  except Exception:
    pass


def spawn(env):
  directory = _debug_directory()
  if not directory:
    return None
  PythonConsoleServer.env = env
  path = os.path.join(directory, 'terminator-debug-%d.sock' % os.getpid())
  server = _DebugUNIXServer(path, PythonConsoleServer)
  dbg("debugserver: listening on %s" % str(server.server_address))
  debugserver = threading.Thread(target=server.serve_forever, name="DebugServer")
  debugserver.setDaemon(True)
  debugserver.start()
  atexit.register(_shutdown_debug_server, server)
  return(debugserver, server)

