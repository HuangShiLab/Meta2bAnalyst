import json, glob

papers_with_assoc = set()
for line in open('knowledge_staging/associations.jsonl'):
    if line.strip():
        papers_with_assoc.add(json.loads(line)['pmid'])

all_papers = set()
for f in glob.glob('knowledge_staging/papers/*.json'):
    rec = json.load(open(f))
    all_papers.add(rec.get('pmid') or rec.get('source_file'))

print(f'Papers with associations: {len(papers_with_assoc)}')
print(f'Total papers processed:   {len(all_papers)}')
print(f'Papers with zero assoc:   {len(all_papers - papers_with_assoc)}')
