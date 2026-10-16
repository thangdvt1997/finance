#!/usr/bin/env python3
"""patch_chr.py <chart.chr> <set file>: chen khoi <expert> (MTAgentReadOnly) vao chart MT4 (ASCII). Idempotent."""
import sys, re
chr_path, set_path = sys.argv[1:3]
strip_only = len(sys.argv) > 3 and sys.argv[3] == "--strip"
s = open(chr_path, 'rb').read().decode('latin-1')
s = re.sub(r'<expert>.*?</expert>\r?\n', '', s, flags=re.S)
if strip_only:
    open(chr_path, 'wb').write(s.encode('latin-1')); sys.exit(0)
inputs = open(set_path, 'rb').read().decode('utf-8', 'ignore').replace('\r\n', '\n').strip().split('\n')
blk = '<expert>\r\nname=MTAgentReadOnly\r\nflags=279\r\nwindow_num=0\r\n<inputs>\r\n' + '\r\n'.join(inputs) + '\r\n</inputs>\r\n</expert>\r\n'
i = s.index('<window>')
s = s[:i] + blk + s[i:]
open(chr_path, 'wb').write(s.encode('latin-1'))
