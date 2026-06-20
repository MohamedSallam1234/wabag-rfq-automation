import { useProjects } from "@/hooks/use-projects";
import { CreateProjectDialog } from "@/components/projects/CreateProjectDialog";
import { ProjectCard } from "@/components/projects/ProjectCard";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";

/** List of all projects, with a create button. */
export function ProjectsPage() {
  const { data: projects, isLoading, error } = useProjects();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">
            Upload documents and generate RFQ packages per project.
          </p>
        </div>
        <CreateProjectDialog />
      </div>

      {isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      )}

      {error instanceof ApiError && (
        <p className="text-sm text-destructive">
          Failed to load projects: {error.detail ?? error.message}
        </p>
      )}

      {!isLoading && !error && projects?.length === 0 && (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <p className="text-muted-foreground">
            No projects yet. Create one to get started.
          </p>
        </div>
      )}

      {!error && projects && projects.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}
