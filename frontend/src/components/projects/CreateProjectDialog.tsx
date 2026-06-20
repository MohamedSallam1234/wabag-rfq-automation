import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Plus } from "lucide-react";

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
import { useCreateProject } from "@/hooks/use-projects";
import { ApiError } from "@/lib/api/client";

const projectSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  location: z.string().max(255).optional().or(z.literal("")),
  client: z.string().max(255).optional().or(z.literal("")),
  consultant: z.string().max(255).optional().or(z.literal("")),
  project_number: z.string().max(128).optional().or(z.literal("")),
  capacity_m3d: z
    .union([z.coerce.number().int().positive(), z.literal("")])
    .optional(),
});

type ProjectFormValues = z.input<typeof projectSchema>;

/** Dialog with a form to create a new project. */
export function CreateProjectDialog() {
  const [open, setOpen] = useState(false);
  const createProject = useCreateProject();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProjectFormValues>({
    resolver: zodResolver(projectSchema),
    defaultValues: {
      name: "",
      location: "",
      client: "",
      consultant: "",
      project_number: "",
      capacity_m3d: "",
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    const payload = {
      name: values.name,
      location: values.location || null,
      client: values.client || null,
      consultant: values.consultant || null,
      project_number: values.project_number || null,
      capacity_m3d:
        typeof values.capacity_m3d === "number" ? values.capacity_m3d : null,
    };
    try {
      await createProject.mutateAsync(payload);
      toast.success("Project created");
      setOpen(false);
      reset();
    } catch (err) {
      const message =
        err instanceof ApiError ? (err.detail ?? err.message) : "Create failed";
      toast.error(message);
    }
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          New project
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create project</DialogTitle>
          <DialogDescription>
            Enter the project details. All fields except the name are optional.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name *</Label>
            <Input id="name" {...register("name")} autoFocus />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="location">Location</Label>
              <Input id="location" {...register("location")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="client">Client</Label>
              <Input id="client" {...register("client")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="consultant">Consultant</Label>
              <Input id="consultant" {...register("consultant")} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="project_number">Project number</Label>
              <Input id="project_number" {...register("project_number")} />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="capacity_m3d">Capacity (m³/day)</Label>
            <Input
              id="capacity_m3d"
              type="number"
              min={1}
              {...register("capacity_m3d")}
            />
            {errors.capacity_m3d && (
              <p className="text-sm text-destructive">
                {errors.capacity_m3d.message}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
