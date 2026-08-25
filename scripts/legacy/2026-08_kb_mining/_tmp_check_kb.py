import json

db = json.load(open('app/knowledge/disease_db.json'))
print(f'disease_db entries: {len(db)}')
print('Sample keys:', list(db.keys())[:5])

tdb = json.load(open('app/knowledge/taxon_db.json'))
print(f'taxon_db entries: {len(tdb)}')
total_assocs = sum(len(v.get('associations', [])) for v in tdb.values())
print(f'Total associations in KB: {total_assocs}')
total_ev = sum(len(v.get('evidence', [])) for v in tdb.values())
print(f'Total evidence records: {total_ev}')
