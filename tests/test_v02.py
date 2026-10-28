"""Wiz 0.2 regression tests (run: python3 tests/test_v02.py). Everything runs on the SIMULATOR."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from build import build_source
from u8sim import U8
from wizc import KEY_CONSTS

FAILS = []

def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if (extra and not cond) else ''))
    if not cond:
        FAILS.append(name)

def s16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v

def run(src, keys=None, steps=3_000_000):
    rom, full, variables, syms = build_source(src)
    m = U8(rom, keys or [])
    why = m.run(steps)
    return m, variables, why

def var(m, variables, name):
    a = variables[name]
    return s16(m.mem[a] | (m.mem[a + 1] << 8))

def key_pair(k):
    return (0x80 >> (k >> 3), 0x80 >> (k & 7))

def lit(m):
    return {(x, y) for y in range(64) for x in range(192) if m.pixel(x, y)}

def fb_pixels(m):
    out = set()
    for y in range(64):
        for x in range(192):
            if m.mem[0xE000 + y * 32 + (x >> 3)] & (0x80 >> (x & 7)):
                out.add((x, y))
    return out

# ---------------------------------------------------------------- 1. constants
m, v, why = run('''
const W = 192
const H = W / 3
const MASK = 1 << 4
a = W
b = H
c = MASK
d = K_OK
e = K_NONE
def main():
    pass
''')
check('const folding', (var(m,v,'a'), var(m,v,'b'), var(m,v,'c'), var(m,v,'d'), var(m,v,'e')) == (192, 64, 16, 0x21, -1),
      [var(m,v,n) for n in 'abcde'])

# ---------------------------------------------------------------- 2. pixel clipping
m, v, why = run('''
sentinel = 4242
def main():
    pixel(-1, 5)
    pixel(192, 5)
    pixel(300, 5)
    pixel(5, 64)
    pixel(5, -3)
    pixel(5, 200)
    pixel(0, 0)
    pixel(191, 63)
''')
check('pixel clipping direct mode', lit(m) == {(0, 0), (191, 63)} and var(m, v, 'sentinel') == 4242, sorted(lit(m)))
m, v, why = run('''
sentinel = 4242
def main():
    buffered(1)
    pixel(-1, 5)
    pixel(192, 5)
    pixel(5, 64)
    pixel(5, -3)
    pixel(0, 0)
    pixel(191, 63)
    pixel(5, 5)
    pixel(5, 5, 0)
''')
check('pixel clipping buffered mode', fb_pixels(m) == {(0, 0), (191, 63)} and var(m, v, 'sentinel') == 4242, sorted(fb_pixels(m)))
check('buffered draws NOT visible before flip', lit(m) == set())

# ---------------------------------------------------------------- 3. flip
m, v, why = run('''
def main():
    buffered(1)
    pixel(10, 10)
    pixel(100, 40)
    flip()
    pixel(50, 50)
    clear()
    pixel(7, 7)
''')
check('flip shows the frame (both planes, black)', lit(m) == {(10, 10), (100, 40)} and
      all(m.pixel(x, y) == 3 for (x, y) in lit(m)), sorted(lit(m)))
check('buffer cleared after flip+clear', fb_pixels(m) == {(7, 7)}, sorted(fb_pixels(m)))

# ---------------------------------------------------------------- 4. key_down / key_hit
src = '''
r_ok = 0
r_up = 0
h1 = 0
h2 = 0
h3 = 0
h4 = 0
def main():
    global r_ok, r_up, h1, h2, h3, h4
    r_ok = key_down(K_OK)
    r_up = key_down(K_UP)
    h1 = key_hit(K_OK)
    h2 = key_hit(K_OK)
    delay(1)
    h3 = key_hit(K_OK)
    while True:
        pass
'''
rom, full, variables, syms = build_source(src)
m = U8(rom, [key_pair(KEY_CONSTS['K_OK'])])
m.run(60_000)
check('key_down true for held key', var(m, variables, 'r_ok') == 1)
check('key_down false for other key', var(m, variables, 'r_up') == 0)
check('key_hit first call = 1, second = 0 while held',
      (var(m, variables, 'h1'), var(m, variables, 'h2'), var(m, variables, 'h3')) == (1, 0, 0),
      (var(m, variables, 'h1'), var(m, variables, 'h2'), var(m, variables, 'h3')))

# all 64 scan indexes round-trip: pressing index k makes key_down(k) true and every other false
tmpl = '''
k = %d
res = 0
other = 0
def main():
    global res, other
    res = key_down(k)
    other = 0
    for j in range(0, 64):
        if j != k:
            other += key_down(j)
    while True:
        pass
'''
bad = []
for k in range(64):
    rom, full, variables, syms = build_source(tmpl % k)
    m = U8(rom, [key_pair(k)])
    m.run(400_000)
    if var(m, variables, 'res') != 1 or var(m, variables, 'other') != 0:
        bad.append((k, var(m, variables, 'res'), var(m, variables, 'other')))
check('key_down exact for all 64 scan indexes', not bad, bad[:5])

# key_hit across press / release / press (state must reset on release)
src = '''
log = 0
def main():
    global log
    log = 0
    while True:
        if key_hit(K_EXE):
            log += 1
'''
rom, full, variables, syms = build_source(src)
m = U8(rom, [])
m.run(20_000)
c0 = var(m, variables, 'log')
m.keys = [key_pair(KEY_CONSTS['K_EXE'])]
m.run(m.steps + 20_000)
c1 = var(m, variables, 'log')
m.run(m.steps + 20_000)
c2 = var(m, variables, 'log')
m.keys = []
m.run(m.steps + 20_000)
m.keys = [key_pair(KEY_CONSTS['K_EXE'])]
m.run(m.steps + 20_000)
c3 = var(m, variables, 'log')
check('key_hit: 0 idle, 1 on press, still 1 while held, 2 after release+press', (c0, c1, c2, c3) == (0, 1, 1, 2), (c0, c1, c2, c3))

# ---------------------------------------------------------------- 5. drawing library vs python reference
def ref_line(x0, y0, x1, y1):
    pts = []
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        pts.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy; x0 += sx
        if e2 <= dx:
            err += dx; y0 += sy
    return pts

def ref_circle(cx, cy, r):
    pts = set(); x, y, err = r, 0, 1 - r
    while x >= y:
        for (a, b) in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
            pts.add((cx + a, cy + b))
        y += 1
        if err < 0: err += 2 * y + 1
        else:
            x -= 1; err += 2 * (y - x) + 1
    return pts

lines = [(2, 3, 150, 40), (150, 40, 2, 3), (10, 60, 10, 5), (0, 0, 191, 0), (30, 30, 30, 30), (-20, 10, 60, 50), (100, 70, 120, -5)]
prog = 'def main():\n    buffered(1)\n' + ''.join('    line(%d, %d, %d, %d)\n' % l for l in lines) + \
       '    circle(96, 32, 20)\n    circle(10, 10, 15)\n    rect(5, 5, 30, 20)\n    fillrect(150, 40, 10, 8)\n    disc(60, 50, 6)\n'
m, v, why = run(prog, steps=20_000_000)
exp = set()
for l in lines:
    exp |= {p for p in ref_line(*l)}
exp |= ref_circle(96, 32, 20) | ref_circle(10, 10, 15)
exp |= {(x, 5) for x in range(5, 35)} | {(x, 24) for x in range(5, 35)} | {(5, y) for y in range(5, 25)} | {(34, y) for y in range(5, 25)}
exp |= {(x, y) for x in range(150, 160) for y in range(40, 48)}
exp |= {(60 + dx, 50 + dy) for dx in range(-6, 7) for dy in range(-6, 7) if dx * dx + dy * dy <= 36}
exp = {(x, y) for (x, y) in exp if 0 <= x < 192 and 0 <= y < 64}
got = fb_pixels(m)
check('line/circle/rect/fillrect/disc match Python reference (incl. clipping)', got == exp,
      (len(got), len(exp), sorted(got ^ exp)[:8], why))

# ---------------------------------------------------------------- 6. math + rand + defaults
m, v, why = run('''
a = abs(-5)
b = min(3, 9)
c = max(3, 9)
d = clamp(50, 0, 10)
e = sign(-77)
srand(1)
r1 = rand(1000)
r2 = rand(1000)
r3 = rand(1000)
def f(x, y=10, z=20):
    return x + y + z
g1 = f(1)
g2 = f(1, 2)
g3 = f(1, 2, 3)
def main():
    pass
''')
seed = 1
rs = []
for _ in range(3):
    seed = (seed * 25173 + 13849) & 0xFFFF
    rs.append(((seed >> 1) & 0x7FFF) % 1000)
check('abs/min/max/clamp/sign', [var(m,v,n) for n in 'abcde'] == [5, 3, 9, 10, -1], [var(m,v,n) for n in 'abcde'])
check('rand matches Python LCG', [var(m,v,n) for n in ('r1','r2','r3')] == rs, ([var(m,v,n) for n in ('r1','r2','r3')], rs))
check('default arguments', [var(m,v,n) for n in ('g1','g2','g3')] == [31, 23, 6], [var(m,v,n) for n in ('g1','g2','g3')])

# user function overrides library function of same name
m, v, why = run('''
def abs(n):
    return 123
a = abs(-5)
def main():
    pass
''')
check('user def overrides library def', var(m, v, 'a') == 123)

print('\n%d failure(s)' % len(FAILS))
sys.exit(1 if FAILS else 0)
