import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

/** 404 catch-all. */
export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
      <h1 className="text-4xl font-bold tracking-tight">404</h1>
      <p className="text-muted-foreground">That page doesn&apos;t exist.</p>
      <Button asChild>
        <Link to="/projects">Back to projects</Link>
      </Button>
    </div>
  );
}
