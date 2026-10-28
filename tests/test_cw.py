"""Wiz 0.4 tests: `for cwii` / `for cw` sections, ML620906 target, boot translation, 1-plane runtime."""
import os, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from build import build_source
from u8sim import U8
from u8asm import Assembler
from wizc import WizError
from targets import select_sections, declared_targets, SectionError, TARGETS

FAILS = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (('  ' + str(extra)) if (extra and not cond) else ''))
    if not cond:
        FAILS.append(name)

def s16(v):
    v &= 0xFFFF
    return v - 65536 if v & 0x8000 else v

def run(src, target, steps=30_000_000):
    rom, full, variables, syms = build_source(src, target)
    m = U8(rom, [], target)
    why = m.run(steps)
    return m, variables, why, full

def var(m, v, name):
    a = v[name]
    return s16(m.mem[a] | (m.mem[a + 1] << 8))

def black(m):
    return {(x, y) for y in range(64) for x in range(192) if m.pixel(x, y) == 3}

# ---------------------------------------------------------------- LEA encodings (hand-computed from the manual)
a = Assembler()
got = [a.encode('LEA', ['0F010H'], 0, True), a.encode('LEA', ['[ER2]'], 0, True), a.encode('LEA', ['4[ER2]'], 0, True)]
check('LEA encodings', got == [[0xF00C, 0xF010], [0xF02A], [0xF02B, 4]], got)

# ---------------------------------------------------------------- section parsing
SRC = '''x = 1
for cwii            # ML620909
a = 10
b = 20
\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014
for cw              # ML620906
a = 30
---------
c = 5
def main():
    pass
'''
s_ii, s_cw = select_sections(SRC, 'cwii'), select_sections(SRC, 'cw')
check('sections: line count preserved', s_ii.count('\n') == SRC.count('\n') == s_cw.count('\n'))
check('sections: cwii keeps its code, drops cw code',
      'a = 10' in s_ii and 'b = 20' in s_ii and 'a = 30' not in s_ii)
check('sections: cw keeps its code, drops cwii code',
      'a = 30' in s_cw and 'a = 10' not in s_cw and 'b = 20' not in s_cw)
check('sections: common code before header and after separator',
      all('x = 1' in t and 'c = 5' in t and 'def main' in t for t in (s_ii, s_cw)))
check('sections: header/separator lines blanked (em-dash never reaches the lexer)',
      '\u2014' not in s_ii and 'for ' not in s_ii and 'for ' not in s_cw)
check('declared targets in order', declared_targets(SRC) == ['cwii', 'cw'])
multi = 'for cwii, cw\nv = 1\n----\nfor all\nw = 2\n----\nz = 3\n'
mi = select_sections(multi, 'cw')
check('sections: "for cwii, cw" and "for all"', 'v = 1' in mi and 'w = 2' in mi and 'z = 3' in mi)
ordinary = 'n = 0\nfor i in range(3):\n    n += 1\ndef main():\n    pass\n'
check('ordinary `for i in range` is not a header', select_sections(ordinary, 'cw') == ordinary and declared_targets(ordinary) == [])
try:
    select_sections('for cw\nx = 1\n', 'cwii'); ok = False
except SectionError as e:
    ok = "no 'for cwii' section" in str(e)
check('error: file without a section for the target', ok)
try:
    declared_targets('for ml620906\nx = 1\n'); ok = False
except SectionError as e:
    ok = 'unknown target' in str(e) and 'line 1' in str(e)
check('error: unknown target name', ok)
try:
    build_source('for cw\nx = 1\ny = z\ndef main():\n    pass\n', 'cw'); ok = False
except WizError as e:
    ok = 'line 3' in str(e)
check('compiler error keeps the ORIGINAL line number inside a section', ok)

# ---------------------------------------------------------------- one file, two machines
DUAL = '''which = 0
for cwii
which = 2
for cw
which = 1
----
def main():
    global which
    which += 10
'''
mi_, vi, wi, _ = run(DUAL, 'cwii')
mc_, vc, wc, _ = run(DUAL, 'cw')
check('dual file: cwii build runs the cwii section', var(mi_, vi, 'which') == 12, (var(mi_, vi, 'which'), wi))
check('dual file: cw build runs the cw section', var(mc_, vc, 'which') == 11, (var(mc_, vc, 'which'), wc))
check('both stop in the halt loop', 'B to self' in wi and 'B to self' in wc, (wi, wc))

# ---------------------------------------------------------------- memory map differences
BIG = 'big = [0] * 3000\ndef main():\n    big[2999] = 7\n'
build_source(BIG, 'cwii')
try:
    build_source(BIG, 'cw'); ok = False
except WizError as e:
    ok = 'RAM' in str(e) or 'memory' in str(e).lower()
check('6000-byte array: fits cwii (20 KB vars), rejected on cw (4 KB vars)', ok)
m, v, why, _ = run('big = [0] * 1900\ndef main():\n    big[1899] = 5\n    big[0] = 6\n', 'cw')
check('1900-element array fits cw and stays in RAM 0xD000-0xDFFF',
      m.mem[0xD000 + 2 * 1899] == 5 and m.mem[0xD000] == 6, why)

