import sys
sys.path.insert(0, '/Users/macstudio/Downloads/meta2banalyst/backend')
from scripts.literature_mine import extract_text
from pathlib import Path

for name in ['PMID39807439.pdf', 'PMID40654456.pdf']:
    p = Path(f'/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/{name}')
    try:
        t = extract_text(p)
        print(f'{name}: {len(t)} chars')
        print(f'  First 200 chars: {repr(t[:200])}')
        print(f'  Last 200 chars: {repr(t[-200:])}')
    except Exception as e:
        print(f'{name}: ERROR - {e}')
    print()
