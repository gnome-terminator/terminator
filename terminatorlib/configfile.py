#!/usr/bin/python

import re
from terminatorlib.config import dbg, debug
from terminatorlib import translation

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
HandleIndents = False

class ConfigSyntaxError(Exception):
  def __init__(self, message, cf):
    self.single_error = cf.errors_are_fatal
    self.message = message
    self.file = cf.filename
    self.lnum = cf._lnum
    self.pos  = cf._pos
    self.line = cf._line

  def __str__(self):
    if self.single_error:
      fmt = "File %(file)s line %(lnum)d:\n    %(line)s\n    %(pad)s^\n%(message)s"
    else:
      fmt = " * %(message)s, line %(lnum)d:\n    %(line)s\n    %(pad)s^\n"
    return fmt % {'message': self.message, 'file': self.file, 'lnum': self.lnum,
                  'line': self.line.rstrip(), 'pad': '-' * self.pos}

class ConfigIndentError(ConfigSyntaxError):
  pass

class ParsedWithErrors(Exception):
  def __init__(self, filename, errors):
    self.file = filename
    self.errors = errors

  def __str__(self):
    return """Errors were encountered while parsing configuration file:

  %r

Some lines have been ignored.

%s
""" % (self.file, "\n".join(map(lambda error: str(error), self.errors)))


class ConfigFile:
  def __init__(self, filename = None, callback = None, errors_are_fatal = False):
    self.callback = callback
    self.errors_are_fatal = errors_are_fatal
    self.filename = filename
    self.errors = []

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
          raise ConfigSyntaxError(_("Unterminated quoted string"), self)
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

    self._sections = {}
    self._currsetting = None
    self._currvalue = None
    self.errors = []

    for self._line in rc:
      try:
        self._lnum += 1
        self._pos = 0
        self._max = len(self._line)
        dbg("Line %d: %r" % (self._lnum, self._line))

        if HandleIndents:
          self._find_indent()
        else:
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
                raise ConfigSyntaxError(_("Setting without a value"), self)

        self._call_if_match(Ignore, lambda junk: dbg("Skipping: %r" % junk))

        if self._line[self._pos:] != '':
          raise ConfigSyntaxError(_("Unexpected token"), self)
        self._line_ok()
      except ConfigSyntaxError, e:
        self._line_error(e)
      except ConfigIndentError, e:
        self.errors.append(e)
        break

    if self.errors:
      raise ParsedWithErrors(self.filename, self.errors)

  def _find_indent(self):
    # Based on tokenizer.py in the base Python standard library
    column = 0
    while self._pos < self._max:
      chr = self._line[self._pos]
      if chr == ' ': column += 1
      elif chr == '\t': column = (column / Tabsize + 1) * Tabsize
      elif chr == '\f': column = 0
      else: break
      self._pos += 1
    if self._pos == self._max: return

    if column > self._indents[-1]:
      self._indents.append(column)
      self._indent() # self._line[:self._pos])

    while column < self._indents[-1]:
      if column not in self._indents:
        raise ConfigSyntaxError("Unindent does not match a previous indent, config parsing aborted", self)
      self._indents.pop()
      self._deindent()

  def _indent(self):
    dbg(" -> Indent %d" % len(self._indents))

  def _deindent(self):
    dbg(" -> Deindent %d" % len(self._indents))

  def _get_section(self):
    i = 1
    sections = []
    while i <= len(self._indents):
      sname = self._sections.get(i, None)
      if not sname:
        break
      sections.append(str(sname))
      i += 1
    return tuple(sections)

  def _section(self, section):
    dbg("Section %r" % section)
    self._sections[len(self._indents)] = section.lower()

  def _setting(self, setting):
    dbg("Setting %r" % setting)
    self._currsetting = setting.lower()

  def _value(self, value):
    dbg("Value %r" % value)
    self._currvalue = value

  def _line_ok(self):
    if self._currvalue is None: return
    else:
      try: # *glares at 2.4 users*
        try:
          self.callback(self._get_section(), self._currsetting, self._currvalue)
        except ValueError, e:
          raise ConfigSyntaxError(str(e), self)
      finally:
        self._currvalue = None

  def _line_error(self, e):
    self._currvalue = None
    if self.errors_are_fatal:
      raise e
    else:
      self.errors.append(e)


