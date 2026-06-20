import { useParams, Link } from "react-router-dom";
import { ChevronLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DocumentUpload } from "@/components/documents/DocumentUpload";
import { DocumentTable } from "@/components/documents/DocumentTable";
import { GenerateRfqDialog } from "@/components/rfqs/GenerateRfqDialog";

import { useProject } from "@/hooks/use-projects";
import { useDocuments } from "@/hooks/use-documents";
import { ApiError } from "@/lib/api/client";

/** Project detail: header + document upload/list + RFQ generation entry. */
export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const {
    data: project,
    isLoading: projectLoading,
    error: projectError,
  } = useProject(projectId);
  const { data: documents, isLoading: docsLoading } = useDocuments(projectId);

  if (projectError instanceof ApiError && projectError.status === 404) {
    return (
      <div className="space-y-4">
        <Button asChild variant="ghost" size="sm">
          <Link to="/projects">
            <ChevronLeft className="h-4 w-4" /> Back to projects
          </Link>
        </Button>
        <p className="text-muted-foreground">Project not found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm">
        <Link to="/projects">
          <ChevronLeft className="h-4 w-4" /> Back to projects
        </Link>
      </Button>

      <div className="flex flex-col gap-1">
        {projectLoading ? (
          <Skeleton className="h-9 w-64" />
        ) : (
          <h1 className="text-2xl font-bold tracking-tight">{project?.name}</h1>
        )}
        <p className="text-sm text-muted-foreground">
          {project?.location || "No location set"}
          {project?.client ? ` · ${project.client}` : ""}
          {project?.capacity_m3d != null
            ? ` · ${project.capacity_m3d.toLocaleString()} m³/d`
            : ""}
        </p>
      </div>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Documents</h2>
          {projectId && <GenerateRfqDialog projectId={projectId} />}
        </div>
        {projectId && <DocumentUpload projectId={projectId} />}
        {projectId && (
          <DocumentTable
            projectId={projectId}
            documents={documents}
            isLoading={docsLoading}
          />
        )}
      </section>
    </div>
  );
}
