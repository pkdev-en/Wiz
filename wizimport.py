import os
import re

IMPORT_RE = re.compile(r'^(?:import\s+([A-Za-z_][\w.]*)|from\s+([A-Za-z_][\w.]*)\s+import\s+\S.*?)\s*(?:#.*)?$')
EXTS = ('.wz', '.cw', '')

LINEMAP = []


def _find(name, dirs):
    rel = name.replace('.', os.sep)
    for d in dirs:
        for ext in EXTS:
            p = os.path.join(d, rel + ext)
            if os.path.isfile(p):
                return os.path.abspath(p)
    return None


def expand_imports(text, target, path=None, error=ValueError):
    from targets import select_sections, SectionError
    main_path = os.path.abspath(path) if path else None
    main_dir = os.path.dirname(main_path) if main_path else os.getcwd()
    main_name = os.path.basename(path) if path else '<source>'
    seen = {main_path} if main_path else set()
    out, linemap = [], []

    def add(text, fname, cur_dir):
        for i, raw in enumerate(text.split('\n'), 1):
            m = IMPORT_RE.match(raw) if raw[:1] not in (' ', '\t', '') else None
            if not m:
                out.append(raw)
                linemap.append((fname, i, raw))
                continue
            name = m.group(1) or m.group(2)
            found = _find(name, [cur_dir, main_dir])
            if found is None:
                tried = ', '.join(name.replace('.', os.sep) + e for e in EXTS if e)
                raise error('%s line %d: cannot import %r (looked for %s next to %s)' % (fname, i, name, tried, fname))
            out.append('')
            linemap.append((fname, i, raw))
            if found in seen:
                continue
            seen.add(found)
            sub = open(found, encoding='utf8').read().replace('\r', '')
            try:
                sub = select_sections(sub, target)
            except SectionError as e:
                raise error('%s: %s' % (os.path.basename(found), e))
            add(sub, os.path.basename(found), os.path.dirname(found))

    add(text, main_name, main_dir)
    LINEMAP[:] = linemap
    return '\n'.join(out)


def describe_line(n):
    if 1 <= n <= len(LINEMAP):
        return LINEMAP[n - 1]
    return None
