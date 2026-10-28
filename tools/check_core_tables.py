"""check_core_tables.py - prove (from the two official manuals) that nX-U8/100 and nX-U16/100 share one encoding.

usage: python3 tools/check_core_tables.py "nX-U8100 Core Instruction Manual.pdf" 766922189-FEUL-U16-100-INST-03-vi.pdf
Needs `pdftotext` (poppler). Compares, from each manual's Chapter 4 appendix, every 16-bit opcode pattern
(first words, e.g. 1000_nnnn_mmmm_0001) and the number of flag columns marked '*' on that row.
Exit code 0 = identical, 1 = differ.
"""
import re
import subprocess
import sys

PAT = re.compile(r'([01a-zA-Z]{4}_[01a-zA-Z]{4}_[01a-zA-Z]{4}_[01a-zA-Z]{4})')


def appendix(pdf):
    txt = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True, check=True).stdout
    lines = txt.split('\n')
    start = max(i for i, l in enumerate(lines) if re.search(r'^\f?\s*4\.\s+(Appendix|Ph. l.c)', l))
    rows = []
    for l in lines[start:]:
        m = re.search(r'^(.*?)' + PAT.pattern, l)
        if m:
            rows.append((m.group(2), m.group(1).count('*')))
    return rows


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    u8, u16 = appendix(sys.argv[1]), appendix(sys.argv[2])
    print('U8 : %d rows, %d distinct patterns' % (len(u8), len({p for p, _ in u8})))
    print('U16: %d rows, %d distinct patterns' % (len(u16), len({p for p, _ in u16})))
    only8 = {p for p, _ in u8} - {p for p, _ in u16}
    only16 = {p for p, _ in u16} - {p for p, _ in u8}
    flagdiff = [(a, b) for a, b in zip(u8, u16) if a != b]
    print('patterns only in U8 :', sorted(only8) or 'none')
    print('patterns only in U16:', sorted(only16) or 'none')
    print('rows whose pattern/flag count differ:', flagdiff or 'none')
    ok = not only8 and not only16 and not flagdiff and len(u8) == len(u16)
    print('RESULT:', 'IDENTICAL - one encoder serves both cores' if ok else 'DIFFERENT - split the encoder per core')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
