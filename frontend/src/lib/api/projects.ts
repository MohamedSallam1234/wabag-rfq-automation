import { apiClient } from "./client";
import type { ProjectCreate, ProjectRead, Uuid } from "./types";

/** POST /api/v1/projects — create a project. */
export function createProject(input: ProjectCreate): Promise<ProjectRead> {
  return apiClient.post<ProjectRead>("/projects", input);
}

/** GET /api/v1/projects — list all projects, newest first. */
export function listProjects(): Promise<ProjectRead[]> {
  return apiClient.get<ProjectRead[]>("/projects");
}

/** GET /api/v1/projects/{id} — fetch a project by id. */
export function getProject(projectId: Uuid): Promise<ProjectRead> {
  return apiClient.get<ProjectRead>(`/projects/${projectId}`);
}
