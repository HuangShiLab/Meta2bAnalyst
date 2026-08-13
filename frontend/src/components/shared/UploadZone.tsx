import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileType } from "lucide-react";
import { cn } from "@/lib/utils";

interface UploadZoneProps {
  onUpload?: (files: File[]) => void;
  accept?: Record<string, string[]>;
  className?: string;
}

export function UploadZone({
  onUpload,
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

  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border p-8 transition-colors hover:bg-muted/50",
        isDragActive && "border-primary bg-primary/5",
        className
      )}
    >
      <input {...getInputProps()} />
      <Upload className="h-8 w-8 text-muted-foreground" />
      <p className="mt-2 text-sm font-medium">
        {isDragActive ? "Drop files here" : "Drag & drop files here"}
      </p>
      <p className="text-xs text-muted-foreground">or click to browse</p>
      <div className="mt-4 flex gap-2">
        <FileType className="h-4 w-4 text-muted-foreground" />
        <span className="text-xs text-muted-foreground">CSV, TSV, Excel</span>
      </div>
    </div>
  );
}
