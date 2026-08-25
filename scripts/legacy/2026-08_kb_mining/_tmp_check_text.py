from pypdf import PdfReader
import sys

for pmid in ['PMID38800100', 'PMID39378072', 'PMID39413077', 'PMID38448300']:
    try:
        r = PdfReader(f'/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/{pmid}.pdf')
        text = ''
        for page in r.pages[:25]:
            text += page.extract_text() or ''
        print(f'{pmid}: {len(text)} chars, {len(r.pages)} pages')
    except Exception as e:
        print(f'{pmid}: ERROR {e}')
