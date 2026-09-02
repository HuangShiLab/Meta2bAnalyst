/**
 * Demo datasets served as static files from /examples/demo/<id>/.
 *
 * Four categories matching sample_data/: single-omics (microbiome,
 * metabolome), multi-omics, and multi-site-multi-omics. Loading a dataset
 * creates a fresh session and uploads every file with its declared file_type,
 * so the Agent / analysis pages can run immediately.
 */

import { authHeaders } from "@/utils/api";

export interface DemoFile {
  /** File name under /examples/demo/<datasetId>/ */
  name: string;
  /** Backend upload file_type (microbiome | metabolome | metadata | ...) */
  fileType: string;
}

export interface DemoDataset {
  id: "microbiome" | "metabolome" | "multi-omics" | "multi-site-multi-omics";
  label: string;
  description: string;
  sessionName: string;
  files: DemoFile[];
}

export const DEMO_DATASETS: DemoDataset[] = [
  {
    id: "microbiome",
    label: "Microbiome",
    description: "Huang mBio 2021 · 261-sample genus abundance table + metadata (20 clinical/visit variables)",
    sessionName: "Demo - Microbiome (mBio 2021)",
    files: [
      { name: "Matched_microbes_abd_261.tsv", fileType: "microbiome" },
      { name: "Matched_metadata_261.tsv", fileType: "metadata" },
    ],
  },
  {
    id: "metabolome",
    label: "Metabolome",
    description: "Huang mBio 2021 · 261-sample metabolite abundance table + metadata",
    sessionName: "Demo - Metabolome (mBio 2021)",
    files: [
      { name: "Matched_metabolites_abd_261.txt", fileType: "metabolome" },
      { name: "Matched_metabolites_metadata_261.txt", fileType: "metadata" },
    ],
  },
  {
    id: "multi-omics",
    label: "Multi-omics",
    description: "Microbiome + metabolome (2 files each); merged 20-column metadata uploaded last as the unified metadata",
    sessionName: "Demo - Multi-omics (mBio 2021)",
    files: [
      { name: "Matched_microbes_abd_261.tsv", fileType: "microbiome" },
      { name: "Matched_metabolites_abd_261.txt", fileType: "metabolome" },
      { name: "Matched_metabolites_metadata_261.txt", fileType: "metadata" },
      { name: "Matched_metadata_261.tsv", fileType: "metadata" },
    ],
  },
  {
    id: "multi-site-multi-omics",
    label: "Multi-site Multi-omics",
    description: "Saliva + urine: GTDB microbiome tables, neg/pos metabolome tables and per-site metadata (8 files)",
    sessionName: "Demo - Multi-site Multi-omics",
    files: [
      { name: "Urine_microbiome_GTDB_abd.txt", fileType: "microbiome" },
      { name: "Saliva_microbiome_GTDB_abd.txt", fileType: "microbiome" },
      { name: "metabolome_neg_urin_renamed.csv", fileType: "metabolome" },
      { name: "metabolome_pos_urin_renamed.csv", fileType: "metabolome" },
      { name: "metabolome_neg_saliva_renamed.csv", fileType: "metabolome" },
      { name: "metabolome_pos_saliva_renamed.csv", fileType: "metabolome" },
      { name: "Urine_metadata.txt", fileType: "metadata" },
      { name: "Saliva_metadata.txt", fileType: "metadata" },
    ],
  },
];

/**
 * Create a new session and upload every file of the dataset into it.
 * Returns the new session id. onProgress receives 1-based file counts.
 */
export async function loadDemoDataset(
  dataset: DemoDataset,
  onProgress?: (done: number, total: number, currentFile: string) => void,
): Promise<string> {
  const sessionRes = await fetch("/api/v1/sessions", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ name: dataset.sessionName }),
  });
  if (!sessionRes.ok) {
    throw new Error(`Failed to create demo session (HTTP ${sessionRes.status})`);
  }
  const session = (await sessionRes.json()) as { id: string };

  for (let i = 0; i < dataset.files.length; i++) {
    const f = dataset.files[i];
    onProgress?.(i, dataset.files.length, f.name);
    const fileRes = await fetch(
      `/examples/demo/${dataset.id}/${encodeURIComponent(f.name)}`,
    );
    if (!fileRes.ok) {
      throw new Error(`Failed to load demo file: ${f.name} (HTTP ${fileRes.status})`);
    }
    const blob = await fileRes.blob();
    const form = new FormData();
    form.append("file_type", f.fileType);
    form.append("file", blob, f.name);
    const uploadRes = await fetch(`/api/v1/sessions/${session.id}/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    });
    if (!uploadRes.ok) {
      const detail = await uploadRes.text().catch(() => "");
      throw new Error(`Failed to upload ${f.name} (HTTP ${uploadRes.status}) ${detail.slice(0, 200)}`);
    }
  }
  onProgress?.(dataset.files.length, dataset.files.length, "");
  return session.id;
}
