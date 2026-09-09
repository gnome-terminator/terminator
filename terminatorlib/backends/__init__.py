# Terminator backends package.
#
# terminal_backend.make_terminal_widget() imports the concrete backend for the
# current platform lazily, so importing this package on its own pulls in
# neither VTE (absent on Windows) nor pywin32 (absent on Linux).
