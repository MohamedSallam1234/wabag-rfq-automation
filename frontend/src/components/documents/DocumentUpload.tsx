import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useUploadDocument } from "@/hooks/use-documents";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { Uuid } from "@/lib/api/types";

const ACCEPTED = ".pdf,.docx,.xlsx,.xls";

interface DocumentUploadProps {
  projectId: Uuid;
}

/** Drag-and-drop + click-to-pick file uploader (single file at a time). */
export function DocumentUpload({ projectId }: DocumentUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useUploadDocument(projectId);

  const submit = async (file: File) => {
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (![".pdf", ".docx", ".xlsx", ".xls"].includes(ext)) {
      toast.error(`Unsupported file type: ${ext || "(none)"}`);
      return;
    }
    try {
      await upload.mutateAsync(file);
      toast.success(`Uploaded ${file.name}`);
    } catch (err) {
      const message =
        err instanceof ApiError ? (err.detail ?? err.message) : "Upload failed";
      toast.error(message);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void submit(file);
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => inputRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-control border-2 border-dashed p-8 text-center transition-colors",
        dragging
          ? "border-info bg-info-soft/50"
          : "border-border-strong hover:border-info/60",
      )}
    >
      <UploadCloud className="h-8 w-8 text-text-muted" />
      <p className="text-sm font-medium text-text-primary">
        Drop a file here, or click to browse
      </p>
      <p className="text-xs text-text-muted">
        One file at a time. PDF, DOCX, XLSX, XLS.
      </p>
      {upload.isPending && <p className="text-xs text-info">Uploading…</p>}
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void submit(file);
          e.target.value = "";
        }}
      />
      <Button type="button" variant="secondary" size="sm" className="mt-2">
        Choose file
      </Button>
    </div>
  );
}