# ---------------------------------------------------------------- boot translation sanity
TRIV = 'def main():\n    pass\n'
mc_, vc, wc, full_cw = run(TRIV, 'cw')
mi_, vi, wi, full_ii = run(TRIV, 'cwii')
check('cw boot reaches main and halts', 'B to self' in wc and mc_.sp == 0xF000, (wc, hex(mc_.sp)))
check('cw boot: LEA + [EA+] stores landed (IE0=20H, IE0+2=0)', mc_.mem[0xF010] == 0x20 and mc_.mem[0xF012] == 0)
check('cw boot: final timer reload 05C8H (TM0D)', (mc_.mem[0xF020], mc_.mem[0xF021]) == (0xC8, 0x05))
check('cw boot: FCON=01H after _reset_SFR, BLKCON0=17H', mc_.mem[0xF00A] == 0x01 and mc_.mem[0xF028] == 0x17,
      (hex(mc_.mem[0xF00A]), hex(mc_.mem[0xF028])))
same = [0xF041, 0xF044, 0xF045, 0xF048, 0xF049, 0xF04A, 0xF04B, 0xF04C, 0xF220, 0xF221, 0xF222, 0xF223, 0xF224]
diff = [(hex(x), mc_.mem[x], mi_.mem[x]) for x in same if mc_.mem[x] != mi_.mem[x]]
check('cw boot port/key init equals the (independently translated) cwii boot', not diff, diff)
check('cw boot never selects a bitplane (0F037H untouched)', mc_.mem[0xF037] == 0)

# ---------------------------------------------------------------- 1-plane runtime
def code_lines(full):
    return [l.split(';')[0] for l in full.split('\n')]
check('cw listing has no write to 0F037H; cwii listing has 4',
      not any('0F037H' in l for l in code_lines(full_cw)) and sum('0F037H' in l for l in code_lines(full_ii)) == 4,
      (sum('0F037H' in l for l in code_lines(full_cw)), sum('0F037H' in l for l in code_lines(full_ii))))

SCENE = '''rom8 spr = [0x18, 0x3C, 0x7E, 0xFF, 0xFF, 0x7E, 0x3C, 0x18]
def draw():
    clear()
    rect(2, 2, 60, 30)
    fillrect(10, 10, 20, 12)
    hline(5, 100, 40)
    vline(120, 3, 60)
    line(0, 0, 191, 63)
    circle(150, 30, 20)
    disc(40, 50, 8)
    text(70, 5, "CW vs CWII")
    num(70, 20, -1234)
    sprite(100, 45, 8, 8, spr)
    pixel(11, 11, 0)
    hline(0, 191, 63, 0)
    pixel(191, 0)
    pixel(300, 5)
'''
direct = SCENE + 'def main():\n    draw()\n'
buffd = SCENE + 'def main():\n    buffered(1)\n    draw()\n    flip()\n'
imgs = {}
for tg in ('cwii', 'cw'):
    for kind, src in (('direct', direct), ('buffered', buffd)):
        m, v, why, _ = run(src, tg)
        imgs[(tg, kind)] = black(m)
        check('scene %s/%s finished' % (tg, kind), 'B to self' in why and len(imgs[(tg, kind)]) > 500, (why, len(imgs[(tg, kind)])))
# cw screen is 192x63 (rows 0..62), cwii 192x64: the scene must match on rows 0..62 and cw must draw nothing on row 63
def top63(img):
    return {p for p in img if p[1] < 63}
check('scene pixel-identical: cw == cwii on rows 0..62 (direct draw)', imgs[('cw', 'direct')] == top63(imgs[('cwii', 'direct')]))
check('scene pixel-identical: cw == cwii on rows 0..62 (buffered + flip)', imgs[('cw', 'buffered')] == top63(imgs[('cwii', 'buffered')]))
check('cw draws nothing on row 63 (direct + buffered)', not any(y >= 63 for (x, y) in imgs[('cw', 'direct')] | imgs[('cw', 'buffered')]))
check('cwii still draws on row 63 (line to 191,63)', any(y == 63 for (x, y) in imgs[('cwii', 'direct')]))
check('scene: buffered == direct on cw', imgs[('cw', 'buffered')] == imgs[('cw', 'direct')])
ref = imgs[('cwii', 'direct')]
check('scene sanity: erased pixel absent, corner pixel present, off-screen ignored',
      (11, 11) not in ref and (191, 0) in ref and all(x < 192 and y < 64 for x, y in ref))

# ---------------------------------------------------------------- keys on cw
import wizc
m, v, why, _ = run('const K_EXE = 5\nx = K_EXE\ny = K_UP\ndef main():\n    pass\n', 'cw')
check('cw: built-in K_EXE can be overridden once, others keep their value (K_UP = 40 on cw)',
      (var(m, v, 'x'), var(m, v, 'y')) == (5, 40), (var(m, v, 'x'), var(m, v, 'y')))
