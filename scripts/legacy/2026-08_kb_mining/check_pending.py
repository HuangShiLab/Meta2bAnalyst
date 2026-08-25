#!/usr/bin/env python3
from pathlib import Path

pdf_dir = Path('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs')
papers_dir = Path('/Users/macstudio/Downloads/meta2banalyst/backend/knowledge_staging/papers')

pdfs = sorted(pdf_dir.glob('*.pdf'))
remaining = [p for p in pdfs if not (papers_dir / f'{p.stem}.json').exists()]

print('总PDF数:', len(pdfs))
print('未处理PDF数:', len(remaining))
for r in remaining[:15]:
    print(' ', r.name)
