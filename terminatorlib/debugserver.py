#!/usr/local/bin/python
#
# Copyright (c) 2008, Thomas Hurst <tom@hur.st>
#
# Use of this file is unrestricted provided this notice is retained.
# If you use it, it'd be nice if you dropped me a note.  Also beer.

from terminatorlib.config import dbg, err
from terminatorlib.version import APP_NAME, APP_VERSION

import socket
import threading
import SocketServer
import code
import sys
import readline
import rlcompleter
import re

class PythonConsoleServer(SocketServer.BaseRequestHandler):
  def setup(self):
    dbg('debugserver: connect from %s' % str(self.client_address))
    self.console = TerminatorConsole()

  def handle(self):
    dbg("debugserver: handling")
    try:
      self.socketio = self.request.makefile()
      sys.stdout = self.socketio
      sys.stdin = self.socketio
#      sys.stderr = self.socketio
      self.console.run(self)
    finally:
      sys.stdout = sys.__stdout__
      sys.stdin = sys.__stdin__
#      sys.stderr = sys.__stderr__
      self.socketio.close()
      dbg("debugserver: done handling")

  def verify_request(self, request, client_address):
    return True

  def finish(self):
    dbg('debugserver: disconnect from %s' % str(self.client_address))

BareLF      = re.compile('([^\015])\015')
DoDont      = re.compile('(^|[^\377])\377[\375\376](.)')
WillWont    = re.compile('(^|[^\377])\377[\373\374](.)')
AreYouThere = re.compile('(^|[^\377])\377\366')
IpTelnet    = re.compile('(^|[^\377])\377\364')
OtherTelnet = re.compile('(^|[^\377])\377[^\377]')

# See http://blade.nagaokaut.ac.jp/cgi-bin/scat.rb/ruby/ruby-talk/205335 for telnet bits
# Python doesn't make this an especially neat conversion :(
class TerminatorConsole(code.InteractiveConsole):
  def parse_telnet(self, data):
    odata = data
    data = re.sub(BareLF, '\\1', data)
    data = data.replace('\015\000', '')
    data = data.replace('\000', '')

    bits = re.findall(DoDont, data)
    dbg("bits = %s" % repr(bits))
    if bits:
      data = re.sub(DoDont, '\\1', data)
      dbg("telnet: DO/DON'T answer")
      # answer DO and DON'T with WON'T
      for bit in bits:
        self.write("\377\374" + bit[1])

    bits = re.findall(WillWont, data)
    if bits:
      data = re.sub(WillWont, '\\1', data)
      dbg("telnet: WILL/WON'T answer")
      for bit in bits:
        # answer WILLs and WON'T with DON'Ts
        self.write("\377\376" + bit[1])

    bits = re.findall(AreYouThere, data)
    if bits:
      dbg("telnet: am I there answer")
      data = re.sub(AreYouThere, '\\1', data)
      for bit in bits:
        self.write("Yes, I'm still here, I think.\n")

    bits = re.findall(IpTelnet, data) # IP (Interrupt Process)
    for bit in bits:
      dbg("debugserver: Ctrl-C detected")
      raise KeyboardInterrupt

    data = re.sub(IpTelnet, '\\1', data) # ignore IP Telnet codes
    data = re.sub(OtherTelnet, '\\1', data) # and any other Telnet codes
    data = data.replace('\377\377', '\377') # and handle escapes

    if data != odata:
      dbg("debugserver: Replaced %s with %s" % (repr(odata), repr(data)))

    return data


  def raw_input(self, prompt = None):
    dbg("debugserver: raw_input prompt = %s" % repr(prompt))
    if prompt:
      self.write(prompt)

    buf = ''
    compstate = 0
    while True:
      data = self.server.socketio.read(1) # should get the client sending unbuffered for tab complete?
      dbg('raw_input: char=%s' % repr(data))
      if data == '\n' or data == '\006':
        buf = self.parse_telnet(buf + data).lstrip()
        if buf != '':
          return buf
      elif data == '\004' or data == '': # ^D
        raise EOFError
      else:
        buf += data

  def write(self, data):
    dbg("debugserver: write %s" % repr(data))
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


def server():
  tcpserver = SocketServer.TCPServer(('127.0.0.1', 0), PythonConsoleServer)
  print "Serving on %s" % str(tcpserver.server_address)
  tcpserver.serve_forever()

def spawn():
#  server()
  # tcpserver = SocketServer.ThreadingTCPServer(('', 0), PythonConsoleServer)
  tcpserver = SocketServer.TCPServer(('', 0), PythonConsoleServer)
  print("debugserver: listening on %s" % str(tcpserver.server_address))
  dbg("debugserver: about to spawn thread")
  debugserver = threading.Thread(target=tcpserver.serve_forever, name="DebugServer")
  debugserver.setDaemon(True)
  dbg("debugserver: about to start thread")
  debugserver.start()
  dbg("debugserver: started thread")
  return(debugserver, tcpserver)