m, v, why, _ = run('x = K_UP\ny = K_UP\ndef main():\n    pass\n', 'cwii')
check('cwii keeps its own key table (K_UP = 0x20)', var(m, v, 'x') == 0x20)
try:
    build_source('const K_EXE = 5\nconst K_EXE = 6\ndef main():\n    pass\n', 'cw'); ok = False
except WizError as e:
    ok = 'already defined' in str(e)
check('error: overriding the same K_ constant twice', ok)
try:
    build_source('const FOO = 1\nconst FOO = 2\ndef main():\n    pass\n', 'cw'); ok = False
except WizError as e:
    ok = 'already defined' in str(e)
check('error: user constants still cannot be redefined', ok)
for tgt, bad in (('cw', 'K_OK'), ('cwii', 'K_ALPHA')):
    try:
        build_source('def main():\n    x = %s\n' % bad, tgt); ok = False; msg = ''
    except WizError as e:
        msg = str(e); ok = ('line 2' in msg and bad in msg and 'not a key on ' + tgt in msg)
    check('%s: %s is rejected with a clear message' % (tgt, bad), ok, msg)
build_source('# K_OK is only in a comment\nconst K_OK = 3\nx = K_OK\ndef main():\n    pass\n', 'cw')
check('cw: a user const named like a missing key is allowed', True)
check('cw key table: 49 keys, all scan codes unique and 0..63',
      len(wizc.CW_KEY_CONSTS) - 1 == 49 and all(0 <= c < 64 for k, c in wizc.CW_KEY_CONSTS.items() if k != 'K_NONE'))

# ---------------------------------------------------------------- command line
tmp = tempfile.mkdtemp()
def cli(*args):
    r = subprocess.run([sys.executable, os.path.join(HERE, '..', 'build.py')] + list(args), capture_output=True, text=True, cwd=tmp)
    return r.returncode, r.stdout + r.stderr
open(os.path.join(tmp, 'both.wz'), 'w').write(DUAL)
open(os.path.join(tmp, 'plain.wz'), 'w').write(TRIV)
rc, out = cli('both.wz')
check('cli: sectioned file builds both targets', rc == 0 and os.path.exists(os.path.join(tmp, 'both.cwii.bin'))
      and os.path.exists(os.path.join(tmp, 'both.cw.bin')), out)
check('cli: the two .bin files differ', open(os.path.join(tmp, 'both.cwii.bin'), 'rb').read() != open(os.path.join(tmp, 'both.cw.bin'), 'rb').read())
rc, out = cli('plain.wz')
check('cli: plain file -> plain.bin (cwii, same name as before)', rc == 0 and os.path.exists(os.path.join(tmp, 'plain.bin')), out)
rc, out = cli('plain.wz', '--target', 'cw')
check('cli: --target cw -> plain.cw.bin', rc == 0 and os.path.exists(os.path.join(tmp, 'plain.cw.bin')), out)
rc, out = cli('plain.wz', '--target', 'all')
check('cli: --target all on a plain file builds both', rc == 0 and out.count('bytes ROM') == 2, out)
rc, out = cli('plain.wz', '--target', 'ml620906')
check('cli: unknown --target is an error', rc == 2 and 'unknown target' in out, out)

# ---------------------------------------------------------------- cw screen: 63 visible rows = VRAM rows 1..63 (measured on a real screen)
OFFSRC = 'def main():\n    clear()\n    pixel(0, 0)\n    pixel(0, 62)\n    pixel(191, 62)\n    pixel(0, 63)\n    hline(0, 192, 63)\n    while True:\n        pass\n'
for tg, off in (('cwii', 0), ('cw', 1)):
    m, v, why, _ = run(OFFSRC, tg, 3_000_000)
    vr = lambda row: m.planes[0][row * 32:(row + 1) * 32]
    check('%s: user y=0 is VRAM row %d' % (tg, off), vr(off)[0] == 0x80 and (off == 0 or not any(vr(0))), (off, list(vr(0))[:3], list(vr(off))[:3]))
    last = 62 + off
    check('%s: user y=62 is VRAM row %d (x=0 and x=191)' % (tg, last), vr(last)[0] == 0x80 and vr(last)[23] == 0x01)
    if tg == 'cw':
        extra = sum(1 for i in range(2048) if m.planes[0][i]) - 4      # y=0 (1 byte), y=62 (2 bytes) -> 3 bytes; row 63 must stay empty
        check('cw: y=63 (pixel + hline) draws nothing', sum(1 for i in range(2048) if m.planes[0][i]) == 3, sum(1 for i in range(2048) if m.planes[0][i]))
    else:
        check('cwii: y=63 is a real row (pixel + hline draw there)', any(vr(63)), list(vr(63))[:4])

print('\nFAILED: %s' % FAILS if FAILS else '\nALL PASS')
sys.exit(1 if FAILS else 0)
