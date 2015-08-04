#!/usr/bin/python

# Plugin by Sinan Nalkaya <sardok@gmail.com>
# See LICENSE of Terminator package.

""" logger.py - Terminator Plugin to log 'content' of individual
terminals """

import os
import sys
import gtk
import terminatorlib.plugin as plugin
from terminatorlib.translation import _

AVAILABLE = ['Logger']

class Logger(plugin.MenuItem):
    """ Add custom command to the terminal menu"""
    capabilities = ['terminal_menu']
    loggers = None
    dialog_action = gtk.FILE_CHOOSER_ACTION_SAVE
    dialog_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                      gtk.STOCK_SAVE, gtk.RESPONSE_OK)

    def __init__(self):
        plugin.MenuItem.__init__(self)
        if not self.loggers:
            self.loggers = {}

    def callback(self, menuitems, menu, terminal):
        """ Add save menu item to the menu"""
        vte_terminal = terminal.get_vte()
        if not self.loggers.has_key(vte_terminal):
            item = gtk.MenuItem(_('Start _Logger'))
            item.connect("activate", self.start_logger, terminal)
        else:
            item = gtk.MenuItem(_('Stop _Logger'))
            item.connect("activate", self.stop_logger, terminal)
            item.set_has_tooltip(True)
            item.set_tooltip_text("Saving at '" + self.loggers[vte_terminal]["filepath"] + "'")
        menuitems.append(item)
        
    def write_content(self, terminal, row_start, col_start, row_end, col_end):
        """ Final function to write a file """
        content = terminal.get_text_range(row_start, col_start, row_end, col_end,
                                          lambda *a: True)
        fd = self.loggers[terminal]["fd"]
        # Don't write the last char which is always '\n'
        fd.write(content[:-1])
        self.loggers[terminal]["col"] = col_end
        self.loggers[terminal]["row"] = row_end

    def save(self, terminal):
        """ 'contents-changed' callback """
        last_saved_col = self.loggers[terminal]["col"]
        last_saved_row = self.loggers[terminal]["row"]
        (col, row) = terminal.get_cursor_position()
        # Save only when buffer is nearly full,
        # for the sake of efficiency
        if row - last_saved_row < terminal.get_row_count():
            return
        self.write_content(terminal, last_saved_row, last_saved_col, row, col)
        
    def start_logger(self, _widget, Terminal):
        """ Handle menu item callback by saving text to a file"""
        savedialog = gtk.FileChooserDialog(title=_("Save Log File As"),
                                           action=self.dialog_action,
                                           buttons=self.dialog_buttons)
        savedialog.set_do_overwrite_confirmation(True)
        savedialog.set_local_only(True)
        savedialog.show_all()
        response = savedialog.run()
        if response == gtk.RESPONSE_OK:
            try:
                logfile = os.path.join(savedialog.get_current_folder(),
                                       savedialog.get_filename())
                fd = open(logfile, 'w+')
                # Save log file path, 
                # associated file descriptor, signal handler id
                # and last saved col,row positions respectively.
                vte_terminal = Terminal.get_vte()
                (col, row) = vte_terminal.get_cursor_position()

                self.loggers[vte_terminal] = {"filepath":logfile,
                                              "handler_id":0, "fd":fd,
                                              "col":col, "row":row}
                # Add contents-changed callback
                self.loggers[vte_terminal]["handler_id"] = vte_terminal.connect('contents-changed', self.save)
            except:
                e = sys.exc_info()[1]
                error = gtk.MessageDialog(None, gtk.DIALOG_MODAL, gtk.MESSAGE_ERROR,
                                          gtk.BUTTONS_OK, e.strerror)
                error.run()
                error.destroy()
        savedialog.destroy()

    def stop_logger(self, _widget, terminal):
        vte_terminal = terminal.get_vte()
        last_saved_col = self.loggers[vte_terminal]["col"]
        last_saved_row = self.loggers[vte_terminal]["row"]
        (col, row) = vte_terminal.get_cursor_position()
        if last_saved_col != col or last_saved_row != row:
            # Save unwritten bufer to the file
            self.write_content(vte_terminal, last_saved_row, last_saved_col, row, col)
        fd = self.loggers[vte_terminal]["fd"]
        fd.close()
        vte_terminal.disconnect(self.loggers[vte_terminal]["handler_id"])
        del(self.loggers[vte_terminal])
