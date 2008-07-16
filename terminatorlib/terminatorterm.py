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
import os, platform, sys

#import version details
from terminatorlib.version import *

# import our configuration loader
from terminatorlib import config
from terminatorlib.config import dbg, err, debug

#import encoding list
from terminatorlib.encoding import TerminatorEncoding

# import vte-bindings
try:
  import vte
except:
  error = gtk.MessageDialog (None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR, gtk.BUTTONS_OK,
    _('You need to install python bindings for libvte ("python-vte" in debian/ubuntu)'))
  error.run()
  sys.exit (1)

class TerminatorTerm (gtk.VBox):

  matches = {}
  TARGET_TYPE_VTE = 8

  def __init__ (self, terminator, profile = None, command = None, cwd = None):
    gtk.VBox.__init__ (self)
    self.terminator = terminator
    self.conf = terminator.conf
    self.command = command

    # Sort out cwd detection code, if available
    self.pid_get_cwd = lambda pid: None
    if platform.system() == 'FreeBSD':
      try:
        from terminatorlib import freebsd
        self.pid_get_cwd = lambda pid: freebsd.get_process_cwd(pid)
        dbg ('Using FreeBSD self.pid_get_cwd')
      except:
        dbg ('FreeBSD version too old for self.pid_get_cwd')
        pass
    elif platform.system() == 'Linux':
      dbg ('Using Linux self.pid_get_cwd')
      self.pid_get_cwd = lambda pid: os.path.realpath ('/proc/%s/cwd' % pid)
    else:
      dbg ('Unable to set a self.pid_get_cwd, unknown system: %s'%platform.system)

    # import a library for viewing URLs
    try:
      # gnome.url_show() is really useful
      dbg ('url_show: importing gnome module')
      import gnome
      gnome.init ('terminator', 'terminator')
      self.url_show = gnome.url_show
    except:
      # webbrowser.open() is not really useful, but will do as a fallback
      dbg ('url_show: gnome module failed, using webbrowser')
      import webbrowser
      self.url_show = webbrowser.open

    self.cwd = cwd or os.getcwd();
    if not os.path.exists(self.cwd) or not os.path.isdir(self.cwd):
      self.cwd = pwd.getpwuid(os.getuid ())[5]

    self.clipboard = gtk.clipboard_get (gtk.gdk.SELECTION_CLIPBOARD)
    self.scrollbar_position = self.conf.scrollbar_position

    self._vte = vte.Terminal ()
    #self._vte.set_double_buffered(True)
    self._vte.set_size (80, 24)
    self.reconfigure_vte ()
    self._vte.show ()

    self._termbox = gtk.HBox ()
    self._termbox.show()
    self._title = gtk.Label()
    self._title.show()
    self._titlebox =  gtk.EventBox()
    self._titlebox.add(self._title)
    self.show()
    self.pack_start(self._titlebox, False)
    self.pack_start(self._termbox)

    if self.conf.titlebars:
      self._titlebox.show()
    else:
      self._titlebox.hide()

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
    self._vte.connect ("popup-menu", self.on_vte_popup_menu)
    self._vte._expose_data = None
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

    self._vte.connect ("composited-changed", self.on_composited_changed)
    self._vte.connect ("window-title-changed", self.on_vte_title_change)
    self._vte.connect ("grab-focus", self.on_vte_focus)
    self._vte.connect ("focus-out-event", self.on_vte_focus_out)
    self._vte.connect ("focus-in-event", self.on_vte_focus_in)
    
    self._vte.connect('expose-event', self.on_expose_event)
    

    exit_action = self.conf.exit_action
    if exit_action == "restart":
      self._vte.connect ("child-exited", self.spawn_child)
    # We need to support "left" because some buggy versions of gnome-terminal
    #  set it in some situations
    elif exit_action in ("close", "left"):
      self._vte.connect ("child-exited", lambda close_term: self.terminator.closeterm (self))

    self._vte.add_events (gtk.gdk.ENTER_NOTIFY_MASK)
    self._vte.connect ("enter_notify_event", self.on_vte_notify_enter)

    self.add_matches()

    dbg ('SEGBUG: Setting http_proxy')
    env_proxy = os.getenv ('http_proxy')
    if not env_proxy and self.conf.http_proxy and self.conf.http_proxy != '':
      os.putenv ('http_proxy', self.conf.http_proxy)

    dbg ('SEGBUG: Setting COLORTERM')
    os.putenv ('COLORTERM', 'gnome-terminal')
    dbg ('SEGBUG: TerminatorTerm __init__ complete')

  def openurl (self, url):
    dbg ('openurl: viewing %s'%url)
    try:
      if subprocess.call(["xdg-open", url]) != 0:
        dbg ('openurl: xdg-open failed')
        raise
    except:
      try:
        dbg ('openurl: calling url_show')
        self.url_show (url)
      except:
        dbg ('openurl: url_show failed. No URL for you')
        pass
 
  def on_drag_begin(self, widget, drag_context, data):
    dbg ('Drag begins')
    widget.drag_source_set_icon_pixbuf(self.terminator.icon_theme.load_icon (APP_NAME, 48, 0))
    
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
    widget.window.invalidate_rect(rect, True)
    widget.window.process_updates(True)
    #finaly reset the values
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
      self._vte.feed_child(txt)
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
    
    data.terminator.remove(widgetsrc)
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

  def add_matches (self, lboundry="[[:<:]]", rboundry="[[:>:]]"):
    userchars = "-A-Za-z0-9"
    passchars = "-A-Za-z0-9,?;.:/!%$^*&~\"#'"
    hostchars = "-A-Za-z0-9"
    pathchars = "-A-Za-z0-9_$.+!*(),;:@&=?/~#%'"
    schemes   = "(news:|telnet:|nntp:|file:/|https?:|ftps?:|webcal:)"
    user      = "[" + userchars + "]+(:[" + passchars + "]+)?"
    urlpath   = "/[" + pathchars + "]*[^]'.}>) \t\r\n,\\\"]"
    
    self.matches['full_uri'] = self._vte.match_add(lboundry + schemes + "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")

    # FreeBSD works with [[:<:]], Linux works with \<
    if self.matches['full_uri'] == -1:
      if lboundry != "\\<":
        self.add_matches(lboundry = "\\<", rboundry = "\\>")
    else:
      self.matches['addr_only'] = self._vte.match_add (lboundry + "(www|ftp)[" + hostchars + "]*\.[" + hostchars + ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
      self.matches['email'] = self._vte.match_add (lboundry + "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+[.a-zA-Z0-9-]*" + rboundry)
      self.matches['nntp'] = self._vte.match_add (lboundry + '''news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@[-A-Za-z0-9.]+(:[0-9]+)?''' + rboundry)

  def spawn_child (self, event=None):
    update_records = self.conf.update_records
    login = self.conf.login_shell
    args = []
    shell = ''

    if self.command:
      dbg ('spawn_child: using self.command: %s'%self.command)
      args = ['-c'] + self.command
    elif self.conf.use_custom_command:
      dbg ('spawn_child: using custom command: %s'%self.conf.custom_command)
      args = ['-c'] + self.conf.custom_command

    try:
      if os.environ['PATH'] == "":
        raise (ValueError)
      paths = os.environ['PATH'].split(':')
    except:
      paths = ['/usr/local/bin', '/usr/bin', '/bin']
    dbg ('spawn_child: found paths: "%s"'%paths)

    if True or not self.command and not os.path.exists (shell):
      dbg ('spawn_child: hunting for a command')
      shell = os.getenv ('SHELL') or ''
      if not os.path.exists (shell):
        dbg ('spawn_child: No usable shell in $SHELL (%s)'%os.getenv('SHELL'))
        shell = pwd.getpwuid (os.getuid ())[6] or ''
        if not os.path.exists (shell):
          for i in ['bash','zsh','tcsh','ksh','csh','sh']:
            for p in paths:
              shell = os.path.join(p, i)
              dbg ('spawn_child: Checking if "%s" exists'%shell)
              if not os.path.exists (shell):
                dbg ('spawn_child: %s does not exist'%shell)
                continue
              else:
                dbg ('spawn_child: %s does exist'%shell)
                break
            if os.path.exists (shell):
              break

    if not self.command and not os.path.exists (shell):
      # Give up, we're completely stuck
      err (_('Unable to find a shell'))
      gobject.timeout_add (100, self.terminator.closeterm, self)
      return (-1)

    if self.conf.login_shell:
      args.insert(0, "-" + shell)
    else:
      args.insert(0, shell)

    dbg ('SEGBUG: Setting WINDOWID')
    os.putenv ('WINDOWID', '%s'%self._vte.get_parent_window().xid)

    dbg ('SEGBUG: Forking command: "%s" with args "%s", loglastlog = "%s", logwtmp = "%s", logutmp = "%s" and cwd "%s"'%(shell, args, login, update_records, update_records, self.cwd))
    self._pid = self._vte.fork_command (command = shell, argv = args, envv = [], loglastlog = login, logwtmp = update_records, logutmp = update_records, directory=self.cwd)

    dbg ('SEGBUG: Forked command') 
    if self._pid == -1:
      err (_('Unable to start shell: ') + shell)
      return (-1)

  def get_cwd (self):
    """ Return the current working directory of the subprocess.
        This function requires OS specific behaviours
    """
    cwd = self.pid_get_cwd (self._pid)
    dbg ('get_cwd found: %s'%cwd)
    return (cwd)

  def reconfigure_vte (self):
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

    # Set our background image, transparency and type
    # Many thanks to the authors of gnome-terminal, on which this code is based.
    background_type = self.conf.background_type

    # set background image settings
    if background_type == "image":
      self._vte.set_background_image_file (self.conf.background_image)
      self._vte.set_scroll_background (self.conf.scroll_background)
    else:
      self._vte.set_background_image_file('')
      self._vte.set_scroll_background(False)

    # set transparency for the background (image)
    if background_type in ("image", "transparent"):
      self._vte.set_background_tint_color (bg_color)
      self._vte.set_background_saturation(1 - (self.conf.background_darkness))
      self._vte.set_opacity(int(self.conf.background_darkness * 65535))
    else:
      self._vte.set_background_saturation(1)
      self._vte.set_opacity(65535)

    if not self._vte.is_composited():
      self._vte.set_background_transparent (background_type == "transparent")
    else:
      self._vte.set_background_transparent (False)

    # Set our cursor blinkiness
    self._vte.set_cursor_blinks (self.conf.cursor_blink)

    # Set our audible belliness
    silent_bell = self.conf.silent_bell
    self._vte.set_audible_bell (not silent_bell)

    # Set our visual flashiness
    self._vte.set_visible_bell (silent_bell)

    # Override our flashybelliness
    if self.conf.force_no_bell:
      self._vte.set_visible_bell (False)
      self._vte.set_audible_bell (False)

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

    # Set our sloppiness
    self.focus = self.conf.focus

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
          if (url[0][0:7] != "mailto:") & (url[1] == self.matches['email']):
            address = "mailto:" + url[0]
          else:
            address = url[0]
          self.openurl ( address )
      return False

    # Left mouse button should transfer focus to this vte widget
    #LP#242612:
    # we also need to give focus on the widget where the paste occured
    if event.button in (1 ,2):
      self._vte.grab_focus ()
      return False

    # Right mouse button should display a context menu if ctrl not pressed
    if event.button == 3 and event.state & gtk.gdk.CONTROL_MASK == 0:
      self.do_popup (event)
      return True

  def on_vte_notify_enter (self, term, event):
    if (self.focus == "sloppy" or self.focus == "mouse"):
      term.grab_focus ()
      return False

  def do_scrollbar_toggle (self):
    self.toggle_widget_visibility (self._scrollbar)

  def do_title_toggle (self):
    self.toggle_widget_visibility (self._titlebox)

  def toggle_widget_visibility (self, widget):
    if not isinstance (widget, gtk.Widget):
      raise TypeError

    if widget.get_property ('visible'):
      widget.hide ()
    else:
      widget.show ()

  def paste_clipboard(self):
    self._vte.paste_clipboard()
    self._vte.grab_focus()

  #keybindings for the individual splited terminals (affects only the
  #the selected terminal)
  def on_vte_key_press (self, term, event):
    keyname = gtk.gdk.keyval_name (event.keyval)

    mask = gtk.gdk.CONTROL_MASK
    if (event.state & mask) == mask:
      if keyname == 'plus':
        self.zoom (True)
        return (True)
      elif keyname == 'minus':
        self.zoom (False)
        return (True)
      elif keyname == 'equal':
        self.zoom_orig ()
        return (True)

    mask = gtk.gdk.CONTROL_MASK | gtk.gdk.SHIFT_MASK | gtk.gdk.MOD1_MASK
    if (event.state & mask) == mask:
      #Top level tab
      if keyname == 'T':
        self.terminator.newtab (self, True)
        return (True)
    # bindings that should be moved to Terminator as they all just call
    # a function of Terminator. It would be cleaner is TerminatorTerm
    # has absolutely no reference to Terminator.
    # N (next) - P (previous) - O (horizontal) - E (vertical) - W (close)

    mask = gtk.gdk.CONTROL_MASK | gtk.gdk.SHIFT_MASK
    if (event.state & mask) == mask:
      if keyname == 'N':
        self.terminator.go_next (self)
        return (True)
      elif keyname == "P":
        self.terminator.go_prev (self)
        return (True)
      elif keyname == 'O':
        self.terminator.splitaxis (self, False)
        return (True)
      elif keyname == 'E':
        self.terminator.splitaxis (self, True)
        return (True)
      elif keyname == 'W':
        self.terminator.closeterm (self)
        return (True)
      elif keyname == 'C':
        self._vte.copy_clipboard ()
        return (True)
      elif keyname == 'V':
        self.paste_clipboard ()
        return (True)
      elif keyname == 'S':
        self.do_scrollbar_toggle ()
        return (True)
      elif keyname == 'T':
        self.terminator.newtab(self)
        return (True)
      elif keyname in ('Up', 'Down', 'Left', 'Right'):
          self.terminator.resizeterm (self, keyname)
          return (True)
      elif keyname  == 'Page_Down':
          self.terminator.move_tab(self, 'right')
          return (True)
      elif keyname == 'Page_Up':
          self.terminator.move_tab(self, 'left')
          return (True)
      elif keyname == 'Z':
        self.terminator.toggle_zoom (self, True)
        return (True)
      elif keyname == 'X':
        self.terminator.toggle_zoom (self)
        return (True)
      
    mask = gtk.gdk.CONTROL_MASK
    if (event.state & mask) == mask:
      if keyname  == 'Page_Down':
          self.terminator.next_tab(self)
          return (True)
      elif keyname == 'Page_Up':
          self.terminator.previous_tab(self)
          return (True)
    
    if keyname and (keyname == 'Tab' or keyname.endswith('_Tab')):
        mask = gtk.gdk.CONTROL_MASK | gtk.gdk.SHIFT_MASK
        if (event.state & mask) == mask:
            self.terminator.go_prev (self)
            return (True)
        mask = gtk.gdk.CONTROL_MASK
        if (event.state & mask) == mask:
            self.terminator.go_next (self)
            return (True)
    # Warning, mask value is either gtk.gdk.CONTROL_MASK or gtk.gdk.CONTROL_MASK | gtk.gdk.SHIFT_MASK
    # if you intend to use it, reinit it
    return (False)

  def zoom_orig (self):
    self._vte.set_font (pango.FontDescription (self.conf.font))

  def zoom (self, zoom_in):
    pangodesc = self._vte.get_font ()
    fontsize = pangodesc.get_size ()

    if fontsize > pango.SCALE and not zoom_in:
      fontsize -= pango.SCALE
    elif zoom_in:
      fontsize += pango.SCALE

    pangodesc.set_size (fontsize)
    self._vte.set_font (pangodesc)

  def on_vte_popup_menu (self, term, event):
    self.do_popup (event)

  def do_popup (self, event = None):
    menu = self.create_popup_menu (event)
    menu.popup (None, None, None, event.button, event.time)

  def create_popup_menu (self, event):
    menu = gtk.Menu ()
    url = None

    if event:
      url = self._vte.match_check (int (event.x / self._vte.get_char_width ()), int (event.y / self._vte.get_char_height ()))

    if url:
      if url[1] != self.matches['email']:
        address = url[0]
        nameopen = _("_Open Link")
        namecopy = _("_Copy Link Address")
        iconopen = gtk.image_new_from_stock(gtk.STOCK_JUMP_TO, gtk.ICON_SIZE_MENU)

        item = gtk.ImageMenuItem (nameopen)
        item.set_property('image', iconopen)
      else:
        if url[0][0:7] != "mailto:":
          address = "mailto:" + url[0]
        else:
          address = url[0]
        nameopen = _("_Send Mail To...")
        namecopy = _("_Copy Email Address")

        item = gtk.MenuItem (nameopen)

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

    item = gtk.CheckMenuItem (_("Show _scrollbar"))
    item.set_active (self._scrollbar.get_property ('visible'))
    item.connect ("toggled", lambda menu_item: self.do_scrollbar_toggle ())
    menu.append (item)
    
    item = gtk.CheckMenuItem (_("Show _titlebar"))
    item.set_active (self._titlebox.get_property ('visible'))
    item.connect ("toggled", lambda menu_item: self.do_title_toggle ())
    menu.append (item)

    self._do_encoding_items (menu)
        
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

      if self.conf.extreme_tabs:
        item = gtk.MenuItem (_("Open Top Level Tab"))
        item.connect ("activate", lambda menu_item: self.terminator.newtab (self, True))
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

    item = gtk.ImageMenuItem (gtk.STOCK_CLOSE)
    item.connect ("activate", lambda menu_item: self.terminator.closeterm (self))
    menu.append (item)

    menu.show_all ()
    return menu

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
   
  def on_vte_title_change(self, vte):
    if self.conf.titletips:
      vte.set_property ("has-tooltip", True)
      vte.set_property ("tooltip-text", vte.get_window_title ())
    #set the title anyhow, titlebars setting only show/hide the label
    self._title.set_text(vte.get_window_title ())
    self.terminator.set_window_title("%s: %s" %(APP_NAME.capitalize(), vte.get_window_title ()))
    notebookpage = self.terminator.get_first_notebook_page(vte)
    while notebookpage != None:
      if notebookpage[0].get_tab_label(notebookpage[1]):
        label = notebookpage[0].get_tab_label(notebookpage[1])
        label.set_title(vte.get_window_title ())
        notebookpage[0].set_tab_label(notebookpage[1], label)
      notebookpage = self.terminator.get_first_notebook_page(notebookpage[0])

  def on_vte_focus_in(self, vte, event):
    self._titlebox.modify_bg(gtk.STATE_NORMAL,self.terminator.window.get_style().bg[gtk.STATE_SELECTED])
    self._title.modify_fg(gtk.STATE_NORMAL, self.terminator.window.get_style().fg[gtk.STATE_SELECTED])
    return
    
  def on_vte_focus_out(self, vte, event):
    self._titlebox.modify_bg(gtk.STATE_NORMAL, self.terminator.window.get_style().bg[gtk.STATE_NORMAL])
    self._title.modify_fg(gtk.STATE_NORMAL, self.terminator.window.get_style().fg[gtk.STATE_NORMAL])
    return

  def on_vte_focus(self, vte):
    if vte.get_window_title ():
      self.terminator.set_window_title("%s: %s" %(APP_NAME.capitalize(), vte.get_window_title ()))
      notebookpage = self.terminator.get_first_notebook_page(vte)
      while notebookpage != None:
        if notebookpage[0].get_tab_label(notebookpage[1]):
          label = notebookpage[0].get_tab_label(notebookpage[1])
          label.set_title(vte.get_window_title ())
          notebookpage[0].set_tab_label(notebookpage[1], label)
        notebookpage = self.terminator.get_first_notebook_page(notebookpage[0])

  def destroy(self):
    self._vte.destroy()
 
