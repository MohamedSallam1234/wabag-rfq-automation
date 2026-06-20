import { Link } from "react-router-dom";
import { MapPin, Building2, Users } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";
import type { ProjectRead } from "@/lib/api/types";

/** A single project in the projects list. */
export function ProjectCard({ project }: { project: ProjectRead }) {
  return (
    <Link to={`/projects/${project.id}`}>
      <Card className="transition-colors hover:border-primary/50 hover:bg-accent/40">
        <CardHeader>
          <CardTitle className="text-lg">{project.name}</CardTitle>
          <p className="text-xs text-muted-foreground">
            Created {formatDate(project.created_at)}
          </p>
        </CardHeader>
        <CardContent className="space-y-1.5 text-sm">
          {project.location && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <MapPin className="h-3.5 w-3.5" />
              <span>{project.location}</span>
            </div>
          )}
          {project.client && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Building2 className="h-3.5 w-3.5" />
              <span>{project.client}</span>
            </div>
          )}
          {project.consultant && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Users className="h-3.5 w-3.5" />
              <span>{project.consultant}</span>
            </div>
          )}
          {project.capacity_m3d != null && (
            <p className="pt-1 font-medium">
              Capacity: {project.capacity_m3d.toLocaleString()} m³/d
            </p>
          )}
          {project.project_number && (
            <p className="text-xs text-muted-foreground">
              #{project.project_number}
            </p>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
