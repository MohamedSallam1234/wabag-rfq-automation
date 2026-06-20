import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { Sparkles, UploadCloud, Loader2, Clock } from "lucide-react";

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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import { RfqSummaryCard } from "./RfqSummaryCard";
import { useGenerateRfq } from "@/hooks/use-rfqs";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";
import type { RfqGenerationResponse, Uuid } from "@/lib/api/types";

const ACCEPTED = ".pdf,.docx,.xlsx,.xls";

interface GenerateRfqDialogProps {
  projectId: Uuid;
}

/**
 * RFQ generation entry point. The backend POST is synchronous and long-running
 * (map-reduce over the project's documents, minutes per run) — the dialog
 * warns about that up front and shows a spinner while the request is open.
 */
export function GenerateRfqDialog({ projectId }: GenerateRfqDialogProps) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [equipment, setEquipment] = useState("");
  const [dragging, setDragging] = useState(false);
  const [result, setResult] = useState<RfqGenerationResponse | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const generate = useGenerateRfq(projectId);

  const reset = () => {
    setFile(null);
    setEquipment("");
    setResult(null);
  };

  const submit = async () => {
    if (!file) {
      toast.error("Select an RFQ template file");
      return;
    }
    if (!equipment.trim()) {
      toast.error("Enter the equipment name");
      return;
    }
    try {
      const res = await generate.mutateAsync({
        file,
        equipment: equipment.trim(),
      });
      setResult(res);
      toast.success("RFQ generated");
    } catch (err) {
      const message =
        err instanceof ApiError
          ? (err.detail ?? err.message)
          : "Generation failed";
      toast.error(message);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) reset();
      }}
    >
      <DialogTrigger asChild>
        <Button>
          <Sparkles className="h-4 w-4" />
          Generate RFQ
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Generate RFQ datasheet</DialogTitle>
          <DialogDescription>
            Upload an RFQ template and name the equipment. The system extracts
            specs from the project&apos;s documents and fills the template.
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <RfqSummaryCard summary={result.summary} />
        ) : (
          <div className="space-y-4">
            <Alert variant="warning">
              <Clock className="h-4 w-4" />
              <AlertTitle>This can take a while</AlertTitle>
              <AlertDescription>
                Generation runs several LLM calls over your project documents
                and may take 5–30 minutes. Keep this dialog open until it
                finishes.
              </AlertDescription>
            </Alert>

            <div className="space-y-2">
              <Label htmlFor="rfq-equipment">Equipment</Label>
              <Input
                id="rfq-equipment"
                placeholder="e.g. RAS Pump, Aeration Blower, Mixer"
                value={equipment}
                onChange={(e) => setEquipment(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label>RFQ template</Label>
              <div
                role="button"
                tabIndex={0}
                onClick={() => inputRef.current?.click()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ")
                    inputRef.current?.click();
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
                className={cn(
                  "flex cursor-pointer flex-col items-center justify-center gap-1 rounded-control border-2 border-dashed p-6 text-center transition-colors",
                  dragging
                    ? "border-info bg-info-soft/50"
                    : "border-border-strong hover:border-info/60",
                )}
              >
                <UploadCloud className="h-6 w-6 text-text-muted" />
                {file ? (
                  <p className="text-sm font-medium text-text-primary">
                    {file.name}
                  </p>
                ) : (
                  <p className="text-sm text-text-muted">
                    Drop the template here or click to browse
                  </p>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept={ACCEPTED}
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) setFile(f);
                    e.target.value = "";
                  }}
                />
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          {result ? (
            <Button type="button" onClick={() => reset()}>
              Generate another
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
                disabled={generate.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                onClick={() => void submit()}
                disabled={generate.isPending}
              >
                {generate.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Generating…
                  </>
                ) : (
                  "Generate"
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
