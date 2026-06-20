import { useParams, Link } from "react-router-dom";
import { ChevronLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
        <Button asChild variant="ghost" size="sm" className="text-text-secondary">
          <Link to="/projects">
            <ChevronLeft className="h-4 w-4" /> Back to projects
          </Link>
        </Button>
        <p className="text-sm text-text-muted">Project not found.</p>
      </div>
    );
  }

  const subtitle = [
    project?.location || "No location set",
    project?.client,
    project?.capacity_m3d != null
      ? `${project.capacity_m3d.toLocaleString()} m³/d`
      : null,
    project?.project_number ? `#${project.project_number}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="space-y-6">
      <Button asChild variant="ghost" size="sm" className="text-text-secondary">
        <Link to="/projects">
          <ChevronLeft className="h-4 w-4" /> Back to projects
        </Link>
      </Button>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          {projectLoading ? (
            <Skeleton className="h-9 w-64" />
          ) : (
            <h1 className="text-[28px] font-bold leading-tight tracking-tight text-text-primary">
              {project?.name}
            </h1>
          )}
          <p className="text-sm text-text-muted">{subtitle}</p>
        </div>
        {projectId && <GenerateRfqDialog projectId={projectId} />}
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-lg font-semibold">
            Documents
            {documents && (
              <span className="ml-2 text-sm font-normal text-text-muted tabular-nums">
                {documents.length}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {projectId && <DocumentUpload projectId={projectId} />}
          {projectId && (
            <DocumentTable
              projectId={projectId}
              documents={documents}
              isLoading={docsLoading}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
