"""u8asm - assembler for the nX-U8/100 and nX-U16/100 cores (ML620909 / ML620906), built from the
opcode table in the OKI nX-U8/100 Core Instruction Manual, Chapter 4 and cross-checked against the
LAPIS nX-U16/100 Core Instruction Manual, Chapter 4 (tools/check_core_tables.py).

Core selection:  Assembler(core='nX-U16/100')   (aliases: 'u16', 'nxu16', 'nX-U8/100', 'u8', 'nxu8').
The two manuals list the SAME 170 opcode patterns, flags and register set, so both cores share one
encoder (ENCODING_TABLE below) and produce byte-identical ROMs; the core only decides the label, the
conditional-branch cycle model (CORES[...]['bcond_cycles']) and what errors are reported.

Words are 16-bit little-endian. Output is a flat ROM image starting at 0x0000.

Supported syntax (one statement per line, ';' starts a comment):
    label:
    NAME EQU expr
    ORG expr
    DW expr[, expr...]      DB expr[, expr...]
    MNEMONIC operands
Pseudo-instructions (always safe for any distance):
    JMP label               -> B label
    JCC label               -> inverted short branch over a B label   (CC = EQ,NE,GE,...)
"""
import re
import sys

COND = {
    'GE': 0x0, 'LT': 0x1, 'GT': 0x2, 'LE': 0x3,
    'GES': 0x4, 'LTS': 0x5, 'GTS': 0x6, 'LES': 0x7,
    'NE': 0x8, 'EQ': 0x9, 'NV': 0xA, 'OV': 0xB,
    'PS': 0xC, 'NS': 0xD, 'AL': 0xE,
}

# (mnemonic) -> Rn,Rm opcode low nibble / imm8 opcode high nibble
ALU_RR = {'ADD': 0x1, 'ADDC': 0x6, 'AND': 0x2, 'CMP': 0x7, 'CMPC': 0x5,
          'MOV': 0x0, 'OR': 0x3, 'XOR': 0x4, 'SUB': 0x8, 'SUBC': 0x9}
ALU_IMM = {'ADD': 0x1, 'ADDC': 0x6, 'AND': 0x2, 'CMP': 0x7, 'CMPC': 0x5,
           'MOV': 0x0, 'OR': 0x3, 'XOR': 0x4}
SHIFT = {'SLL': 0xA, 'SLLC': 0xB, 'SRL': 0xC, 'SRLC': 0xD, 'SRA': 0xE}


# Per-core facts. 'table' is the opcode table the encoder uses: both manuals' Chapter 4 are
# identical (verified by tools/check_core_tables.py), so both point at the same table.
ENCODING_TABLE = 'u8_u16_common'
CORES = {
    'nX-U8/100': {'family': 'U8', 'table': ENCODING_TABLE, 'bcond_cycles': (1, 3)},
    # U16 manual 1.1: A33/A34 core -> Bcond 1 (not taken) / 3 (taken); A35 core -> 1 / 2.
    # A34 is the default the manual names when a chip's datasheet does not say. ML620906 TRG: COREREV=A3.2.
    'nX-U16/100': {'family': 'U16', 'table': ENCODING_TABLE, 'bcond_cycles': (1, 3)},
}
_CORE_ALIASES = {'u8': 'nX-U8/100', 'nxu8': 'nX-U8/100', 'nx-u8/100': 'nX-U8/100', 'nx-u8': 'nX-U8/100',
                 'u16': 'nX-U16/100', 'nxu16': 'nX-U16/100', 'nx-u16/100': 'nX-U16/100', 'nx-u16': 'nX-U16/100'}


def resolve_core(name):
    key = _CORE_ALIASES.get(str(name).strip().lower())
    if key is None:
        raise ValueError('unknown core %r (use %s)' % (name, ', '.join(CORES)))
    return key


class AsmError(Exception):
    pass


def _reg(tok):
    m = re.fullmatch(r'(?i)r(\d+)', tok)
    if m and int(m.group(1)) < 16:
        return int(m.group(1))
    return None


def _ereg(tok):
    m = re.fullmatch(r'(?i)er(\d+)', tok)
    if m and int(m.group(1)) < 16 and int(m.group(1)) % 2 == 0:
        return int(m.group(1))
    return None


