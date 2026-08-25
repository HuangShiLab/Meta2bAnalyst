import os, pathlib
pdfs=set(p.stem for p in pathlib.Path('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs').glob('*.pdf'))
done=set(p.stem for p in pathlib.Path('knowledge_staging/papers').glob('*.json'))
todo=sorted(pdfs-done)
print(f'Total PDFs: {len(pdfs)}')
print(f'Processed: {len(done)}')
print(f'Remaining: {len(todo)}')
print()
for t in todo:
    print(t)
