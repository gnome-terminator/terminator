#!/usr/bin/python
#
# Copyright (c) 2008, Thomas Hurst <tom@hur.st>
#
# Use of this file is unrestricted provided this notice is retained.
# If you use it, it'd be nice if you dropped me a note.  Also beer.

from terminatorlib.util import dbg, err
from terminatorlib.version import APP_NAME, APP_VERSION

import socket
import threading
import SocketServer
import code
import sys
import readline
import rlcompleter
import re

def ddbg(msg):
  # uncomment this to get lots of spam from debugserver
  return
  dbg(msg)

class PythonConsoleServer(SocketServer.BaseRequestHandler):
  env = None
  def setup(self):
    dbg('debugserver: connect from %s' % str(self.client_address))
    ddbg('debugserver: env=%r' % PythonConsoleServer.env)
    self.console = TerminatorConsole(PythonConsoleServer.env)

  def handle(self):
    ddbg("debugserver: handling")
    try:
      self.socketio = self.request.makefile()
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

  def verify_request(self, request, client_address):
    return True

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


def spawn(env):
  PythonConsoleServer.env = env
  tcpserver = SocketServer.TCPServer(('127.0.0.1', 0), PythonConsoleServer)
  dbg("debugserver: listening on %s" % str(tcpserver.server_address))
  debugserver = threading.Thread(target=tcpserver.serve_forever, name="DebugServer")
  debugserver.setDaemon(True)
  debugserver.start()
  return(debugserver, tcpserver)

