import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Pencil } from "lucide-react";

import { useUpdateDocumentClassification } from "@/hooks/use-documents";
import { DOC_TYPES, type DocType, type Uuid } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";

interface OverrideClassDialogProps {
  projectId: Uuid;
  documentId: Uuid;
  currentDocType: string | null;
}

/** Lets an engineer manually override a document's classification. */
export function OverrideClassDialog({
  projectId,
  documentId,
  currentDocType,
}: OverrideClassDialogProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState<DocType | null>(
    (DOC_TYPES as readonly string[]).includes(currentDocType ?? "")
      ? (currentDocType as DocType)
      : null,
  );
  const mutation = useUpdateDocumentClassification(projectId);

  const handleSave = async () => {
    if (!value) {
      toast.error("Select a document type");
      return;
    }
    try {
      await mutation.mutateAsync({
        documentId,
        update: { doc_type: value },
      });
      toast.success("Classification updated");
      setOpen(false);
    } catch (err) {
      const message =
        err instanceof ApiError ? (err.detail ?? err.message) : "Update failed";
      toast.error(message);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="iconSm">
          <Pencil className="h-3.5 w-3.5" />
          <span className="sr-only">Override classification</span>
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Override classification</DialogTitle>
          <DialogDescription>
            Select the correct document type. This marks the classification
            source as manual.
          </DialogDescription>
        </DialogHeader>
        <Select
          value={value ?? undefined}
          onValueChange={(v) => setValue(v as DocType)}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select document type" />
          </SelectTrigger>
          <SelectContent>
            {DOC_TYPES.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
