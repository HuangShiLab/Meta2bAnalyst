import os, glob, sys

pdf_dir = os.path.expanduser("~/Downloads/oral-microbiome-data-collector/papers/pdfs")
done_dir = os.path.expanduser("~/Downloads/meta2banalyst/backend/knowledge_staging/papers")

pdfs = sorted([os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(pdf_dir, "*.pdf"))])
done = sorted([os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(done_dir, "*.json"))])

todo = [p for p in pdfs if p not in done]
print(f"PDFs: {len(pdfs)}, Done: {len(done)}, Todo: {len(todo)}")
for t in todo[:10]:
    print(f"  + {t}")
