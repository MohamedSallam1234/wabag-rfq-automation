import { useState } from "react";
import { toast } from "sonner";
import { Download, Trash2, FileText, Sheet, File } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

import { ClassificationBadge } from "./ClassificationBadge";
import { OverrideClassDialog } from "./OverrideClassDialog";
import { useDeleteDocument } from "@/hooks/use-documents";
import { getDocument } from "@/lib/api/documents";
import { ApiError } from "@/lib/api/client";
import {
  GENERATED_DOC_TYPE,
  type DocumentRead,
  type Uuid,
} from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/utils";

interface DocumentTableProps {
  projectId: Uuid;
  documents?: DocumentRead[];
  isLoading: boolean;
}

function fileIcon(contentType: string) {
  if (contentType.includes("sheet") || contentType.includes("excel")) {
    return <Sheet className="h-4 w-4" />;
  }
  if (contentType.includes("pdf")) {
    return <FileText className="h-4 w-4" />;
  }
  return <File className="h-4 w-4" />;
}

/** Download handler: fetch the signed URL via getDocument, then open it. */
async function handleDownload(documentId: Uuid) {
  try {
    const detail = await getDocument(documentId);
    // Signed URLs point at Supabase Storage; opening in a new tab sidesteps any
    // cross-origin restriction on a programmatic <a download> click.
    window.open(detail.download_url, "_blank", "noopener,noreferrer");
  } catch (err) {
    const message =
      err instanceof ApiError
        ? (err.detail ?? err.message)
        : "Could not fetch download URL";
    toast.error(message);
  }
}

/** Table of a project's documents with per-row actions. */
export function DocumentTable({
  projectId,
  documents,
  isLoading,
}: DocumentTableProps) {
  const deleteDocument = useDeleteDocument(projectId);
  const [toDelete, setToDelete] = useState<DocumentRead | null>(null);

  const confirmDelete = async () => {
    if (!toDelete) return;
    try {
      await deleteDocument.mutateAsync(toDelete.id);
      toast.success(`Deleted ${toDelete.original_filename}`);
    } catch (err) {
      const message =
        err instanceof ApiError ? (err.detail ?? err.message) : "Delete failed";
      toast.error(message);
    } finally {
      setToDelete(null);
    }
  };

  return (
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40%]">File</TableHead>
            <TableHead>Classification</TableHead>
            <TableHead>Revision</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Uploaded</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <TableRow key={i}>
                {Array.from({ length: 6 }).map((__, j) => (
                  <TableCell key={j}>
                    <Skeleton className="h-5 w-full" />
                  </TableCell>
                ))}
              </TableRow>
            ))}

          {!isLoading && documents?.length === 0 && (
            <TableRow>
              <TableCell
                colSpan={6}
                className="py-10 text-center text-muted-foreground"
              >
                No documents uploaded yet.
              </TableCell>
            </TableRow>
          )}

          {!isLoading &&
            documents?.map((doc) => {
              const isGenerated = doc.doc_type === GENERATED_DOC_TYPE;
              const pagesOrSheets =
                doc.page_count != null
                  ? `${doc.page_count}p`
                  : doc.sheet_names && doc.sheet_names.length > 0
                    ? `${doc.sheet_names.length} sheet${doc.sheet_names.length > 1 ? "s" : ""}`
                    : null;
              return (
                <TableRow key={doc.id}>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      {fileIcon(doc.content_type)}
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          {doc.original_filename}
                        </p>
                        {pagesOrSheets && (
                          <p className="text-xs text-muted-foreground">
                            {pagesOrSheets}
                          </p>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <ClassificationBadge
                      docType={doc.doc_type}
                      source={doc.doc_type_source}
                    />
                  </TableCell>
                  <TableCell>
                    {doc.revision_label ? (
                      <span className="font-mono text-xs">
                        {doc.revision_label}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatBytes(doc.size_bytes)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(doc.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => void handleDownload(doc.id)}
                        aria-label="Download"
                      >
                        <Download className="h-3.5 w-3.5" />
                      </Button>
                      {!isGenerated && (
                        <OverrideClassDialog
                          projectId={projectId}
                          documentId={doc.id}
                          currentDocType={doc.doc_type}
                        />
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-destructive hover:text-destructive"
                        onClick={() => setToDelete(doc)}
                        aria-label="Delete"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
        </TableBody>
      </Table>

      <Dialog
        open={Boolean(toDelete)}
        onOpenChange={(o) => !o && setToDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete document?</DialogTitle>
            <DialogDescription>
              {toDelete?.original_filename} will be removed from the project and
              its stored artifact deleted. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setToDelete(null)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => void confirmDelete()}
              disabled={deleteDocument.isPending}
            >
              {deleteDocument.isPending ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
