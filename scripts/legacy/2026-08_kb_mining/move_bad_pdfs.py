import glob, os, shutil
src='/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs'
dst='/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs_bad'
os.makedirs(dst, exist_ok=True)
n=0
for f in sorted(glob.glob(src+'/*.pdf')):
    if os.path.isdir(f):
        continue
    with open(f, 'rb') as fh:
        if fh.read(5) != b'%PDF-':
            shutil.move(f, os.path.join(dst, os.path.basename(f)))
            print('moved:', os.path.basename(f))
            n += 1
print(f'total moved: {n}')