class Assembler:
    def __init__(self, core='nX-U8/100'):
        self.syms = {}
        self.core = resolve_core(core)
        self.core_info = CORES[self.core]

    # ---- expression evaluation -------------------------------------
    def ev(self, s, final):
        s = s.strip()
        s = re.sub(r'(?i)\b([0-9][0-9a-f]*)h\b', lambda m: str(int(m.group(1), 16)), s)
        s = re.sub(r'(?i)0x([0-9a-f]+)', lambda m: str(int(m.group(1), 16)), s)

        def sub(m):
            n = m.group(0)
            if n in self.syms:
                return str(self.syms[n])
            if final:
                raise AsmError('undefined symbol %s' % n)
            return '0'
        s = re.sub(r'[A-Za-z_.$][A-Za-z0-9_.$]*', sub, s)
        try:
            return int(eval(s, {'__builtins__': {}}, {}))
        except Exception:
            raise AsmError('bad expression: %r' % s)

    # ---- one instruction -> list of 16-bit words --------------------
    def encode(self, mn, ops, pc, final):
        mn = mn.upper()
        n = len(ops)

        def imm(tok):
            return self.ev(tok.lstrip('#'), final)

        # --- no operand ---
        simple = {'NOP': 0xFE8F, 'RT': 0xFE1F, 'RTI': 0xFE0F, 'BRK': 0xFFFF,
                  'EI': 0xED08, 'DI': 0xEBF7, 'SC': 0xED80, 'RC': 0xEB7F,
                  'CPLC': 0xFECF, 'INC': 0xFE2F, 'DEC': 0xFE3F}
        if mn in simple and n == 0:
            return [simple[mn]]
        if mn in ('INC', 'DEC') and ops == ['[EA]']:
            return [simple[mn]]

        # --- PUSH / POP ---
        if mn in ('PUSH', 'POP') and n >= 1:
            names = [o.upper() for o in ops]
            if n == 1 and _ereg(names[0]) is not None:
                e = _ereg(names[0])
                return [(0xF000 | (e << 8) | (0x5E if mn == 'PUSH' else 0x1E))]
            if n == 1 and _reg(names[0]) is not None:
                r = _reg(names[0])
                return [0xF000 | (r << 8) | (0x4E if mn == 'PUSH' else 0x0E)]
            bits = 0
            for nm in names:
                if nm == 'EA': bits |= 1
                elif nm == 'LR': bits |= 8
                elif nm in ('PSW', 'EPSW'): bits |= 4
                elif nm in ('PC', 'ELR'): bits |= 2
                else: raise AsmError('bad register list item %s' % nm)
            return [0xF000 | (bits << 8) | (0xCE if mn == 'PUSH' else 0x8E)]

        # --- DSR prefix (Wiz-internal: data segment of the NEXT memory access) ---
        if mn == 'DSRI' and n == 1:
            return [0xE300 | (self.ev(ops[0], final) & 0xFF)]

        # --- branches ---
        if mn in ('B', 'BL') and n == 1:
            e = _ereg(ops[0])
            if e is not None:
                return [0xF002 | (e << 8) | (0 if mn == 'B' else 1)]
            tgt = self.ev(ops[0], final)
            return [0xF000 | (((tgt >> 16) & 0xF) << 8) | (0 if mn == 'B' else 1), tgt & 0xFFFF]
        if mn == 'JMP' and n == 1:
            return self.encode('B', ops, pc, final)
        m = re.fullmatch(r'B(GES|LTS|GTS|LES|GE|LT|GT|LE|NE|EQ|NV|OV|PS|NS|AL)', mn)
        if m and n == 1:
            tgt = self.ev(ops[0], final)
            r = (tgt - (pc + 2)) >> 1 if final else 0
            if final and ((tgt - (pc + 2)) & 1 or not -128 <= r <= 127):
                raise AsmError('branch out of range (%d words) at %04X' % (r, pc))
            return [0xC000 | (COND[m.group(1)] << 8) | (r & 0xFF)]
        m = re.fullmatch(r'J(GES|LTS|GTS|LES|GE|LT|GT|LE|NE|EQ|NV|OV|PS|NS)', mn)
        if m and n == 1:
            inv = COND[m.group(1)] ^ 1
            tgt = self.ev(ops[0], final)
            # skip the following 2-word B instruction: offset = +2 words
            return [0xC000 | (inv << 8) | 2, 0xF000 | (((tgt >> 16) & 0xF) << 8), tgt & 0xFFFF]

        # --- LEA (EA <- address) ---
        if mn == 'LEA' and n == 1:
            m = re.fullmatch(r'\[(?i:er)(\d+)\]', ops[0])
            if m:
                return [0xF00A | (int(m.group(1)) << 4)]
            m = re.fullmatch(r'(.+)\[(?i:er)(\d+)\]', ops[0])
            if m:
                return [0xF00B | (int(m.group(2)) << 4), self.ev(m.group(1), final) & 0xFFFF]
            return [0xF00C, self.ev(ops[0], final) & 0xFFFF]

        # --- MUL / DIV ---
        if mn in ('MUL', 'DIV') and n == 2:
            e, r = _ereg(ops[0]), _reg(ops[1])
            if e is None or r is None:
                raise AsmError('%s needs ERn,Rm' % mn)
            return [0xF000 | (e << 8) | (r << 4) | (0x4 if mn == 'MUL' else 0x9)]

        # --- extend / ALU one-operand ---
        if mn == 'EXTBW' and n == 1:
            e = _ereg(ops[0])
            return [0x800F | (((e | 1) << 8)) | (e << 4)]  # 1000_nnn1_nnn0_1111
        if mn in ('NEG', 'DAA', 'DAS') and n == 1:
            r = _reg(ops[0])
            code = {'DAA': 0x1F, 'DAS': 0x3F, 'NEG': 0x5F}[mn]
            return [0x8000 | (r << 8) | code]

        # --- SB / RB / TB ---
        if mn in ('SB', 'RB', 'TB') and n == 1:
            low = {'SB': 0x0, 'RB': 0x2, 'TB': 0x1}[mn]
            m = re.fullmatch(r'(?i)r(\d+)\.([0-7])', ops[0])
            if m:
                return [0xA000 | (int(m.group(1)) << 8) | (int(m.group(2)) << 4) | low]
            m = re.fullmatch(r'(.+)\.([0-7])', ops[0])
            if m:
                return [0xA080 | (int(m.group(2)) << 4) | low, self.ev(m.group(1), final) & 0xFFFF]
            raise AsmError('bad bit operand %s' % ops[0])

        # --- shifts ---
        if mn in SHIFT and n == 2:
            r = _reg(ops[0])
            if ops[1].startswith('#'):
                return [0x9000 | (r << 8) | ((imm(ops[1]) & 7) << 4) | SHIFT[mn]]
            return [0x8000 | (r << 8) | (_reg(ops[1]) << 4) | SHIFT[mn]]

        # --- LEA ---
        # (not used by the compiler; omitted deliberately)

        # --- L / ST ---
        if mn in ('L', 'ST') and n == 2:
            st = (mn == 'ST')
            dst = ops[0]
            src = ops[1]
            r, e = _reg(dst), _ereg(dst)
            if r is None and e is None:
                raise AsmError('%s first operand must be Rn/ERn' % mn)
            sz = 0 if e is None else 2  # low nibble group
            reg = r if e is None else e
            base = (1 if st else 0)
            m = re.fullmatch(r'\[(?i:er)(\d+)\]', src)
            if m:
                k = int(m.group(1))
                if e is None:
                    return [0x9000 | (reg << 8) | (k << 4) | base]
                return [0x9000 | (reg << 8) | (k << 4) | (0x2 + base)]
            if src == '[EA]':
                if e is None:
                    return [0x9000 | (reg << 8) | 0x30 | base]
                return [0x9000 | (reg << 8) | 0x30 | (0x2 + base)]
            if src == '[EA+]':
                if e is None:
                    return [0x9000 | (reg << 8) | 0x50 | base]
                return [0x9000 | (reg << 8) | 0x50 | (0x2 + base)]
            m = re.fullmatch(r'(.+)\[(?i:er)(\d+)\]', src)
            if m:
                k = int(m.group(2))
                d = self.ev(m.group(1), final) & 0xFFFF
                if e is None:
                    return [0x9000 | (reg << 8) | (k << 4) | (0x8 + base), d]
                return [0xA000 | (reg << 8) | (k << 4) | (0x8 + base), d]
            # direct address Dadr
            d = self.ev(src, final) & 0xFFFF
            if e is None:
                return [0x9010 | (reg << 8) | base, d]
            return [0x9010 | (reg << 8) | (0x2 + base), d]

        # --- MOV special registers ---
        if mn == 'MOV' and n == 2:
            a, b = ops[0].upper(), ops[1].upper()
            if a == 'PSW' and b.startswith('#'):
                return [0xE900 | (imm(b) & 0xFF)]
            if a == 'PSW' and _reg(b) is not None:
                return [0xA00B | (_reg(b) << 4)]
            if _reg(a) is not None and b == 'PSW':
                return [0xA003 | (_reg(a) << 8)]
            if _ereg(a) is not None and b == 'SP':
                return [0xA01A | (_ereg(a) << 8)]
            if a == 'SP' and _ereg(b) is not None:
                return [0xA10A | (_ereg(b) << 4)]
        if mn == 'ADD' and n == 2 and ops[0].upper() == 'SP':
            return [0xE100 | (imm(ops[1]) & 0xFF)]

        # --- ALU ---
        if mn in ALU_RR and n == 2:
            r, e = _reg(ops[0]), _ereg(ops[0])
            if r is not None:
                r2 = _reg(ops[1])
                if r2 is not None:
                    return [0x8000 | (r << 8) | (r2 << 4) | ALU_RR[mn]]
                if ops[1].startswith('#') and mn in ALU_IMM:
                    v = imm(ops[1])
                    if not -128 <= v <= 255:
                        raise AsmError('imm8 out of range: %d' % v)
                    return [(ALU_IMM[mn] << 12) | (r << 8) | (v & 0xFF)]
            if e is not None:
                e2 = _ereg(ops[1])
                if e2 is not None and mn in ('ADD', 'MOV', 'CMP'):
                    low = {'ADD': 0x6, 'MOV': 0x5, 'CMP': 0x7}[mn]
                    return [0xF000 | (e << 8) | (e2 << 4) | low]
                if ops[1].startswith('#') and mn in ('ADD', 'MOV'):
                    v = imm(ops[1])
                    if not -64 <= v <= 63:
                        raise AsmError('imm7 out of range: %d (use two MOV Rn,#imm8)' % v)
                    top = 0x80 if mn == 'ADD' else 0x00
                    return [0xE000 | (e << 8) | top | (v & 0x7F)]
        raise AsmError('cannot encode: %s %s' % (mn, ', '.join(ops)))

    # ---- driver ------------------------------------------------------
    def assemble(self, text, base=0):
        lines = []
        for raw in text.replace('\r', '').split('\n'):
            line = raw.split(';')[0].strip()
            if line:
                lines.append(line)
        image = {}
        for final in (False, True):
            pc = base
            image = {}
            for line in lines:
                while True:
                    m = re.match(r'^([A-Za-z_.$][A-Za-z0-9_.$]*):\s*(.*)$', line)
                    if not m:
                        break
                    if not final:
                        self.syms[m.group(1)] = pc
                    line = m.group(2)
                if not line:
                    continue
                m = re.match(r'^([A-Za-z_.$][A-Za-z0-9_.$]*)\s+EQU\s+(.+)$', line, re.I)
                if m:
                    self.syms[m.group(1)] = self.ev(m.group(2), final)
                    continue
                head, _, rest = line.partition(' ')
                head_u = head.upper()
                rest = rest.strip()
                if head_u == 'ORG':
                    pc = self.ev(rest, final)
                    continue
                if head_u == 'DW':
                    for t in rest.split(','):
                        v = self.ev(t, final) & 0xFFFF
                        image[pc] = v & 0xFF
                        image[pc + 1] = v >> 8
                        pc += 2
                    continue
                if head_u == 'DB':
                    for t in rest.split(','):
                        image[pc] = self.ev(t, final) & 0xFF
                        pc += 1
                    continue
                ops = [o.strip() for o in re.split(r',(?![^\[]*\])', rest)] if rest else []
                if pc & 1:
                    raise AsmError('instruction at odd address %04X: %s' % (pc, line))
                try:
                    words = self.encode(head_u, ops, pc, final)
                except AsmError as ex:
                    raise AsmError('%s  [%s]' % (ex, line))
                for w in words:
                    image[pc] = w & 0xFF
                    image[pc + 1] = (w >> 8) & 0xFF
                    pc += 2
        return image


def to_bin(image, size=None):
    top = max(image) + 1
    if size:
        top = max(top, size)
    out = bytearray(b'\xFF' * top)
    for a, v in image.items():
        out[a] = v
    return bytes(out)


if __name__ == '__main__':
    src = open(sys.argv[1]).read()
    a = Assembler(sys.argv[3] if len(sys.argv) > 3 else 'nX-U8/100')   # usage: u8asm.py in.asm out.bin [core]
    img = a.assemble(src)
    open(sys.argv[2], 'wb').write(to_bin(img))
    print('%d bytes' % len(img))
