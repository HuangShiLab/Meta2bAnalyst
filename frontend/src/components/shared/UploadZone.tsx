import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileType, FileCheck2, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  onUpload?: (files: File[]) => void;
  /** Currently selected file; when set, the zone shows its name/size instead of the bare drop hint. */
  file?: File | null;
  accept?: Record<string, string[]>;
  className?: string;
}

const formatSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

export function UploadZone({
  onUpload,
  file = null,
  accept = {
    "text/csv": [".csv"],
    "text/tab-separated-values": [".tsv"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  },
  className,
}: UploadZoneProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      onUpload?.(acceptedFiles);
    },
    [onUpload]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
  });

  const clearFile = (e: React.MouseEvent) => {
    // Keep the dropzone click (file picker) from firing when clearing.
    e.stopPropagation();
    onUpload?.([]);
  };

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border p-8 transition-colors hover:bg-muted/50",
        isDragActive && "border-primary bg-primary/5",
        file && "border-green-500/60 bg-green-50/50",
        className
      )}
    >
      <input {...getInputProps()} />
      {file ? (
        <div className="flex w-full items-center gap-2">
          <FileCheck2 className="h-6 w-6 shrink-0 text-green-600" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-green-800" title={file.name}>
              {file.name}
            </p>
            <p className="text-xs text-muted-foreground">
              {formatSize(file.size)} — click to replace
            </p>
          </div>
          <button
            type="button"
            onClick={clearFile}
            className="shrink-0 rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Remove file"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : (
        <>
          <Upload className="h-8 w-8 text-muted-foreground" />
          <p className="mt-2 text-sm font-medium">
            {isDragActive ? "Drop files here" : "Drag & drop files here"}
          </p>
          <p className="text-xs text-muted-foreground">or click to browse</p>
          <div className="mt-4 flex gap-2">
            <FileType className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs text-muted-foreground">CSV, TSV, Excel</span>
          </div>
        </>
      )}
    </div>
  );
}
