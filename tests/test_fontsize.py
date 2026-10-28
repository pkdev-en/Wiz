"""Sized text regression tests (run: python3 tests/test_fontsize.py). Everything runs on the SIMULATOR.

Syntax under test:
  print(x, y, cao, dai, a, b, ...)   cao, dai = pixel height and width of each character cell (default 8 x 6).
                                     They count as a size only when both are constants and a value follows;
                                     otherwise every argument is printed as before.
  text(x, y, cao, dai, s)            same size, any expression (variables allowed)
  char(x, y, c, cao, dai)
The glyphs are the 6x8 font resampled nearest-neighbour, so integer multiples are exact pixel doubling."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from build import build_source
from u8sim import U8
from wizc import WizError

FAILS = []

def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if (extra and not cond) else ''))
    if not cond:
        FAILS.append(name)

def screen(src, steps=40_000_000, target='cw'):
    rom, full, variables, syms = build_source(src, target)
    m = U8(rom, [], target)
    m.run(steps)
    return lambda x, y: 1 if m.pixel(x, y) else 0

def bbox(P, x0, x1, y0, y1):
    pts = [(x, y) for x in range(x0, x1) for y in range(y0, y1) if P(x, y)]
    if not pts:
        return None
    return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts))

SRC = '''
def main():
    clear()
    print(0, 0, "Hi")
    print(40, 0, 16, 12, "Hi")
    print(0, 20, 12345)
    print(0, 30, 16, 12, 12345)
    print(100, 0, 6, 5, "Hi")
    hh = 24
    ww = 18
    text(100, 20, hh, ww, "A")
    char(150, 20, 66, 10, 8)
    print(0, 50, 7, 9, 8, 6, "x")
    while True:
        key()
'''
P = screen(SRC)
check('reference screen is not blank', bbox(P, 0, 192, 0, 60) is not None and bbox(P, 0, 30, 0, 10) is not None)
check('16x12 text is exact 2x of 8x6',
      sum(P(x, y) for x in range(12) for y in range(8)) > 10 and
      all(P(40 + 2 * x + i, 2 * y + j) == P(x, y) for x in range(12) for y in range(8) for i in (0, 1) for j in (0, 1)))
check('16x12 number is exact 2x of 8x6',
      sum(P(x, 20 + y) for x in range(30) for y in range(8)) > 30 and
      all(P(2 * x + i, 30 + 2 * y + j) == P(x, 20 + y) for x in range(30) for y in range(8) for i in (0, 1) for j in (0, 1)))
b = bbox(P, 100, 135, 0, 12)
check('6x5 text stays inside its 12 x 6 cells', b is not None and b[1] <= 111 and b[3] <= 5, b)
b = bbox(P, 100, 140, 20, 60)
check('text() with variable 24x18 spans two cells high enough', b is not None and b[3] - b[2] >= 18 and b[1] <= 117, b)
b = bbox(P, 150, 175, 20, 40)
check('char() 10x8 stays inside 8 x 10', b is not None and b[1] <= 157 and b[3] <= 29, b)

# constants followed by a value are a size; a lone constant pair at the end is still two numbers
Q = screen('''
def main():
    clear()
    print(0, 0, 8, 6)
    print(0, 20, 3, "x")
    while True:
        key()
''')
R = screen('''
def main():
    clear()
    print(0, 0, 8)
    print(6, 0, 6)
    print(0, 20, 3, "x")
    while True:
        key()
''')
check('print(x, y, 8, 6) with only two constants still prints two numbers',
      bbox(Q, 0, 40, 0, 8) is not None and all(Q(x, y) == R(x, y) for x in range(40) for y in range(8)))

# errors
try:
    build_source('def main():\n    print(0, 0, 0, 6, "x")\n    while True:\n        key()\n')
    check('print() with cao 0 is rejected', False)
except WizError as e:
    check('print() with cao 0 is rejected', 'cao' in str(e), e)

# every target compiles and draws the same pixels
for tgt in ('cw', 'cwii'):
    try:
        S = screen(SRC, target=tgt)
        check('sized print runs on %s' % tgt, S(41, 8) == P(41, 8) and bbox(S, 40, 60, 0, 20) == bbox(P, 40, 60, 0, 20))
    except Exception as e:
        check('sized print runs on %s' % tgt, False, e)

print('\n%d failure(s)' % len(FAILS))
sys.exit(1 if FAILS else 0)
