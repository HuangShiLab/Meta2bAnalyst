#!/usr/bin/env python3
from pypdf import PdfReader
import os

os.chdir('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs')
files = ['PMID39525937.pdf','PMID39807439.pdf','PMID40496020.pdf','PMID40601605.pdf','PMID40654456.pdf']
for f in files:
    try:
        pages = len(PdfReader(f).pages)
        print(f, pages, 'pages')
    except Exception as e:
        print(f, 'ERROR:', e)
