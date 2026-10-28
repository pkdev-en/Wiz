import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from build import build_source
from u8sim import U8
from wizc import KEY_CONSTS
from font6x8 import FONT

FAILS = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if (extra and not cond) else ''))
    if not cond: FAILS.append(name)

def s16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v
def lit(m):
    return {(x, y) for y in range(64) for x in range(192) if m.pixel(x, y)}
def fb(m):
    return {(x, y) for y in range(64) for x in range(192) if m.mem[0xE000 + y * 32 + (x >> 3)] & (0x80 >> (x & 7))}
def text_ref(x, y, s):
    out = set()
    for i, ch in enumerate(s):
        base = (ord(ch) - 32) * 8
        for r in range(8):
            for k in range(6):
                if FONT[base + r] & (0x80 >> k): out.add((x + i * 6 + k, y + r))
    return out
kp = lambda k: (0x80 >> (k >> 3), 0x80 >> (k & 7))

# ---------------- print
src = '''
rom8 name = "Bob"
def main():
    score = 42
    print(2, 3, "Score ", score, " of ", -7)
    print(2, 20, name)
    e = print(2, 40, 123)
    print(100, 40, e)
'''
rom, full, V, syms = build_source(src)
m = U8(rom, []); m.run(30_000_000)
exp = text_ref(2, 3, "Score 42 of -7") | text_ref(2, 20, "Bob") | text_ref(2, 40, "123") | text_ref(100, 40, str(2 + 18))
check('print: strings + numbers chained, rom8 name as text, returns end x', lit(m) == exp, sorted(lit(m) ^ exp)[:6])

# ---------------- asm hline / fillrect vs python model, both draw modes
random.seed(5)
ops = []
for _ in range(60):
    x = random.randint(-10, 200); w = random.randint(0, 120)
    y = random.randint(-3, 66); h = random.randint(1, 6)
    c = random.randint(0, 1)
    ops.append((x, y, w, h, c))
ops += [(0, 0, 192, 1, 1), (191, 5, 1, 1, 1), (0, 6, 8, 1, 1), (3, 7, 5, 1, 1), (8, 8, 8, 1, 1), (7, 9, 2, 1, 1),
        (0, 10, 192, 1, 1), (5, 10, 100, 1, 0), (64, 11, 128, 1, 1), (63, 12, 1, 1, 1)]
def model(ops):
    g = set()
    for (x, y, w, h, c) in ops:
        for j in range(y, y + h):
            if not 0 <= j < 64: continue
            for i in range(x, x + w):
                if 0 <= i < 192:
                    (g.add if c else g.discard)((i, j))
    return g
for mode in (0, 1):
    body = 'def main():\n' + ('    buffered(1)\n' if mode else '') + ''.join('    fillrect(%d, %d, %d, %d, %d)\n' % o for o in ops)
    rom, full, V, syms = build_source(body)
    m = U8(rom, []); why = m.run(80_000_000)
    got = fb(m) if mode else lit(m)
    exp = model(ops)
    check('hline/fillrect asm span == model (%s mode, %d ops)' % ('buffered' if mode else 'direct', len(ops)),
          got == exp, (len(got), len(exp), sorted(got ^ exp)[:6], why))
    if not mode:
        both = all(m.pixel(x, y) == 3 for (x, y) in got)
        check('direct mode sets/clears BOTH bitplanes', both)

# ---------------- pong: never draws above TOP, keys work, win text
rom, full, V, syms = build_source(open('examples/05_pong.wz').read())
m = U8(rom, [])
def g(n):
    a = V[n]; return s16(m.mem[a] | (m.mem[a + 1] << 8))
top_violations = set()
frames = 0
for i in range(120):
    if i == 30: m.keys = [kp(KEY_CONSTS['K_DOWN'])]
    if i == 60: m.keys = [kp(KEY_CONSTS['K_UP'])]
    if i == 90: m.keys = []
    m.run(m.steps + 300_000)
    top_violations |= {p for p in lit(m) if p[1] < 8}
check('pong never lights a pixel in the top 8 rows (status bar area)', not top_violations, sorted(top_violations)[:5])
check('pong draws the field border at y=TOP', all(m.pixel(x, 8) == 3 for x in range(192)) and all(m.pixel(x, 63) == 3 for x in range(192)))
check('pong keys: paddle clamped inside field', 10 <= g('py') <= 48, g('py'))
# force a win and check the message renders
m.mem[V['me']] = 8; m.mem[V['me'] + 1] = 0
m.run(m.steps + 1_500_000)
exp = text_ref(72, 33 - 4, "YOU WIN!")
check('pong shows "YOU WIN!" at 8 points', exp <= lit(m), len(exp - lit(m)))

# ---------------- demo 06
rom, full, V, syms = build_source(open('examples/06_demo.wz').read())
m = U8(rom, [])
m.run(8_000_000)
check('demo: n=5 -> fib=5, 5!=120 shown', text_ref(4, 11, "n = 5") <= lit(m) and text_ref(4, 21, "fib = 5") <= lit(m) and text_ref(4, 31, "n! = 120") <= lit(m))
m.keys = [kp(KEY_CONSTS['K_UP'])]; m.run(m.steps + 6_000_000); m.keys = []; m.run(m.steps + 6_000_000)
check('demo: UP -> n=6, fib=8, 6!=720, presses=1', text_ref(4, 11, "n = 6") <= lit(m) and text_ref(4, 21, "fib = 8") <= lit(m)
      and text_ref(4, 31, "n! = 720") <= lit(m) and text_ref(4, 41, "presses: 1") <= lit(m))

print('\n%d failure(s)' % len(FAILS))
sys.exit(1 if FAILS else 0)
