import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createProject, getProject, listProjects } from "@/lib/api/projects";
import type { ProjectCreate, Uuid } from "@/lib/api/types";

export const projectsKeys = {
  all: ["projects"] as const,
  detail: (id: Uuid) => ["projects", id] as const,
};

/** List all projects (newest first). */
export function useProjects() {
  return useQuery({
    queryKey: projectsKeys.all,
    queryFn: listProjects,
  });
}

/** Fetch a single project by id. */
export function useProject(projectId: Uuid | undefined) {
  return useQuery({
    queryKey: projectId ? projectsKeys.detail(projectId) : ["projects", "none"],
    queryFn: () => getProject(projectId as Uuid),
    enabled: Boolean(projectId),
  });
}

/** Create a project; invalidates the projects list. */
export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ProjectCreate) => createProject(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: projectsKeys.all }),
  });
}
