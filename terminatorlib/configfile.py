#!/usr/local/bin/python

import re
from terminatorlib.config import dbg, debug

def group(*choices): return '(' + '|'.join(choices) + ')'
def any(*choices): return group(*choices) + '*'
def maybe(*choices): return group(*choices) + '?'

Newline = re.compile(r'[\r\n]+')
Whitespace = r'[ \f\t]*'
Comment = r'#[^\r\n]*'
Ignore  = re.compile(Whitespace + maybe(Comment) + maybe(r'[\r\n]+') + '$')

WhitespaceRE = re.compile(Whitespace)
CommentRE = re.compile(Comment)

QuotedStrings = {"'": re.compile(r"'([^'\r\n]*)'"), '"': re.compile(r'"([^"\r\n]*)"')}

Section = re.compile(r"\[([^\r\n\]]+)\][ \f\t]*")
Setting = re.compile(r"(\w+)\s*=\s*")

PaletteColours = '(?:#[0-9a-fA-F]{12}:){15}#[0-9a-fA-F]{12}'
SingleColour   = '#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}'

Colourvalue = re.compile(group(PaletteColours, SingleColour))
Barevalue = re.compile(r'((?:[^\r\n# \f\t]+|[^\r\n#]+(?!' + Ignore.pattern +'))+)')

Tabsize = 8

class ConfigSyntaxError(Exception):
  def __init__(self, message, cf):
    self.message = message
    self.file = cf.filename
    self.lnum = cf._lnum
    self.pos  = cf._pos
    self.line = cf._line

  def __str__(self):
    return "File %s line %d:\n    %s\n   %s^\n%s" % (repr(self.file), self.lnum,
                                                     self.line.rstrip(),
                                                     ' ' * self.pos, self.message)

class ConfigFile:
  def __init__(self, filename = None):
    self.filename = filename
    self.settings = {}

  def _call_if_match(self, re, callable, group = 0):
    if self._pos == self._max:
      return False
    mo = re.match(self._line, self._pos)
    if mo:
      if callable:
        callable(mo.group(group))
      self._pos = mo.end()
      return True
    else:
      return False

  def _call_if_quoted_string(self, callable):
    if self._pos == self._max:
      return False
    chr = self._line[self._pos]
    if chr in '"\'':
      string = ''
      while True:
        mo = QuotedStrings[chr].match(self._line, self._pos)
        if mo is None:
          raise ConfigSyntaxError("Unterminated quoted string", self)
        self._pos = mo.end()
        if self._line[self._pos - 2] == '\\':
          string += mo.group(1)[0:-1] + chr
          self._pos -= 1
        else:
          string += mo.group(1)
          break
      callable(string)
      return True
    else:
      return False

  def parse(self):
    file = open(self.filename)
    rc = file.readlines()
    file.close()

    self._indents = [0]
    self._pos = 0
    self._max = 0
    self._lnum = 0
    self._line = ''

    self._currsection = None
    self._cursetting = None

    for self._line in rc:
      self._lnum += 1
      self._pos = 0
      self._max = len(self._line)
      dbg("Line %d: %s" % (self._lnum, repr(self._line)))

      self._call_if_match(WhitespaceRE, None)

      # [Section]
      self._call_if_match(Section, self._section, 1)
      # setting =
      if self._call_if_match(Setting, self._setting, 1):
        # "quoted value"
        if not self._call_if_quoted_string(self._value):
          # #000000 # colour that would otherwise be a comment
          if not self._call_if_match(Colourvalue, self._value, 1):
            # bare value
            if not self._call_if_match(Barevalue, self._value, 1):
              raise ConfigSyntaxError("Setting without a value", self)

      self._call_if_match(Ignore, lambda junk: dbg("Ignoring: %s" % junk))

      if self._line[self._pos:] != '':
        raise ConfigSyntaxError("Unexpected token", self)

  def _section(self, section):
    dbg("Section %s" % repr(section))
    self._currsection = section.lower()

  def _setting(self, setting):
    dbg("Setting %s" % repr(setting))
    self._currsetting = setting.lower()

  def _value(self, value):
    dbg("Value %s" % repr(value))
    if self._currsection is not None:
      self.settings.setdefault(self._currsection, {})[self._currsetting] = value
    else:
      self.settings[self._currsetting] = value

