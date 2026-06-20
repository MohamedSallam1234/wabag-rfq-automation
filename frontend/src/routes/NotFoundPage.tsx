import { Link } from "react-router-dom";
import { Compass } from "lucide-react";

import { Button } from "@/components/ui/button";

/** 404 catch-all. */
export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <div
        className="flex h-14 w-14 items-center justify-center rounded-tile bg-info-soft"
        aria-hidden="true"
      >
        <Compass className="h-7 w-7 text-info" />
      </div>
      <h1 className="text-[28px] font-bold tracking-tight text-text-primary">
        Page not found
      </h1>
      <p className="text-sm text-text-muted">
        That page doesn&apos;t exist. Head back to your projects.
      </p>
      <Button asChild>
        <Link to="/projects">Back to projects</Link>
      </Button>
    </div>
  );
}
