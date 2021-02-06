# Tmux Control Mode

Terminator supports the [tmux control mode](http://man7.org/linux/man-pages/man1/tmux.1.html#CONTROL_MODE).

## Usage

Remote SSH example, starts tmux on remote host and displays tabs and splits in terminator:

```
terminator -t --remote example.org
```

Start a local tmux session and show it in a new terminator:
```
terminator -t
```

Users might need to add `-u` if terminator is already running, to disable dbus.

## Background

There is a detailed description in the tmux [wiki](https://github.com/tmux/tmux/wiki/Control-Mode).

While iterm2 detects tmux control mode sequences and enters tmux mode, terminator needs to be started in tmux mode and initiates the tmux session itself.
