#!/usr/bin/env python3
import os, subprocess, re

PMIDS_FILE = "/Users/macstudio/Downloads/meta2banalyst/backend/knowledge_staging/redownload_pmids_remaining.txt"
PDF_DIR = "/Users/macstudio/Downloads/oral-microbiome-data-collector/papers/pdfs"

pmids = [l.strip() for l in open(PMIDS_FILE) if l.strip()]
print("待重下载 PMID 数:", len(pmids))

removed = 0
kept = 0
not_found = 0

for pmid in pmids:
    files = [f for f in os.listdir(PDF_DIR) if re.match(r'PMID' + pmid + r'[_.]', f)]
    if not files:
        print(pmid, "-> NOT FOUND")
        not_found += 1
        continue
    for f in files:
        t = subprocess.run(['file', '-b', os.path.join(PDF_DIR, f)], capture_output=True, text=True).stdout
        is_pdf = t.startswith('PDF') or '%PDF' in t
        print(pmid, "->", f, ":", t.strip()[:50], "(PDF=" + str(is_pdf) + ")")
        if is_pdf:
            kept += 1
        else:
            os.remove(os.path.join(PDF_DIR, f))
            print("  删除假PDF:", f)
            removed += 1

print(f"总结: 保留真实PDF {kept} 个, 删除假PDF {removed} 个, 未找到 {not_found} 个")
