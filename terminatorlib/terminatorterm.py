#!/usr/bin/python
#    Terminator - multiple gnome terminals in one window
#    Copyright (C) 2006-2008  cmsj@tenshu.net
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 2 only.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

"""Terminator by Chris Jones <cmsj@tenshu.net>"""
import pygtk
pygtk.require ("2.0")
import gobject, gtk, pango
import os, signal, sys, subprocess, pwd, re

#import version details
from terminatorlib.version import *

# import our configuration loader
from terminatorlib import config
from terminatorlib.config import dbg, err, debug

#import encoding list
from terminatorlib.encoding import TerminatorEncoding

# import translation support
from terminatorlib import translation

# import vte-bindings
try:
  import vte
except ImportError:
  error = gtk.MessageDialog (None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK,
    _('You need to install python bindings for libvte ("python-vte" in debian/ubuntu)'))
  error.run()
  sys.exit (1)

class TerminatorTermTitle (gtk.EventBox):
  wanted = None
  _title = None
  _termtext = ""
  _sizetext = ""
  _group = None
  _separator = None
  _hbox = None
  _icon = None
  _parent = None
  _unzoomed_title = None

  def __init__ (self, configwanted = False):
    gtk.EventBox.__init__ (self)

    self._title = gtk.Label ()
    self._group = gtk.Label ()
    self._separator = gtk.VSeparator ()
    self._icon = gtk.Image ()
    self._hbox = gtk.HBox ()

    self._hbox.pack_start (self._icon, False, True, 2)
    self._hbox.pack_start (self._group, False, True, 2)
    self._hbox.pack_start (self._separator, False, True, 2)
    self._hbox.pack_start (self._title, True, True)
    self.add (self._hbox)

    self._title.show ()
    self._hbox.show ()

    self.wanted = configwanted

  def set_group_label (self, name):
    """If 'name' is None, hide the group name object, otherwise set it as the group label"""
    if name:
      self._group.set_text (name)
      self._group.show ()
      self._separator.show ()
    else:
      self._group.hide ()
      self._separator.hide ()

  def set_terminal_title (self, name):
    """Set the title text shown in the titlebar"""
    self._termtext = name
    self.update_label ()

  def set_terminal_size (self, width, height):
    """Set the terminal size shown in the titlebar"""
    self._sizetext = "%sx%s" % (width, height)
    self.update_label ()

  def update_label (self):
    """Update the gtk label with values previously set"""
    self._title.set_text ("%s %s" % (self._termtext, self._sizetext))

  def get_terminal_title (self):
    """Return the text showin in the titlebar"""
    return (self._termtext)

  def set_background_color (self, color):
    """Set the background color of the titlebar"""
    self.modify_bg (gtk.STATE_NORMAL, color)

  def set_foreground_color (self, color):
    """Set the foreground color of the titlebar"""
    self._title.modify_fg (color)

  def set_from_icon_name (self, name, size = gtk.ICON_SIZE_MENU):
    """Set an icon for the group label"""
    if not name:
      self._icon.hide ()
      return

    self._icon.set_from_icon_name (APP_NAME + name, size)
    self._icon.show ()

  def update (self):
    """Update our state"""
    if not self._parent:
      self._parent = self.get_parent ()

    if self._parent.terminator._zoomed and len (self._parent.terminator.term_list):
      if not self._unzoomed_title:
        self._unzoomed_title = self.get_terminal_title ()
      if self._parent.conf.zoomedtitlebar:
        self.set_terminal_title ("Zoomed/Maximised terminal, %d hidden" % (len (self._parent.terminator.term_list) - 1))
        self.show()
      else:
        self.hide()
      return
    else:
      if self._unzoomed_title:
        self.set_terminal_title (self._unzoomed_title)
        self._unzoomed_title = None

    if isinstance (self._parent.get_parent (), gtk.Window):
      self.hide()
      return

    if (self._parent.conf.titlebars and self.wanted) or self._parent._group:
      self.show ()
    else:
      self.hide ()

    if self._parent._group:
      self.set_group_label (self._parent._group)
    else:
      self.set_group_label (None)

