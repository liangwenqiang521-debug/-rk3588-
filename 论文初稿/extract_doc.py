import olefile, sys, re

path = sys.argv[1]
ole = olefile.OleFileIO(path)
# locate WordDocument stream
wdf = ole.openstream('WordDocument')
data = wdf.read()
ole.close()

# FIB: nFib at 0x02
nFib = int.from_bytes(data[0x02:0x04], 'little')
fcClx = int.from_bytes(data[0x01A2:0x01A6], 'little')
lcbClx = int.from_bytes(data[0x01A6:0x01AA], 'little')
fcMin = int.from_bytes(data[0x0018:0x001C], 'little')
ccpText = int.from_bytes(data[0x004C:0x0050], 'little')
print(f"nFib={nFib:#06x} fcClx={fcClx} lcbClx={lcbClx} fcMin={fcMin} ccpText={ccpText}")

# Parse CLX to find piece table (Pcdt)
clx = data[fcClx:fcClx+lcbClx]
# CLX = sequence of Prc (0x01) then Pcdt (0x02)
i = 0
pieces = []
while i < len(clx):
    t = clx[i]
    if t == 0x01:
        cb = int.from_bytes(clx[i+1:i+3], 'little')
        i += 3 + cb
    elif t == 0x02:
        # Pcdt: PlcPcd = array of CPs (4 bytes each) then array of PCD (8 bytes each)
        # number of pieces = (n-1)
        plc = clx[i+1:]
        # each CP 4 bytes, then PCDs 8 bytes
        # Determine count
        n = (len(plc)) // (4 + 8)
        # Actually PlcPcd: (n+1) CPs and n PCDs => total = (n+1)*4 + n*8 = 12n+4 => n = (len-4)/12
        n = (len(plc) - 4) // 12
        for k in range(n):
            cp = int.from_bytes(plc[4*k:4*k+4], 'little')
            pcd_off = 4*(n+1) + 8*k
            pcd = plc[pcd_off:pcd_off+8]
            fc = int.from_bytes(pcd[2:6], 'little')
            fCompressed = (pcd[6] & 0x01) == 1
            fcReal = (fc & 0x3FFFFFFF) >> 1  # fc >> 1, mask high bits
            pieces.append((cp, fcReal, fCompressed))
        break
    else:
        break

print(f"pieces found: {len(pieces)}")
text_parts = []
for idx,(cp, fc, comp) in enumerate(pieces):
    if idx+1 < len(pieces):
        cp_end = pieces[idx+1][0]
    else:
        cp_end = ccpText
    length = cp_end - cp
    if comp:
        # 1 byte per char (CP 1252/ANSI), but for CJK word uses... actually compressed=ANSI
        seg = data[fc:fc+length]
        text_parts.append(seg.decode('cp1252', errors='replace'))
    else:
        # UTF-16LE, length*2 bytes
        seg = data[fc:fc+length*2]
        text_parts.append(seg.decode('utf-16-le', errors='replace'))

full = ''.join(text_parts)
# Normalize paragraph marks
full = full.replace('\r', '\n')
print("==== TEXT DUMP (first 60000 chars) ====")
print(full[:60000])
