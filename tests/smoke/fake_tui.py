import sys,time
sys.stdout.write('\x1b[?1049h\x1b[2J\x1b[H')
for i in range(10): sys.stdout.write('TUIFRAME_%d\r\n'%i)
sys.stdout.flush(); time.sleep(600)