class TerminatorTerm (gtk.VBox):

  matches = None
  TARGET_TYPE_VTE = 8
  _custom_font_size = None
  _group = None
  focus = None
  _urgent_bell_cnid = None

  def __init__ (self, terminator, profile = None, command = None, cwd = None):
    gtk.VBox.__init__ (self)
    self.terminator = terminator
    self.conf = terminator.conf
    self.command = command
    self._oldtitle = ""
    self.matches = {}

    self.cwd = cwd or os.getcwd();
    if not os.path.exists(self.cwd) or not os.path.isdir(self.cwd):
      self.cwd = pwd.getpwuid(os.getuid ())[5]

    self.clipboard = gtk.clipboard_get (gtk.gdk.SELECTION_CLIPBOARD)
    self.scrollbar_position = self.conf.scrollbar_position

    self._composited_support = True
    self._vte = vte.Terminal ()
    if not hasattr(self._vte, "set_opacity") or not hasattr(self._vte, "is_composited"):
      self._composited_support = False
    dbg ('H9TRANS: composited_support: %s' % self._composited_support)
    #self._vte.set_double_buffered(True)
    self._vte.set_size (80, 24)
    self._vte._expose_data = None
    self._vte.show ()

    self._termbox = gtk.HBox ()
    self._termbox.show()
    
    self._titlebox = TerminatorTermTitle (self.conf.titlebars)

    self._search_string = None
    self._searchbox = gtk.HBox()
    self._searchinput = gtk.Entry()
    self._searchinput.set_activates_default(True)
    self._searchinput.show()

    self._searchinput.connect('activate', self.do_search)
    self._searchinput.connect('key-press-event', self.search_keypress)

    slabel = gtk.Label()
    slabel.set_text(_("Search:"))
    slabel.show()

    sclose = gtk.Button()
    sclose.set_relief(gtk.RELIEF_NONE)
    sclose.set_focus_on_click(False)
    sclose.set_relief(gtk.RELIEF_NONE)
    sclose_icon = gtk.Image()
    sclose_icon.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
    sclose.add(sclose_icon)
    sclose.set_name("terminator-search-close-button")
    if hasattr(sclose, "set_tooltip_text"):
      sclose.set_tooltip_text("Close Search Bar")
    sclose.connect('clicked', self.end_search)
    sclose.show_all()

    # Button for the next result. Explicitly not show()n by default.
    self._search_next = gtk.Button(_("Next"))
    self._search_next.connect('clicked', self.next_search)

    self._searchbox.pack_start(slabel, False)
    self._search_result_label = gtk.Label()
    self._search_result_label.set_text("")
    self._search_result_label.show()
    self._searchbox.pack_start(self._searchinput)
    self._searchbox.pack_start(self._search_result_label, False)
    self._searchbox.pack_start(self._search_next, False, False)
    self._searchbox.pack_end(sclose, False, False)

    self.show()
    self.pack_start(self._titlebox, False)
    self.pack_start(self._termbox)
    self.pack_end(self._searchbox)

    self._titlebox.update ()

    self._scrollbar = gtk.VScrollbar (self._vte.get_adjustment ())
    if self.scrollbar_position != "hidden" and self.scrollbar_position != "disabled":
      self._scrollbar.show ()

    if self.scrollbar_position == 'left':
      packfunc = self._termbox.pack_end
    else:
      packfunc = self._termbox.pack_start

    packfunc (self._vte)
    packfunc (self._scrollbar, False)

    self._vte.connect ("key-press-event", self.on_vte_key_press)
    self._vte.connect ("button-press-event", self.on_vte_button_press)
    self._vte.connect ("popup-menu", self.create_popup_menu)
    """drag and drop"""
    srcvtetargets = [ ( "vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE ) ]
    dsttargets = [ ( "vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE ), ('text/plain', 0, 0) , ("STRING", 0, 0), ("COMPOUND_TEXT", 0, 0)]
    self._vte.drag_source_set( gtk.gdk.CONTROL_MASK | gtk.gdk.BUTTON3_MASK, srcvtetargets, gtk.gdk.ACTION_MOVE)
    self._titlebox.drag_source_set( gtk.gdk.BUTTON1_MASK, srcvtetargets, gtk.gdk.ACTION_MOVE)
    #self._vte.drag_dest_set(gtk.DEST_DEFAULT_MOTION | gtk.DEST_DEFAULT_HIGHLIGHT |gtk.DEST_DEFAULT_DROP ,dsttargets, gtk.gdk.ACTION_MOVE)
    self._vte.drag_dest_set(gtk.DEST_DEFAULT_MOTION | gtk.DEST_DEFAULT_HIGHLIGHT |gtk.DEST_DEFAULT_DROP ,dsttargets, gtk.gdk.ACTION_MOVE)
    self._vte.connect("drag-begin", self.on_drag_begin, self)
    self._titlebox.connect("drag-begin", self.on_drag_begin, self)
    self._vte.connect("drag-data-get", self.on_drag_data_get, self)
    self._titlebox.connect("drag-data-get", self.on_drag_data_get, self)
    #for testing purpose: drag-motion
    self._vte.connect("drag-motion", self.on_drag_motion, self)
    self._vte.connect("drag-data-received", self.on_drag_data_received, self)

    if self.conf.copy_on_selection:
      self._vte.connect ("selection-changed", lambda widget: self._vte.copy_clipboard ())
    if self._composited_support :
      self._vte.connect ("composited-changed", self.on_composited_changed)
    self._vte.connect ("window-title-changed", self.on_vte_title_change)
    self._vte.connect ("grab-focus", self.on_vte_focus)
    self._vte.connect ("focus-out-event", self.on_vte_focus_out)
    self._vte.connect ("focus-in-event", self.on_vte_focus_in)
    self._vte.connect ("resize-window", self.on_resize_window)
    self._vte.connect ("size-allocate", self.on_vte_size_allocate)

    exit_action = self.conf.exit_action
    if exit_action == "restart":
      self._vte.connect ("child-exited", self.spawn_child)
    # We need to support "left" because some buggy versions of gnome-terminal
    #  set it in some situations
    elif exit_action in ("close", "left"):
      self._vte.connect ("child-exited", lambda close_term: self.terminator.closeterm (self))

    self._vte.add_events (gtk.gdk.ENTER_NOTIFY_MASK)
    self._vte.connect ("enter_notify_event", self.on_vte_notify_enter)

    self._vte.connect_after ("realize", self.reconfigure_vte)

    self.add_matches(posix = self.conf.try_posix_regexp)

    env_proxy = os.getenv ('http_proxy')
    if not env_proxy and self.conf.http_proxy and self.conf.http_proxy != '':
      os.putenv ('http_proxy', self.conf.http_proxy)

    os.putenv ('COLORTERM', 'gnome-terminal')

  def prepareurl (self, url, match):
    dbg ("prepareurl: Checking '%s' with a match of '%s'" % (url, match))
    if match == self.matches['email'] and url[0:7] != 'mailto:':
      url = 'mailto:' + url
    elif match == self.matches['addr_only'] and url[0:3] == 'ftp':
      url = 'ftp://' + url
    elif match == self.matches['addr_only']:
      url = 'http://' + url
    elif match == self.matches['launchpad']:
      url = 'https://bugs.launchpad.net/bugs/%s' % re.sub (r'[^0-9]+', '', url)
    
    return url

  def openurl (self, url):
    dbg ('openurl: viewing %s'%url)
    try:
      dbg ('openurl: calling xdg-open')
      subprocess.Popen(["xdg-open", url])
    except:
      dbg ('openurl: xdg-open failed')
      try:
        dbg ('openurl: calling url_show')
        self.terminator.url_show (url)
      except:
        dbg ('openurl: url_show failed. No URL for you')
        pass

  def on_resize_window(self, widget, width, height):
    dbg ('Resize window triggered on %s: %dx%d' % (widget, width, height))

  def on_vte_size_allocate(self, widget, allocation):
    self._titlebox.set_terminal_size (self._vte.get_column_count (), self._vte.get_row_count ())

  def get_pixbuf(self, maxsize= None):
    pixmap = self.get_snapshot()
    (width, height) = pixmap.get_size()
    pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, width, height)
    pixbuf.get_from_drawable(pixmap, pixmap.get_colormap(), 0, 0, 0, 0, width, height)

    longest = max(width, height)

    if maxsize is not None:
      factor = float(maxsize) / float(longest)

    if not maxsize or (width * factor) > width or (height * factor) > height:
      factor = 1

    scaledpixbuf = pixbuf.scale_simple (int(width * factor), int(height * factor), gtk.gdk.INTERP_BILINEAR)

    return(scaledpixbuf)

  def on_drag_begin(self, widget, drag_context, data):
    dbg ('Drag begins')
    widget.drag_source_set_icon_pixbuf(self.get_pixbuf (512))

  def on_drag_data_get(self,widget, drag_context, selection_data, info, time, data):
    dbg ("Drag data get")
    selection_data.set("vte",info, str(data.terminator.term_list.index (self)))

  def on_expose_event(self, widget, event):
    if widget._expose_data is None:
      return False

    color = widget._expose_data['color']
    coord = widget._expose_data['coord']
    
    context = widget.window.cairo_create()
    #leaving those xxx_group as they could be usefull
    ##http://macslow.thepimp.net/?p=153
    #context.push_group()
    context.set_source_rgba(color.red, color.green, color.blue, 0.5)
    if len(coord) > 0 :
      context.move_to(coord[len(coord)-1][0],coord[len(coord)-1][1])
      for i in coord:
        context.line_to(i[0],i[1])
    
    context.fill()
    #context.pop_group_to_source()
    #context.paint()
    return False

  def on_drag_motion(self, widget, drag_context, x, y, time, data): 
    dbg ("Drag Motion on ")
    """
x-special/gnome-icon-list
text/uri-list
UTF8_STRING
COMPOUND_TEXT
TEXT
STRING
text/plain;charset=utf-8
text/plain;charset=UTF-8
text/plain
    """
      
    if 'text/plain' in drag_context.targets:
      #copy text from another widget
      return
    srcwidget = drag_context.get_source_widget()
    if (isinstance(srcwidget, gtk.EventBox) and srcwidget == self._titlebox) or widget == srcwidget:
      #on self
      return

    alloc = widget.allocation
    rect = gtk.gdk.Rectangle(0, 0, alloc.width, alloc.height)
    
    if self.conf.use_theme_colors:
      color = self._vte.get_style ().text[gtk.STATE_NORMAL]
    else:
      color = gtk.gdk.color_parse (self.conf.foreground_color)
     
    pos = self.get_location(widget, x, y)
    topleft = (0,0)
    topright = (alloc.width,0)
    topmiddle = (alloc.width/2,0)
    bottomleft = (0, alloc.height)
    bottomright = (alloc.width,alloc.height)
    bottommiddle = (alloc.width/2, alloc.height)
    middle = (alloc.width/2, alloc.height/2)
    middleleft = (0, alloc.height/2)
    middleright = (alloc.width, alloc.height/2)
    #print "%f %f %d %d" %(coef1, coef2, b1,b2)
    coord = ()
    if pos == "right":
      coord = (topright, topmiddle, bottommiddle, bottomright)
    if pos == "top":
      coord = (topleft, topright, middleright , middleleft) 
    if pos == "left":
      coord = (topleft, topmiddle, bottommiddle, bottomleft)
    if pos == "bottom":
      coord = (bottomleft, bottomright, middleright , middleleft) 
    
    
    #here, we define some widget internal values
    widget._expose_data = { 'color': color, 'coord' : coord }
    #redraw by forcing an event
    connec = widget.connect_after('expose-event', self.on_expose_event)
    widget.window.invalidate_rect(rect, True)
    widget.window.process_updates(True)
    #finaly reset the values
    widget.disconnect(connec)
    widget._expose_data = None

  def on_drag_drop(self, widget, drag_context, x, y, time):
    parent = widget.get_parent()
    dbg ('Drag drop on %s'%parent)

  def on_drag_data_received(self, widget, drag_context, x, y, selection_data, info, time, data):
    dbg ("Drag Data Received")
    if selection_data.type == 'text/plain':
      #copy text to destination
      #print "%s %s" % (selection_data.type, selection_data.target)
      txt = selection_data.data.strip()
      if txt[0:7] == "file://":
        txt = "'%s'" % txt[7:]
      for term in self.terminator.term_list:
        if term == self or (term._group != None and term._group == self._group):
          term._vte.feed_child(txt)
      return
      
    widgetsrc = data.terminator.term_list[int(selection_data.data)]
    srcvte = drag_context.get_source_widget()
    #check if computation requireds
    if (isinstance(srcvte, gtk.EventBox) and srcvte == self._titlebox) or srcvte == widget:
      dbg ("  on itself")
      return
    
    srchbox = widgetsrc
    dsthbox = widget.get_parent().get_parent()
    
    dstpaned = dsthbox.get_parent()
    srcpaned = srchbox.get_parent()
    if isinstance(dstpaned, gtk.Window) and isinstance(srcpaned, gtk.Window):
      dbg ("  Only one terminal")
      return
    pos = self.get_location(widget, x, y)
    
    data.terminator.remove(widgetsrc, True)
    data.terminator.add(self, widgetsrc,pos)
    return

  def get_location(self, vte, x, y):
    pos = ""
    #get the diagonales function for the receiving widget
    coef1 = float(vte.allocation.height)/float(vte.allocation.width)
    coef2 = -float(vte.allocation.height)/float(vte.allocation.width)
    b1 = 0
    b2 = vte.allocation.height
    #determine position in rectangle
    """
    --------
    |\    /|
    | \  / |
    |  \/  |
    |  /\  |
    | /  \ |
    |/    \|
    --------
    """
    if (x*coef1 + b1 > y ) and (x*coef2 + b2 < y ):
      pos =  "right"
    if (x*coef1 + b1 > y ) and (x*coef2 + b2 > y ):
      pos = "top"
    if (x*coef1 + b1 < y ) and (x*coef2 + b2 > y ):
      pos = "left"
    if (x*coef1 + b1 < y ) and (x*coef2 + b2 < y ):
      pos = "bottom"
    return pos

  def add_matches (self, posix = True):
    userchars = "-A-Za-z0-9"
    passchars = "-A-Za-z0-9,?;.:/!%$^*&~\"#'"
    hostchars = "-A-Za-z0-9"
    pathchars = "-A-Za-z0-9_$.+!*(),;:@&=?/~#%'"
    schemes   = "(news:|telnet:|nntp:|file:/|https?:|ftps?:|webcal:)"
    user      = "[" + userchars + "]+(:[" + passchars + "]+)?"
    urlpath   = "/[" + pathchars + "]*[^]'.}>) \t\r\n,\\\"]"

    if posix:
      dbg ('add_matches: Trying POSIX URL regexps.  Set try_posix_regexp = False in config to only try GNU if you get (harmless) VTE warnings.')
      lboundry = "[[:<:]]"
      rboundry = "[[:>:]]"
    else: # GNU
      dbg ('add_matches: Trying GNU URL regexps.  Set try_posix_regexp = True in config if URLs are not detected.')
      lboundry = "\\<"
      rboundry = "\\>"

    self.matches['full_uri'] = self._vte.match_add(lboundry + schemes + "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")

    if self.matches['full_uri'] == -1:
      if posix:
        err ('add_matches: POSIX match failed, trying GNU')
        self.add_matches(posix = False)
      else:
        err ('add_matches: Failed adding URL match patterns')
    else:
      self.matches['voip'] = self._vte.match_add(lboundry + '(callto:|h323:|sip:)' + "[" + userchars + "+][" + userchars + ".]*(:[0-9]+)?@?[" + pathchars + "]+" + rboundry)
      self.matches['addr_only'] = self._vte.match_add (lboundry + "(www|ftp)[" + hostchars + "]*\.[" + hostchars + ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
      self.matches['email'] = self._vte.match_add (lboundry + "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+[.a-zA-Z0-9-]*" + rboundry)
      self.matches['nntp'] = self._vte.match_add (lboundry + '''news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@[-A-Za-z0-9.]+(:[0-9]+)?''' + rboundry)
      # if the url looks like a Launchpad changelog closure entry LP: #92953 - make it a url to http://bugs.launchpad.net
      self.matches['launchpad'] = self._vte.match_add ('\\bLP:? #?[0-9]+\\b')

  def _path_lookup(self, command):
    if os.path.isabs (command):
      if os.path.isfile (command):
        return command
      else:
        return None
    elif command[:2] == './' and os.path.isfile(command):
      dbg('path_lookup: Relative filename "%s" found in cwd' % command)
      return command

    try:
      paths = os.environ['PATH'].split(':')
      if len(paths[0]) == 0: raise (ValueError)
    except (ValueError, NameError):
      dbg('path_lookup: PATH not set in environment, using fallbacks')
      paths = ['/usr/local/bin', '/usr/bin', '/bin']

    dbg('path_lookup: Using %d paths: %s' % (len(paths), paths))

    for path in paths:
      target = os.path.join (path, command)
      if os.path.isfile (target):
        dbg('path_lookup: found "%s"' % target)
        return target

    dbg('path_lookup: Unable to locate "%s"' % command)

  def _shell_lookup(self):
    shells = [os.getenv('SHELL'), pwd.getpwuid(os.getuid())[6],
              'bash', 'zsh', 'tcsh', 'ksh', 'csh', 'sh']

    for shell in shells:
      if shell is None: continue
      elif os.path.isfile (shell):
        return shell
      else:
        rshell = self._path_lookup(shell)
        if rshell is not None:
          dbg('shell_lookup: Found "%s" at "%s"' % (shell, rshell))
          return rshell

    dbg('shell_lookup: Unable to locate a shell')

  def spawn_child (self, event=None):
    update_records = self.conf.update_records
    login = self.conf.login_shell
    args = []
    shell = None
    command = None

    if self.command:
      dbg ('spawn_child: using self.command: %s' % self.command)
      command = self.command
    elif self.conf.use_custom_command:
      dbg ('spawn_child: using custom command: %s' % self.conf.custom_command)
      command = self.conf.custom_command

    if type(command) is list:
      # List of arguments from -x
      dbg('spawn_child: Bypassing shell and trying to run "%s" directly' % command[0])
      shell = self._path_lookup(command[0])
      args = command
    else:
      shell = self._shell_lookup()

      if self.conf.login_shell:
        args.insert(0, "-%s" % shell)
      else:
        args.insert(0, shell)

      if command is not None:
        args += ['-c', command]

    if shell is None:
      # Give up, we're completely stuck
      err (_('Unable to find a shell'))
      gobject.timeout_add (100, self.terminator.closeterm, self)
      return (-1)

    os.putenv ('WINDOWID', '%s' % self._vte.get_parent_window().xid)

    self._pid = self._vte.fork_command (command = shell, argv = args,
        envv = [], loglastlog = login, logwtmp = update_records,
        logutmp = update_records, directory=self.cwd)

    self.on_vte_title_change(self._vte) # Force an initial update of our titles
    self._titlebox.update ()

    if self._pid == -1:
      err (_('Unable to start shell: ') + shell)
      return (-1)

  def get_cwd (self):
    """ Return the current working directory of the subprocess.
        This function requires OS specific behaviours
    """
    try:
      cwd = self.terminator.pid_get_cwd (self._pid)
    except OSError:
      err ('get_cwd: unable to get cwd of %d' % self._pid)
      cwd = '~'
      pass
    dbg ('get_cwd found: %s'%cwd)
    return (cwd)

  def reconfigure_vte (self, widget = None):
    # Set our emulation
    self._vte.set_emulation (self.conf.emulation)

    # Set our wordchars
    self._vte.set_word_chars (self.conf.word_chars)

    # Set our mouselation
    self._vte.set_mouse_autohide (self.conf.mouse_autohide)

    # Set our compatibility
    backspace = self.conf.backspace_binding
    delete = self.conf.delete_binding

# Note, each of the 4 following comments should replace the line beneath it, but the python-vte bindings don't appear to support this constant, so the magic values are being assumed from the C enum :/
    if backspace == "ascii-del":
#      backbind = vte.ERASE_ASCII_BACKSPACE
      backbind = 2
    else:
#      backbind = vte.ERASE_AUTO_BACKSPACE
      backbind = 1

    if delete == "escape-sequence":
#      delbind = vte.ERASE_DELETE_SEQUENCE
      delbind = 3
    else:
#      delbind = vte.ERASE_AUTO
      delbind = 0

    self._vte.set_backspace_binding (backbind)
    self._vte.set_delete_binding (delbind)

    # Set our font
    if not self._custom_font_size:
      try:
        self._vte.set_font (pango.FontDescription (self.conf.font))
      except:
        pass

    # Set our boldness
    self._vte.set_allow_bold (self.conf.allow_bold)

    # Set our color scheme
    palette = self.conf.palette
    if self.conf.use_theme_colors:
      fg_color = self._vte.get_style ().text[gtk.STATE_NORMAL]
      bg_color = self._vte.get_style ().base[gtk.STATE_NORMAL]
    else:
      fg_color = gtk.gdk.color_parse (self.conf.foreground_color)
      bg_color = gtk.gdk.color_parse (self.conf.background_color)
      
    colors = palette.split (':')
    palette = []
    for color in colors:
      if color:
        palette.append (gtk.gdk.color_parse (color))
    self._vte.set_colors (fg_color, bg_color, palette)

    cursor_color = self.conf.cursor_color
    if cursor_color != '':
      self._vte.set_color_cursor (gtk.gdk.color_parse (cursor_color))

    # Set cursor shape
    if hasattr (self._vte, "set_cursor_shape"):
      self._vte.set_cursor_shape (getattr (vte, "CURSOR_SHAPE_" + self.conf.cursor_shape.upper ()))

    # Set our background image, transparency and type
    # Many thanks to the authors of gnome-terminal, on which this code is based.
    background_type = self.conf.background_type
    dbg ('H9TRANS: Configuring background type as: %s' % background_type)

    # set background image settings
    if background_type == "image":
      dbg ('H9TRANS: Setting background image to: %s' % self.conf.background_image)
      self._vte.set_background_image_file (self.conf.background_image)
      dbg ('H9TRANS: Setting background image scroll to: %s' % self.conf.scroll_background)
      self._vte.set_scroll_background (self.conf.scroll_background)
    else:
      dbg ('H9TRANS: Unsetting background image')
      self._vte.set_background_image_file('')
      dbg ('H9TRANS: Unsetting background image scrolling')
      self._vte.set_scroll_background(False)

    # set transparency for the background (image)
    opacity = 65535
    if background_type in ("image", "transparent"):
      self._vte.set_background_tint_color (bg_color)
      self._vte.set_background_saturation(1 - (self.conf.background_darkness))
      opacity = int(self.conf.background_darkness * 65535)
      dbg ('H9TRANS: Set background tint color to: %s' % bg_color)
      dbg ('H9TRANS: Set background saturation to: %s' % (1 - (self.conf.background_darkness)))
    else:
      dbg ('H9TRANS: Set background saturation to: 1')
      self._vte.set_background_saturation(1)
      
    if self._composited_support:
      dbg ('H9TRANS: Set opacity to: %s' % opacity)
      self._vte.set_opacity(opacity)

    if background_type == "transparent":
      if not self.conf.enable_real_transparency:
        self._vte.set_background_transparent (True)
      else:
        self._vte.set_background_transparent (False)

    # Set our cursor blinkiness
    self._vte.set_cursor_blinks (self.conf.cursor_blink)

    if self.conf.force_no_bell:
      self._vte.set_audible_bell (False)
      self._vte.set_visible_bell (False)
      if self._urgent_bell_cnid:
        self._vte.disconnect (self._urgent_bell_cnid)
        self._urgent_bell_cnid = None
    else:
      # Set our audible belliness
      self._vte.set_audible_bell (self.conf.audible_bell)

      # Set our visual flashiness
      self._vte.set_visible_bell (self.conf.visible_bell)

      # Set our urgent belliness
      if self.conf.urgent_bell:
        try:
          self._urgent_bell_cnid = self._vte.connect ("beep", self.terminator.on_beep)
        except TypeError:
          err ("beep signal not supported by your VTE, urgent handler not available")
      elif self._urgent_bell_cnid:
        self._vte.disconnect (self._urgent_bell_cnid)
        self._urgent_bell_cnid = None

    # Set our scrolliness
    self._vte.set_scrollback_lines (self.conf.scrollback_lines)
    self._vte.set_scroll_on_keystroke (self.conf.scroll_on_keystroke)
    self._vte.set_scroll_on_output (self.conf.scroll_on_output)

    if self.scrollbar_position != self.conf.scrollbar_position:
      self.scrollbar_position = self.conf.scrollbar_position

      if self.scrollbar_position == 'hidden' or self.scrollbar_position == 'disabled':
        self._scrollbar.hide ()
      else:
        self._scrollbar.show ()
        if self.scrollbar_position == 'right':
          self._termbox.reorder_child (self._vte, 0)
        elif self.scrollbar_position == 'left':
          self._termbox.reorder_child (self._scrollbar, 0)

    if hasattr (self._vte, "set_alternate_screen_scroll"):
      self._vte.set_alternate_screen_scroll (self.conf.alternate_screen_scroll)

    # Set our sloppiness
    self.focus = self.conf.focus

    # Sync our titlebar state
    self._titlebox.update ()
    self._vte.queue_draw ()

  def on_composited_changed (self, widget):
    self.reconfigure_vte ()

  def on_vte_button_press (self, term, event):
    # Left mouse button + Ctrl while over a link should open it
    mask = gtk.gdk.CONTROL_MASK
    if (event.state & mask) == mask:
      if event.button == 1:
        url = self._vte.match_check (int (event.x / self._vte.get_char_width ()), int (event.y / self._vte.get_char_height ()))
        if url:
          self.openurl (self.prepareurl (url[0], url[1]))
      return False

    # Left mouse button should transfer focus to this vte widget
    # we also need to give focus on the widget where the paste occured
    if event.button in (1 ,2):
      if event.button == 2 and self._group:
        self.paste_clipboard (True)
        return True
      self._vte.grab_focus ()
      return False

    # Right mouse button should display a context menu if ctrl not pressed
    if event.button == 3 and event.state & gtk.gdk.CONTROL_MASK == 0:
      self.create_popup_menu (self._vte, event)
      return True

  def on_vte_notify_enter (self, term, event):
    if (self.focus == "sloppy" or self.focus == "mouse"):
      term.grab_focus ()
      return False

  def do_scrollbar_toggle (self):
    self.toggle_widget_visibility (self._scrollbar)

  def do_title_toggle (self):
    self._titlebox.wanted = not self._titlebox.get_property ('visible')
    self.toggle_widget_visibility (self._titlebox)

  def toggle_widget_visibility (self, widget):
    if not isinstance (widget, gtk.Widget):
      raise TypeError

    if widget.get_property ('visible'):
      widget.hide ()
    else:
      widget.show ()

  def paste_clipboard(self, primary = False):
    if self._group:
      for term in self.terminator.term_list:
        if term._group == self._group:
          if primary:
            term._vte.paste_primary ()
          else:
            term._vte.paste_clipboard ()
    else:
      if primary:
        self._vte.paste_primary ()
      else:
        self._vte.paste_clipboard ()
    self._vte.grab_focus()

  #keybindings for the individual splited terminals (affects only the
  #the selected terminal)
  UnhandledKeybindings = ('close_window', 'full_screen')
  def on_vte_key_press (self, term, event):
    if not event:
      dbg ('on_vte_key_press: Called on %s with no event' % term)
      return False
    mapping = self.terminator.keybindings.lookup(event)
    
    if mapping == "hide_window":
      return False

    if mapping and mapping not in self.UnhandledKeybindings:
      dbg("on_vte_key_press: lookup found %r" % mapping) 
      # handle the case where user has re-bound copy to ctrl+<key>
      # we only copy if there is a selection otherwise let it fall through to ^<key>
      if (mapping == "copy" and event.state & gtk.gdk.CONTROL_MASK):
        if self._vte.get_has_selection ():
          getattr(self, "key_" + mapping)()
          return True
      else:
        getattr(self, "key_" + mapping)()
        return True

    if self._group and self._vte.is_focus ():
      self.terminator.group_emit (self, self._group, 'key-press-event', event)
    return False

  # Key events
  def key_zoom_in(self):
    self.zoom (True)

  def key_zoom_out(self):
    self.zoom (False)

  def key_copy(self):
    self._vte.copy_clipboard ()

  def key_paste(self):
    self.paste_clipboard ()

  def key_toggle_scrollbar(self):
    self.do_scrollbar_toggle ()

  def key_zoom_normal(self):
    self.zoom_orig ()

  def key_search(self):
    self.start_search()

  # bindings that should be moved to Terminator as they all just call
  # a function of Terminator. It would be cleaner if TerminatorTerm
  # has absolutely no reference to Terminator.
  # N (next) - P (previous) - O (horizontal) - E (vertical) - W (close)
  def key_new_root_tab(self):
    self.terminator.newtab (self, True)

  def key_go_next(self):
    self.terminator.go_next (self)

  def key_go_prev(self):
    self.terminator.go_prev (self)

  def key_go_up(self):
    self.terminator.go_up (self)

  def key_go_down(self):
    self.terminator.go_down (self)

  def key_go_left(self):
    self.terminator.go_left (self)

  def key_go_right(self):
    self.terminator.go_right (self)

  def key_split_horiz(self):
    self.terminator.splitaxis (self, False)

  def key_split_vert(self):
    self.terminator.splitaxis (self, True)

  def key_close_term(self):
    self.terminator.closeterm (self)

  def key_new_tab(self):
    self.terminator.newtab(self)

  def key_resize_up(self):
    self.terminator.resizeterm (self, 'Up')

  def key_resize_down(self):
    self.terminator.resizeterm (self, 'Down')

  def key_resize_left(self):
    self.terminator.resizeterm (self, 'Left')

  def key_resize_right(self):
    self.terminator.resizeterm (self, 'Right')

  def key_move_tab_right(self):
    self.terminator.move_tab (self, 'right')

  def key_move_tab_left(self):
    self.terminator.move_tab (self, 'left')

  def key_toggle_zoom(self):
    self.terminator.toggle_zoom (self)

  def key_scaled_zoom(self):
    self.terminator.toggle_zoom (self, True)

  def key_next_tab(self):
    self.terminator.next_tab (self)

  def key_prev_tab(self):
    self.terminator.previous_tab (self)

  def key_switch_to_tab_1(self):
    self.terminator.switch_to_tab (self, 0)

  def key_switch_to_tab_2(self):
    self.terminator.switch_to_tab (self, 1)

  def key_switch_to_tab_3(self):
    self.terminator.switch_to_tab (self, 2)

  def key_switch_to_tab_4(self):
    self.terminator.switch_to_tab (self, 3)

  def key_switch_to_tab_5(self):
    self.terminator.switch_to_tab (self, 4)

  def key_switch_to_tab_6(self):
    self.terminator.switch_to_tab (self, 5)

  def key_switch_to_tab_7(self):
    self.terminator.switch_to_tab (self, 6)

  def key_switch_to_tab_8(self):
    self.terminator.switch_to_tab (self, 7)

  def key_switch_to_tab_9(self):
    self.terminator.switch_to_tab (self, 8)

  def key_switch_to_tab_10(self):
    self.terminator.switch_to_tab (self, 9)

  def key_reset(self):
    self._vte.reset (True, False)

  def key_reset_clear(self):
    self._vte.reset (True, True)

  def key_group_all(self):
    self.group_all(self)

  def key_ungroup_all(self):
    self.ungroup_all(self)

  def key_group_tab(self):
    self.group_tab(self)

  def key_ungroup_tab(self):
    self.ungroup_tab(self)

  def key_new_window(self):
    cmd = sys.argv[0]
    
    if not os.path.isabs(cmd):
      # Command is not an absolute path. Figure out where we are
      cmd = os.path.join (self.terminator.origcwd, sys.argv[0])
      if not os.path.isfile(cmd):
        # we weren't started as ./terminator in a path. Give up
        err('Unable to locate Terminator')
        return False
          
    dbg("Spawning: %s" % cmd)
    subprocess.Popen([cmd,])
  # End key events

  def zoom_orig (self):
    self._custom_font_size = None
    self._vte.set_font (pango.FontDescription (self.conf.font))

  def zoom (self, zoom_in):
    pangodesc = self._vte.get_font ()
    fontsize = pangodesc.get_size ()

    if fontsize > pango.SCALE and not zoom_in:
      fontsize -= pango.SCALE
    elif zoom_in:
      fontsize += pango.SCALE

    pangodesc.set_size (fontsize)
    self._custom_font_size = fontsize
    self._vte.set_font (pangodesc)

  def start_search(self):
    self._searchbox.show()
    self._searchinput.grab_focus()

  def search_keypress(self, widget, event):
    key = gtk.gdk.keyval_name(event.keyval)
    if key == 'Escape':
      self.end_search()

  def end_search(self, widget = None):
    self._search_row = 0
    self._search_string = None
    self._search_result_label.set_text("")
    self._searchbox.hide()
    self._scrollbar.set_value(self._vte.get_cursor_position()[1])
    self._vte.grab_focus()

  def do_search(self, widget):
    string = widget.get_text()
    dbg("do_search: Looking for %r" % string)
    if string == '':
      return

    if string != self._search_string:
      self._search_row = self._get_vte_buffer_range()[0]
      self._search_string = string

    self._search_result_label.set_text("Searching scrollback")
    self.next_search()

  # Called by get_text_range, once per character.  Argh.
  def _search_character(self, widget, col, row, junk):
    return True

  def next_search(self, widget=None):
    startrow,endrow = self._get_vte_buffer_range()
    while True:
      if self._search_row == endrow:
        self._search_row = startrow
        self._search_result_label.set_text("Finished Search")
        self._search_next.hide()
        return
      buffer = self._vte.get_text_range(self._search_row, 0, self._search_row, -1, self._search_character)

      # dbg("Row %d buffer: %r" % (self._search_row, buffer))
      index = buffer.find(self._search_string)
      if index != -1:
        self._search_result_label.set_text("Found at row %d" % self._search_row)
        self._scrollbar.set_value(self._search_row)
        self._search_row += 1
        self._search_next.show()
        return
      self._search_row += 1

  def _get_vte_buffer_range(self):
    column, endrow = self._vte.get_cursor_position()
    startrow = max(0, endrow - self.conf.scrollback_lines)
    return(startrow, endrow)

  def get_geometry (self):
    '''Returns Gdk.Window.get_position(), pixel-based cursor position,
       and Gdk.Window.get_geometry()'''
    reply = dict()
    x, y = self._vte.window.get_origin ()
    reply.setdefault('origin_x',x)
    reply.setdefault('origin_y',y)

    column, row = self._vte.get_cursor_position ()
    cursor_x = column * self._vte.get_char_width ()
    cursor_y = row    * self._vte.get_char_height ()
    reply.setdefault('cursor_x', cursor_x)
    reply.setdefault('cursor_y', cursor_y)

    geometry = self._vte.window.get_geometry()
    reply.setdefault('offset_x', geometry[0])
    reply.setdefault('offset_y', geometry[1])
    reply.setdefault('span_x', geometry[2])
    reply.setdefault('span_y', geometry[3])
    reply.setdefault('depth', geometry[4])

    return reply

  def create_popup_menu (self, widget, event = None):
    menu = gtk.Menu ()
    url = None
    address = None

    if event:
      url = self._vte.match_check (int (event.x / self._vte.get_char_width ()), int (event.y / self._vte.get_char_height ()))
      button = event.button
      time = event.time
    else:
      button = 0
      time = 0

    if url:
      address = self.prepareurl (url[0], url[1])

      if url[1] == self.matches['email']:
        nameopen = _("_Send Mail To...")
        namecopy = _("_Copy Email Address")
        item = gtk.MenuItem (nameopen)
      elif url[1] == self.matches['voip']:
        nameopen = _("Ca_ll To...")
        namecopy = _("_Copy Call Address")
        item = gtk.MenuItem (nameopen)
      else:
        nameopen = _("_Open Link")
        namecopy = _("_Copy Link Address")
        iconopen = gtk.image_new_from_stock(gtk.STOCK_JUMP_TO, gtk.ICON_SIZE_MENU)

        item = gtk.ImageMenuItem (nameopen)
        item.set_property('image', iconopen)

      item.connect ("activate", lambda menu_item: self.openurl (address))
      menu.append (item)

      item = gtk.MenuItem (namecopy)
      item.connect ("activate", lambda menu_item: self.clipboard.set_text (url[0]))
      menu.append (item)

      item = gtk.MenuItem ()
      menu.append (item)

    item = gtk.ImageMenuItem (gtk.STOCK_COPY)
    item.connect ("activate", lambda menu_item: self._vte.copy_clipboard ())
    item.set_sensitive (self._vte.get_has_selection ())
    menu.append (item)

    item = gtk.ImageMenuItem (gtk.STOCK_PASTE)
    item.connect ("activate", lambda menu_item: self.paste_clipboard ())
    menu.append (item)

    item = gtk.MenuItem ()
    menu.append (item)

    if not self.terminator._zoomed:
      str_horiz = _("Split H_orizontally")
      str_vert = _("Split V_ertically")

      item = gtk.ImageMenuItem (str_horiz)
      item_image = gtk.Image ()
      item_image.set_from_icon_name (APP_NAME + '_horiz', gtk.ICON_SIZE_MENU)
      item.set_image (item_image)

      item.connect ("activate", lambda menu_item: self.terminator.splitaxis (self, False))
      menu.append (item)
      item = gtk.ImageMenuItem (str_vert)
      item_image = gtk.Image ()
      item_image.set_from_icon_name (APP_NAME + '_vert', gtk.ICON_SIZE_MENU)
      item.set_image (item_image)

      item.connect ("activate", lambda menu_item: self.terminator.splitaxis (self, True))
      menu.append (item)

      item = gtk.MenuItem (_("Open _Tab"))
      item.connect ("activate", lambda menu_item: self.terminator.newtab (self))
      menu.append (item)

      if self.terminator.debugaddress:
        item = gtk.MenuItem (_("Open _Debug Tab"))
        item.connect ("activate", lambda menu_item: self.terminator.newtab (self, command = "telnet %s" % ' '.join([str(x) for x in self.terminator.debugaddress])))
        menu.append (item)


      if self.conf.extreme_tabs:
        item = gtk.MenuItem (_("Open Top Level Tab"))
        item.connect ("activate", lambda menu_item: self.terminator.newtab (self, True))
        menu.append (item)
      
      item = gtk.MenuItem ()
      menu.append (item)

    item = gtk.ImageMenuItem (gtk.STOCK_CLOSE)
    item.connect ("activate", lambda menu_item: self.terminator.closeterm (self))
    menu.append (item)

    item = gtk.MenuItem ()
    menu.append (item)

    if len (self.terminator.term_list) > 1:
      if not self.terminator._zoomed:
        item = gtk.MenuItem (_("_Zoom terminal"))
        item.connect ("activate", lambda menu_item: self.terminator.toggle_zoom (self, True))
        menu.append (item)

        item = gtk.MenuItem (_("Ma_ximise terminal"))
        item.connect ("activate", lambda menu_item: self.terminator.toggle_zoom (self))
        menu.append (item)
      else:
        if self.terminator._zoomed and not self.terminator._maximised:
          item = gtk.MenuItem (_("_Unzoom terminal"))
          item.connect ("activate", lambda menu_item: self.terminator.toggle_zoom (self, True))
          menu.append (item)

        if self.terminator._zoomed and self.terminator._maximised:
          item = gtk.MenuItem (_("Unma_ximise terminal"))
          item.connect ("activate", lambda menu_item: self.terminator.toggle_zoom (self))
          menu.append (item)

      item = gtk.MenuItem ()
      menu.append (item)


    item = gtk.CheckMenuItem (_("Show _scrollbar"))
    item.set_active (self._scrollbar.get_property ('visible'))
    item.connect ("toggled", lambda menu_item: self.do_scrollbar_toggle ())
    menu.append (item)
    
    item = gtk.CheckMenuItem (_("Show _titlebar"))
    item.set_active (self._titlebox.get_property ('visible'))
    item.connect ("toggled", lambda menu_item: self.do_title_toggle ())
    if self._group:
      item.set_sensitive (False)
    menu.append (item)

    item = gtk.MenuItem (_("Ed_it profile"))
    item.connect ("activate", lambda menu_item: self.terminator.edit_profile (self))
    menu.append (item)

    self._do_encoding_items (menu)
        
    item = gtk.MenuItem ()
    menu.append (item)

    item = gtk.MenuItem (_("_Group"))
    menu.append (item)
    submenu = gtk.Menu ()
    item.set_submenu (submenu)
    self.populate_grouping_menu (submenu)
    if len (self.terminator.term_list) == 1:
      item.set_sensitive (False)

    menu.show_all ()
    menu.popup (None, None, None, button, time)

    return True

  def populate_grouping_menu (self, widget):
    groupitem = None

    if len (self.terminator.groupings) > 0:
      groupitem = gtk.RadioMenuItem (groupitem, _("None"))
      groupitem.set_active (self._group == None)
      groupitem.connect ("activate", self.set_group, None)
      widget.append (groupitem)

      for group in self.terminator.groupings:
        item = gtk.RadioMenuItem (groupitem, group)
        item.set_active (self._group == group)
        item.connect ("toggled", self.set_group, group)
        widget.append (item)
        groupitem = item

      item = gtk.MenuItem ()
      widget.append (item)
    
    item = gtk.MenuItem (_("_New group"))
    item.connect ("activate", self.create_group)
    widget.append (item)

    item = gtk.MenuItem ()
    widget.append (item)

    item = gtk.MenuItem (_("_Group all"))
    item.connect ("activate", self.group_all)
    widget.append (item)

    if self.terminator.get_first_parent_widget (self, gtk.Notebook) is not None and \
       not isinstance (self.get_parent(), gtk.Notebook):
      item = gtk.MenuItem (_("G_roup all in tab"))
      item.connect ("activate", self.group_tab)
      widget.append (item)

    if len (self.terminator.groupings) > 0:
      item = gtk.MenuItem (_("_Ungroup all"))
      item.connect ("activate", self.ungroup_all)
      widget.append (item)
    
    if self.terminator.get_first_parent_widget(self, gtk.Notebook) is not None and \
       not isinstance(self.get_parent(), gtk.Notebook) and \
       len(self.terminator.groupings) > 0:
      item = gtk.MenuItem(_("Ungr_oup all in tab"))
      item.connect("activate", self.ungroup_tab)
      widget.append(item)

  def create_group (self, item):
    win = gtk.Window ()
    vbox = gtk.VBox ()
    hbox = gtk.HBox ()
    entrybox = gtk.HBox ()
    win.add (vbox)
    label = gtk.Label (_("Group name:"))
    entry = gtk.Entry ()
    okbut = gtk.Button (stock=gtk.STOCK_OK)
    canbut = gtk.Button (stock=gtk.STOCK_CANCEL)

    entrybox.pack_start (label, False, True)
    entrybox.pack_start (entry, True, True)
    hbox.pack_end (okbut, False, False)
    hbox.pack_end (canbut, False, False)
    vbox.pack_start (entrybox, False, True)
    vbox.pack_start (hbox, False, True)

    canbut.connect ("clicked", lambda kill: win.destroy())
    okbut.connect ("clicked", self.do_create_group, win, entry)
    entry.connect ("activate", self.do_create_group, win, entry)

    win.show_all ()

  def do_create_group (self, widget, window, entry):
    name = entry.get_text ()
    self.add_group(name)
    self.set_group (None, name)

    window.destroy ()

  def add_group (self, groupname):
    if not groupname in self.terminator.groupings:
      self.terminator.groupings.append(groupname)

  def set_group (self, item, data):
    if self._group == data:
      # No action needed
      return
    else:
       self._group = data
    
    self._titlebox.set_group_label (data)
    self._titlebox.update ()

    self.terminator.group_hoover ()

  def group_all (self, widget):
    allname = _("All")
    self.add_group(allname)
    for term in self.terminator.term_list:
      term.set_group (None, allname)
    self.terminator.group_hoover ()

  def ungroup_all (self, widget):
    for term in self.terminator.term_list:
      term.set_group (None, None)
    self.terminator.group_hoover ()

  def find_all_terms_in_tab (self, notebook, pagenum=-1):
    if pagenum == -1:
      pagenum = notebook.get_current_page()
    notebookchild = notebook.get_nth_page(pagenum)

    terms = []

    for term in self.terminator.term_list:
      termparent = term.get_parent()
      while not isinstance(termparent, gtk.Window):
        if termparent == notebookchild:
          terms.append(term)
        termparent = termparent.get_parent()

    return terms

  def group_tab (self, widget):
    groupname = ""
    notebook = self.terminator.get_first_parent_widget(self, gtk.Notebook)
    pagenum = notebook.get_current_page()
    notebookchild = notebook.get_nth_page(pagenum)
    terms = self.find_all_terms_in_tab(notebook)

    notebooktablabel = notebook.get_tab_label(notebookchild)
    if notebooktablabel.custom is True:
      groupname = notebooktablabel.get_title()

    if groupname == "":
      groupname = "Tab %d" % (pagenum + 1)

    self.add_group(groupname)
    for term in terms:
      term.set_group(None, groupname)
    self.terminator.group_hoover()

  def ungroup_tab (self, widget):
    notebook = self.terminator.get_first_parent_widget(self, gtk.Notebook)
    terms = self.find_all_terms_in_tab (notebook)

    for term in terms:
      term.set_group (None, None)
    self.terminator.group_hoover()

  def on_encoding_change (self, widget, encoding):
    current = self._vte.get_encoding ()
    if current != encoding:
      dbg ('Setting Encoding to: %s'%encoding)
      self._vte.set_encoding (encoding)
      
  def _do_encoding_items (self, menu):
    active_encodings = self.conf.active_encodings
    item = gtk.MenuItem (_("Encodings"))
    menu.append (item)
    submenu = gtk.Menu ()
    item.set_submenu (submenu)
    
    current_encoding = self._vte.get_encoding ()
    group = None
    for encoding in active_encodings:
      radioitem = gtk.RadioMenuItem (group, _(encoding))
      if group is None:
        group = radioitem
        
      if encoding == current_encoding:
        radioitem.set_active (True)
      
      radioitem.connect ('activate', self.on_encoding_change, encoding)
      submenu.append (radioitem)
      
    item = gtk.MenuItem (_("Other Encodings"))
    submenu.append (item)
    #second level

    submenu = gtk.Menu ()
    item.set_submenu (submenu)
    encodings = TerminatorEncoding ().get_list ()
    encodings.sort (lambda x, y: cmp (x[2].lower (), y[2].lower ()))
    group = None

    for encoding in encodings:
      if encoding[1] in active_encodings:
        continue

      if encoding[1] is None:
        label = "%s %s"%(encoding[2], self._vte.get_encoding ())
      else:
        label = "%s %s"%(encoding[2], encoding[1])
        
      radioitem = gtk.RadioMenuItem (group, label)
      if group is None:
        group = radioitem
        
      if encoding[1] == current_encoding:
        radioitem.set_active (True)
      
      radioitem.connect ('activate', self.on_encoding_change, encoding[1])
      submenu.append (radioitem)

  def get_window_title(self, vte = None):
    if vte is None:
      vte = self._vte
    title = vte.get_window_title ()
    if title is None:
      title = str(self.command)
    return title

  def on_vte_title_change(self, vte):
    title = self.get_window_title(vte)
    if title == self._oldtitle:
      # Title hasn't changed, don't bother doing anything
      return
    self._oldtitle = title

    if self.conf.titletips:
      vte.set_property ("has-tooltip", True)
      vte.set_property ("tooltip-text", title)
    #set the title anyhow, titlebars setting only show/hide the label
    self._titlebox.set_terminal_title (title)
    self.terminator.set_window_title (title)
    notebookpage = self.terminator.get_first_notebook_page(vte)
    while notebookpage != None:
      if notebookpage[0].get_tab_label(notebookpage[1]):
        label = notebookpage[0].get_tab_label(notebookpage[1])
        label.set_title(title)
        # FIXME: Is this necessary? The above line should update the label. LP #369370 might be related
        notebookpage[0].set_tab_label(notebookpage[1], label)
      notebookpage = self.terminator.get_first_notebook_page(notebookpage[0])

  def on_vte_focus_in(self, vte, event):
    self._titlebox.set_background_color (self.terminator.window.get_style().bg[gtk.STATE_SELECTED])
    return

  def on_vte_focus_out(self, vte, event):
    self._titlebox.set_background_color (self.terminator.window.get_style().bg[gtk.STATE_NORMAL])
    return

  def on_vte_focus(self, vte):
    title = self.get_window_title(vte)
    self.terminator.set_window_title(title)
    notebookpage = self.terminator.get_first_notebook_page(vte)
    while notebookpage != None:
      if notebookpage[0].get_tab_label(notebookpage[1]):
        label = notebookpage[0].get_tab_label(notebookpage[1])
        label.set_title(title)
        notebookpage[0].set_tab_label(notebookpage[1], label)
      notebookpage = self.terminator.get_first_notebook_page(notebookpage[0])
 
  def is_scrollbar_present(self):
	  return self._scrollbar.get_property('visible')

