import os, glob, re, json

pdfs = []
for f in glob.glob('/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs/*.pdf'):
    m = re.match(r'PMID\d+', os.path.basename(f))
    if m:
        pdfs.append(m.group(0))

jsons = []
for f in glob.glob('knowledge_staging/papers/*.json'):
    m = re.match(r'PMID\d+', os.path.basename(f))
    if m:
        jsons.append(m.group(0))

failed = [d.get('file', '').replace('.pdf', '') for d in json.load(open('knowledge_staging/failed.json'))]
failed_pmids = []
for f in failed:
    m = re.match(r'PMID\d+', f)
    if m:
        failed_pmids.append(m.group(0))

pdf_set = set(pdfs)
json_set = set(jsons)
failed_set = set(failed_pmids)

print(f'Total PDFs: {len(pdf_set)}')
print(f'Processed (has JSON): {len(json_set)}')
print(f'Failed: {len(failed_set)}')
unproc = sorted(pdf_set - json_set - failed_set)
print(f'Unprocessed: {len(unproc)}')
if unproc:
    print('Unprocessed PMIDs:', unproc)
else:
    print('All PDFs have been attempted!')

# Check overlap
overlap = json_set & failed_set
if overlap:
    print(f'Warning: {len(overlap)} in both processed and failed:', overlap)
