/**
 * Client-side figure export: PNG / SVG / real PDF.
 *
 * The old downloadFigure was a placeholder (href="#") and downloadPDF posted
 * to a backend /export/pdf route that does not exist, silently falling back
 * to an SVG download. Server-side rasterization is not an option on this
 * intranet deployment (Kaleido needs Chrome, which the backend image lacks),
 * so everything happens in the browser: plotly.js (dynamically imported, so
 * the multi-megabyte library stays out of the main bundle until the first
 * export) renders the figure offscreen, and the PDF path wraps a rasterized
 * JPEG in a minimal single-page PDF written by hand -- no PDF dependency.
 */
import type { PlotlyFigure } from "@/types";

async function renderFigureImage(
  figure: { data?: unknown[]; layout?: Record<string, unknown> },
  format: "png" | "svg" | "jpeg",
  scale = 2,
): Promise<string> {
  // dist UMD bundle: the package source entry needs node buffer polyfills
  // that vite does not provide.
  const Plotly = (await import("plotly.js/dist/plotly.min.js")).default;
  const holder = document.createElement("div");
  holder.style.position = "fixed";
  holder.style.left = "-10000px";
  holder.style.width = "1000px";
  holder.style.height = "640px";
  document.body.appendChild(holder);
  try {
    await Plotly.newPlot(
      holder,
      figure.data as never[],
      {
        ...(figure.layout as object),
        width: 1000,
        height: 640,
        autosize: false,
      } as never,
      { staticPlot: true } as never,
    );
    return await Plotly.toImage(holder, { format, width: 1000, height: 640, scale });
  } finally {
    Plotly.purge(holder);
    document.body.removeChild(holder);
  }
}

function triggerDownload(href: string, filename: string): string {
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  return href;
}

/** Wrap JPEG bytes in a minimal valid single-page PDF (DCTDecode XObject). */
export function jpegToPdfBytes(jpeg: Uint8Array, widthPx: number, heightPx: number): Uint8Array {
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  const offsets: number[] = [];
  let length = 0;
  const push = (chunk: string | Uint8Array) => {
    const bytes = typeof chunk === "string" ? enc.encode(chunk) : chunk;
    parts.push(bytes);
    length += bytes.length;
  };
  const obj = (body: string) => {
    offsets.push(length);
    push(body);
  };

  push("%PDF-1.4\n");
  obj("1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n");
  obj("2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n");
  const W = Math.round(widthPx / 2);
  const H = Math.round(heightPx / 2);
  obj(
    `3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 ${W} ${H}]` +
      `/Resources<</XObject<</Im0 4 0 R>>>>/Contents 5 0 R>>endobj\n`,
  );

  const jpegHeader =
    `4 0 obj<</Type/XObject/Subtype/Image/Width ${widthPx}/Height ${heightPx}` +
    `/ColorSpace/DeviceRGB/BitsPerComponent 8/Filter/DCTDecode/Length ${jpeg.length}>>stream\n`;
  const jpegFooter = "\nendstream endobj\n";
  offsets.push(length);
  push(jpegHeader);
  push(jpeg);
  push(jpegFooter);

  const content = `q ${W} 0 0 ${H} 0 0 cm /Im0 Do Q`;
  obj(`5 0 obj<</Length ${content.length}>>stream\n${content}\nendstream endobj\n`);

  const xrefStart = length;
  let xref = `xref\n0 ${offsets.length + 1}\n0000000000 65535 f \n`;
  for (const off of offsets) {
    xref += `${String(off).padStart(10, "0")} 00000 n \n`;
  }
  push(xref);
  push(`trailer<</Size ${offsets.length + 1}/Root 1 0 R>>\nstartxref\n${xrefStart}\n%%EOF`);

  const out = new Uint8Array(length);
  let pos = 0;
  for (const part of parts) {
    out.set(part, pos);
    pos += part.length;
  }
  return out;
}

export async function downloadFigure(
  figure: { data?: unknown[]; layout?: Record<string, unknown> } | undefined,
  format: "png" | "svg" | "jpeg",
): Promise<void> {
  if (!figure) return;
  try {
    const dataUrl = await renderFigureImage(figure, format);
    triggerDownload(dataUrl, `figure.${format}`);
  } catch (error) {
    console.error("Figure export failed:", error);
    alert(`Figure export failed: ${error instanceof Error ? error.message : String(error)}`);
  }
}

export async function downloadFigurePdf(
  figure: PlotlyFigure | { data?: unknown[]; layout?: Record<string, unknown> } | undefined,
  filename: string,
): Promise<void> {
  if (!figure) return;
  try {
    const pngUrl = await renderFigureImage(figure, "png", 2);
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("could not rasterize the figure"));
      img.src = pngUrl;
    });
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas unavailable");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    const jpegUrl = canvas.toDataURL("image/jpeg", 0.92);
    const base64 = jpegUrl.slice(jpegUrl.indexOf(",") + 1);
    const binary = atob(base64);
    const jpeg = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) jpeg[i] = binary.charCodeAt(i);
    const pdf = jpegToPdfBytes(jpeg, canvas.width, canvas.height);
    const blob = new Blob([pdf as BlobPart], { type: "application/pdf" });
    const url = triggerDownload(
      URL.createObjectURL(blob),
      filename.endsWith(".pdf") ? filename : `${filename}.pdf`,
    );
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (error) {
    console.error("PDF export failed:", error);
    alert(`PDF export failed: ${error instanceof Error ? error.message : String(error)}`);
  }
}
