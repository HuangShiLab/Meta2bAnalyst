import os
pdf_dir = '/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs'
done_dir = 'knowledge_staging/papers'
pdfs = set(os.path.splitext(f)[0] for f in os.listdir(pdf_dir) if f.endswith('.pdf'))
done = set(os.path.splitext(f)[0] for f in os.listdir(done_dir) if f.endswith('.json'))
print(f'PDFs: {len(pdfs)}, Done: {len(done)}, New: {len(pdfs - done)}')
if pdf_done := (pdfs - done):
    print('Unprocessed:')
    for f in sorted(pdf_done):
        print(' ', f)
