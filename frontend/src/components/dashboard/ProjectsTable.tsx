import { Link } from "react-router-dom";
import {
  Building2,
  ChevronRight,
  FileText,
  MoreHorizontal,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import {
  projectDocCount,
  projectRfqStatus,
} from "@/lib/derive";
import type { DocumentRead, ProjectRead, Uuid } from "@/lib/api/types";

export interface ProjectsTableProps {
  projects: ProjectRead[];
  docsByProject: Record<Uuid, DocumentRead[]>;
  isLoading: boolean;
  /** Card title. Defaults to "Recent Projects". */
  title?: string;
  /** Where the "View all" link points. Omit to hide the link. */
  viewAllTo?: string;
}

const SKELETON_ROWS = Array.from({ length: 4 }, (_, i) => i);

/** Recent Projects table (DESIGN.md §8.5) — only API-backed columns. */
export function ProjectsTable({
  projects,
  docsByProject,
  isLoading,
  title = "Recent Projects",
  viewAllTo,
}: ProjectsTableProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-lg font-semibold">{title}</CardTitle>
        {viewAllTo && (
          <Button asChild variant="link" size="sm" className="text-link">
            <Link to={viewAllTo}>
              View all
              <ChevronRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        )}
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>Project</TableHead>
              <TableHead>Client</TableHead>
              <TableHead>Location</TableHead>
              <TableHead>Capacity</TableHead>
              <TableHead className="text-center">Documents</TableHead>
              <TableHead>RFQ Status</TableHead>
              <TableHead>Last Updated</TableHead>
              <TableHead className="w-10 text-right" aria-label="Actions" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              SKELETON_ROWS.map((row) => (
                <TableRow key={`skeleton-${row}`} className="hover:bg-transparent">
                  <TableCell colSpan={8} className="py-4">
                    <Skeleton className="h-5 w-full" />
                  </TableCell>
                </TableRow>
              ))
            ) : projects.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell colSpan={8} className="py-12 text-center">
                  <div className="flex flex-col items-center gap-2 text-text-muted">
                    <FileText className="h-7 w-7" aria-hidden="true" />
                    <p className="text-sm">
                      No projects yet. Create one to start uploading documents.
                    </p>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              projects.map((project) => {
                const docs = docsByProject[project.id];
                const docCount = projectDocCount(docs);
                const status = projectRfqStatus(docs);
                const docsLoading = docs === undefined;
                return (
                  <TableRow key={project.id}>
                    <TableCell className="font-medium">
                      <Link
                        to={`/projects/${project.id}`}
                        className="inline-flex items-center gap-2 text-link hover:underline"
                      >
                        <Building2 className="h-4 w-4 shrink-0 text-text-muted" />
                        <span>{project.name}</span>
                      </Link>
                    </TableCell>
                    <TableCell className="text-text-secondary">
                      {project.client ?? "—"}
                    </TableCell>
                    <TableCell className="text-text-secondary">
                      {project.location ?? "—"}
                    </TableCell>
                    <TableCell className="text-text-secondary tabular-nums">
                      {project.capacity_m3d != null
                        ? `${project.capacity_m3d.toLocaleString()} m³/d`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-center">
                      <span className="inline-flex items-center gap-1.5 text-text-secondary tabular-nums">
                        <FileText className="h-3.5 w-3.5 text-text-muted" />
                        {docsLoading ? (
                          <Skeleton className="h-4 w-5" />
                        ) : (
                          docCount
                        )}
                      </span>
                    </TableCell>
                    <TableCell>
                      {docsLoading ? (
                        <Skeleton className="h-5 w-20" />
                      ) : (
                        <Badge variant={status.variant}>{status.label}</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-text-muted">
                      {formatDate(project.updated_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="iconSm"
                            className="text-text-muted hover:text-text-primary"
                            aria-label={`Actions for ${project.name}`}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link to={`/projects/${project.id}`}>
                              Open
                            </Link>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
