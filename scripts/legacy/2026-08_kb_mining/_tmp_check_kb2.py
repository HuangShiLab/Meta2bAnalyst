import json

tdb = json.load(open('app/knowledge/taxon_db.json'))
print(f'taxon_db entries: {len(tdb)}')

# Count disease_associations and disease_evidence
total_assocs = 0
total_ev = 0
for taxon, data in tdb.items():
    total_assocs += len(data.get('disease_associations', {}))
    for ev_list in data.get('disease_evidence', {}).values():
        total_ev += len(ev_list)

print(f'Total disease_associations in KB: {total_assocs}')
print(f'Total evidence records: {total_ev}')

# Count literature_evidence in disease_db
ddb = json.load(open('app/knowledge/disease_db.json'))
print(f'disease_db entries: {len(ddb)}')

db_ev = 0
for disease, data in ddb.items():
    for ev_list in data.get('literature_evidence', {}).values():
        db_ev += len(ev_list)
print(f'Literature evidence in disease_db: {db_ev}')
