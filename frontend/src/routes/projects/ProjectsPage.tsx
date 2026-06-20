import { useProjects } from "@/hooks/use-projects";
import { useProjectsDocuments } from "@/hooks/use-projects-documents";
import { CreateProjectDialog } from "@/components/projects/CreateProjectDialog";
import { ProjectsTable } from "@/components/dashboard/ProjectsTable";
import {
  KpiCard,
  ACTIVE_PROJECTS_ICON,
  DOCUMENTS_UPLOADED_ICON,
  RFQ_PACKAGES_ICON,
} from "@/components/dashboard/KpiCard";
import { ApiError } from "@/lib/api/client";
import { totalDocuments, totalRfqPackages } from "@/lib/derive";

/**
 * Projects landing — a dashboard derived only from real endpoints.
 *
 * KPIs (Active Projects, Documents Uploaded, RFQ Packages Generated) are
 * computed client-side from `GET /projects` + per-project
 * `GET /projects/{id}/documents` (N+1; see use-projects-documents.ts). The
 * DESIGN.md KPIs for Open Conflicts / TBD Fields / Avg. Confidence are
 * omitted — those values are only ever returned transiently inside an RFQ
 * generation response and are not queryable.
 */
export function ProjectsPage() {
  const { data: projects, isLoading, error } = useProjects();
  const { docsByProject, isLoading: docsLoading } = useProjectsDocuments(
    projects,
  );

  const projectCount = projects?.length ?? 0;
  const docTotal = totalDocuments(docsByProject);
  const rfqTotal = totalRfqPackages(docsByProject);
  const kpisLoading = isLoading || (projectCount > 0 && docsLoading);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-[28px] font-bold leading-tight tracking-tight text-text-primary">
            Projects
          </h1>
          <p className="text-sm text-text-muted">
            Upload engineering documents and generate RFQ packages per project.
          </p>
        </div>
        <CreateProjectDialog />
      </div>

      {error instanceof ApiError ? (
        <p className="text-sm text-destructive">
          Failed to load projects: {error.detail ?? error.message}
        </p>
      ) : (
        <>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            <KpiCard
              tone="info"
              icon={ACTIVE_PROJECTS_ICON}
              label="Active Projects"
              value={projectCount}
              isLoading={isLoading}
              caption={projectCount === 1 ? "1 project" : `${projectCount} projects`}
            />
            <KpiCard
              tone="extraction"
              icon={DOCUMENTS_UPLOADED_ICON}
              label="Documents Uploaded"
              value={docTotal}
              isLoading={kpisLoading}
              caption={
                projectCount > 0 ? `across ${projectCount} projects` : undefined
              }
            />
            <KpiCard
              tone="success"
              icon={RFQ_PACKAGES_ICON}
              label="RFQ Packages Generated"
              value={rfqTotal}
              isLoading={kpisLoading}
              caption={rfqTotal === 1 ? "1 package" : `${rfqTotal} packages`}
            />
          </div>

          <ProjectsTable
            projects={projects ?? []}
            docsByProject={docsByProject}
            isLoading={isLoading}
            title="All Projects"
          />
        </>
      )}
    </div>
  );
}
