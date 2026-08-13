import { useCallback, useState } from "react";
import type { UploadFile } from "@/types";

export function useUpload() {
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [isUploading, setIsUploading] = useState(false);

  const uploadFiles = useCallback(
    async (acceptedFiles: File[]) => {
      setIsUploading(true);

      const newFiles: UploadFile[] = acceptedFiles.map((file) => ({
        id: crypto.randomUUID(),
        name: file.name,
        size: file.size,
        type: file.type,
        progress: 0,
        status: "pending",
      }));

      setFiles((prev) => [...prev, ...newFiles]);

      // TODO: Replace with actual upload logic
      for (const file of newFiles) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        setFiles((prev) =>
          prev.map((f) =>
            f.id === file.id ? { ...f, progress: 50, status: "uploading" as const } : f
          )
        );
        await new Promise((resolve) => setTimeout(resolve, 500));
        setFiles((prev) =>
          prev.map((f) =>
            f.id === file.id ? { ...f, progress: 100, status: "success" as const } : f
          )
        );
      }

      setIsUploading(false);
      return newFiles;
    },
    []
  );

  const removeFile = useCallback((fileId: string) => {
    setFiles((prev) => prev.filter((f) => f.id !== fileId));
  }, []);

  return { files, isUploading, uploadFiles, removeFile };
}
