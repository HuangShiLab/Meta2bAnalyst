#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/shihuang/Documents/kimi/workspace/meta2banalyst/backend')

from app.knowledge import lookup_taxon, lookup_method, lookup_disease, fuzzy_lookup_taxon

t = lookup_taxon('Faecalibacterium_prausnitzii')
print('Taxon OK:', t['name'] if t else 'FAIL')
print('  Functions:', t.get('known_functions', [])[:3] if t else [])

m = lookup_method('permanova')
print('Method OK:', m['name'] if m else 'FAIL')
print('  Cautions count:', len(m.get('cautions', [])) if m else 0)

d = lookup_disease('dysbiosis')
print('Disease OK:', d['name'] if d else 'FAIL')
print('  Key genera count:', len(d.get('key_genera', [])) if d else 0)

f = fuzzy_lookup_taxon('Faecalibacterium')
print('Fuzzy OK:', len(f), 'matches')
