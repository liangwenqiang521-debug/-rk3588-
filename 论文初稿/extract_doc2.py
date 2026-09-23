import olefile, sys

path = sys.argv[1]
ole = olefile.OleFileIO(path)
data = ole.openstream('WordDocument').read()
ole.close()

# Try UTF-16LE decode of whole stream, keep printable chars
try:
    txt = data.decode('utf-16-le', errors='replace')
except Exception:
    txt = ''

keep = []
for ch in txt:
    o = ord(ch)
    if ch in '\r\n\t ':
        keep.append('\n' if ch in '\r\n' else ch)
    elif 0x20 <= o <= 0x7E:
        keep.append(ch)
    elif 0x4E00 <= o <= 0x9FFF:   # CJK
        keep.append(ch)
    elif 0x3000 <= o <= 0x303F:   # CJK punctuation
        keep.append(ch)
    elif 0xFF00 <= o <= 0xFFEF:   # fullwidth forms
        keep.append(ch)
    elif 0x2010 <= o <= 0x205F:
        keep.append(ch)
    elif 0x2022 == o or 0x2014 == o or 0x2018<=o<=0x201F:
        keep.append(ch)
    elif ch == '—' or ch == '–' or ch == '‘' or ch == '’' or ch == '"' or ch=='"':
        keep.append(ch)
    else:
        # collapse runs of junk
        if keep and keep[-1] != ' ':
            keep.append(' ')
out = ''.join(keep)
# collapse multiple spaces
import re
out = re.sub(r' {2,}', ' ', out)
out = re.sub(r'\n{3,}', '\n\n', out)
print(out[:40000])
