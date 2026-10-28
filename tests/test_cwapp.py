"""cwapp target: a Wiz program living in segment 3 (patched into a firmware). Run from the wiz/ folder."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from build import build_source
from u8sim import U8
from wizc import key_consts

fails = []
def check(name, ok, extra=''):
    print(('PASS ' if ok else 'FAIL ') + name + ((' ' + str(extra)) if extra and not ok else ''))
    if not ok: fails.append(name)

SRC = open(os.path.join(os.path.dirname(__file__), '..', 'examples', '10_app_hello.wz')).read()
rom, full, v, syms = build_source(SRC, 'cwapp')
check('cwapp: code is placed at 3:0E40 (trampoline first)', syms['_TRAMP'] == 0x30E40 and syms['_APP'] > 0x30E40)
check('cwapp: nothing is emitted before 3:0E40 (image below it is blank flash, 0xFF)', all(b == 0xFF for b in rom[:0x30E40]))

def run(src, tg, steps, press=None):
    r, f, vv, ss = build_source(src, tg)
    st, sp = (None, ())
    if tg == 'cwapp':
        st, sp = (ss['_APP'] >> 16, ss['_APP'] & 0xFFFF), {(0, 0xA1CE)}
    m = U8(r, [], tg, st, sp)
    why = m.run(press[0]) if press else ''
    if press:
        k = key_consts(tg)[press[1]]
        m.keys = m.keys + [(0x80 >> (k >> 3), 0x80 >> (k & 7))]
    return m, m.run(steps)

a, _ = run(SRC, 'cwapp', 3_000_000)
b, _ = run(SRC.replace('for cwapp', 'for cw').replace('exit()', 'pass'), 'cw', 3_000_000)
check('cwapp: screen is pixel-identical to the same program built for cw (segment 0)', a.ascii() == b.ascii() and a.ascii().count('#') > 50)
c, why = run(SRC, 'cwapp', 6_000_000, ('1500000', 'K_AC') if False else (1_500_000, 'K_AC'))
check('cwapp: AC -> exit() lands on the firmware reset handler 0:A1CE with SP = F000', why == 'stop at 0:A1CE' and c.sp == 0xF000, why)

# ROM-level checks on the patched image (needs the sample ROM next to the repo; skipped otherwise)
for rp in ('/mnt/user-data/uploads/bro.bin', os.path.join(os.path.dirname(__file__), '..', 'bro.bin')):
    if os.path.exists(rp):
        import subprocess
        out = '/tmp/_cwapp_patched.bin'
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), '..', 'patch_menu.py'), rp, os.path.join(os.path.dirname(__file__), '..', 'examples', '10_app_hello.wz'), out], capture_output=True, text=True)
        check('patch_menu.py runs on the sample ROM', r.returncode == 0, r.stdout + r.stderr)
        pr = open(out, 'rb').read(); orig = open(rp, 'rb').read()
        diff = [i for i in range(len(orig)) if orig[i] != pr[i]]
        check('patch changes only the hook, one menu byte and the program area',
              all(i in range(0x25E1E, 0x25E22) or i == 0x8000 or i >= 0x30E40 for i in diff))
        for mode, want in ((0x03, (2, 0x5E88)), (0x06, (2, 0x5E22)), (0x45, (2, 0x5E22))):
            m = U8(pr, [], 'cwapp', (3, 0x0E40), {(2, 0x5E88), (2, 0x5E22)})
            m.r[8] = mode; m.run(100000)
            check('trampoline: mode %02X continues at %X:%04X' % (mode, *want), (m.csr, m.pc) == want)
        break
print('ALL PASS' if not fails else '%d failure(s)' % len(fails))
sys.exit(1 if fails else 0)
