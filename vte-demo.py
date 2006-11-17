#!/usr/bin/python
import sys
import string
import getopt
import gtk
import vte

def selected_cb(terminal, column, row, cb_data):
	if (row == 15):
		if (column < 40):
			return 1
	return 0

def restore_cb(terminal):
	(text, attrs) = terminal.get_text(selected_cb, 1)
	print "A portion of the text at restore-time is:"
	print text

def child_exited_cb(terminal):
	gtk.main_quit()

if __name__ == '__main__':
	child_pid = -1;
	# Defaults.
	audible = 0
	background = None
	blink = 0
	command = None
	emulation = "xterm"
	font = "fixed 12"
	scrollback = 100
	transparent = 0
	visible = 0
	# Let the user override them.
	(shorts, longs) = getopt.getopt(sys.argv[1:], "B:Tabc:f:n:t:v", ["background", "transparent", "audible", "blink", "command=", "font=", "scrollback=", "terminal=", "visible"])
	for argpair in (shorts + longs):
		if ((argpair[0] == '-B') or (argpair[0] == '--background')):
			print "Setting background image to `" + argpair[1] + "'."
			background = argpair[1]
		if ((argpair[0] == '-T') or (argpair[0] == '--transparent')):
			print "Setting transparency."
			transparent = not transparent
		if ((argpair[0] == '-a') or (argpair[0] == '--audible')):
			print "Setting audible bell."
			audible = not audible
		if ((argpair[0] == '-b') or (argpair[0] == '--blink')):
			print "Setting blinking cursor."
			blink = not blink
		if ((argpair[0] == '-c') or (argpair[0] == '--command')):
			print "Running command `" + argpair[1] + "'."
			command = argpair[1]
		if ((argpair[0] == '-f') or (argpair[0] == '--font')):
			print "Setting font to `" + argpair[1] + "'."
			font = argpair[1]
		if ((argpair[0] == '-n') or (argpair[0] == '--scrollback')):
			scrollback = string.atoi(argpair[1])
			if (scrollback == 0):
				scrollback = 100
			else:
				print "Setting scrollback size to `" + str(scrollback) + "'."
		if ((argpair[0] == '-t') or (argpair[0] == '--terminal')):
			print "Setting terminal type to `" + argpair[1] + "'."
			emulation = argpair[1]
		if ((argpair[0] == '-v') or (argpair[0] == '--visible')):
			print "Setting visible bell."
			visible = not visible
	window = gtk.Window()
	terminal = vte.Terminal()
	if (background):
		terminal.set_background_image(background)
	if (transparent):
		terminal.set_background_transparent(gtk.TRUE)
	terminal.set_cursor_blinks(blink)
	terminal.set_emulation(emulation)
	terminal.set_font_from_string(font)
	terminal.set_scrollback_lines(scrollback)
	terminal.set_audible_bell(audible)
	terminal.set_visible_bell(visible)
	terminal.connect("child-exited", child_exited_cb)
	terminal.connect("restore-window", restore_cb)
	if (command):
		# Start up the specified command.
		child_pid = terminal.fork_command(command)
	else:
		# Start up the default command, the user's shell.
		child_pid = terminal.fork_command()
	terminal.show()

	scrollbar = gtk.VScrollbar()
	scrollbar.set_adjustment(terminal.get_adjustment())

	box = gtk.HBox()
	box.pack_start(terminal)
	box.pack_start(scrollbar)

	window.add(box)
	window.show_all()
	gtk.main()
