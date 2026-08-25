from pypdf import PdfReader
import sys
for pmid in ['PMID38355866', 'PMID38448300', 'PMID38800100']:
    try:
        r = PdfReader(f'/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/{pmid}.pdf')
        print(f'{pmid}: pages={len(r.pages)}')
    except Exception as e:
        print(f'{pmid}: ERROR {e}')
