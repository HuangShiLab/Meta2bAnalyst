import json, collections

n = qv = 0
conds = set()
taxa = set()
ranks = collections.Counter()
pmids = set()
papers = set()

with open('knowledge_staging/associations.jsonl') as fh:
    for line in fh:
        if not line.strip():
            continue
        rec = json.loads(line)
        n += 1
        if rec.get('quote_verified'):
            qv += 1
        conds.add(rec.get('condition', ''))
        taxa.add(rec.get('taxon', ''))
        ranks[rec.get('taxon_rank', 'unknown')] += 1
        pmids.add(rec.get('pmid'))
        papers.add(rec.get('paper') or rec.get('pmid'))

print(f'Total associations: {n}')
print(f'Quote-verified:     {qv} ({100*qv/n:.1f}%)')
print(f'Unique conditions:  {len(conds)}')
print(f'Unique taxa:        {len(taxa)}')
print(f'Unique PMIDs:       {len(pmids)}')
print(f'Papers represented: {len(papers)}')
print(f'Rank distribution:  {dict(ranks)}')
