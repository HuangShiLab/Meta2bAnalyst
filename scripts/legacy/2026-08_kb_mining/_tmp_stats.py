import json
from collections import Counter

data = [json.loads(l) for l in open('knowledge_staging/associations.jsonl')]
print(f'Total associations: {len(data)}')
print(f'Quote verified: {sum(1 for d in data if d.get("quote_verified"))}')

conds = Counter(d.get('condition', 'unknown') for d in data)
print('Top conditions:', conds.most_common(8))

ranks = Counter(d.get('taxon_rank', 'unknown') for d in data)
print('Taxon ranks:', ranks.most_common())

dirs = Counter(d.get('direction', 'unknown') for d in data)
print('Directions:', dirs.most_common())
