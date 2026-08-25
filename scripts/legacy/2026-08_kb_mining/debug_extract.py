#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/macstudio/Downloads/meta2banalyst/backend')
from scripts.literature_mine import extract_text
from pathlib import Path

p = Path('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/PMID39807439.pdf')
t = extract_text(p)
print('文本长度:', len(t))
print('前500字符:')
print(t[:500])
print('---')
print('最后200字符:')
print(t[-200:])
