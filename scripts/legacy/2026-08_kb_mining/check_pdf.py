import glob, os
files = sorted(glob.glob('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/*.pdf'))
bad, good = [], []
for f in files:
    if os.path.isdir(f):
        continue
    with open(f, 'rb') as fh:
        if fh.read(5) != b'%PDF-':
            bad.append(os.path.basename(f))
        else:
            good.append(os.path.basename(f))
print(f"total={len(files)} good={len(good)} bad={len(bad)}")
for b in bad:
    print(f"BAD: {b}")
