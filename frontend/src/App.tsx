import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  createBrowserRouter,
  Navigate,
  RouterProvider,
} from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";

import { RootLayout } from "@/components/layout/RootLayout";
import { NotFoundPage } from "@/routes/NotFoundPage";
import { ProjectsPage } from "@/routes/projects/ProjectsPage";
import { ProjectDetailPage } from "@/routes/projects/ProjectDetailPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // RFQ generation is long but it's a mutation, not a query; queries are
      // all fast CRUD reads. A short stale time keeps the list views snappy
      // without re-fetching on every focus.
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const router = createBrowserRouter([
  {
    path: "/",
    element: <RootLayout />,
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },
      { path: "projects", element: <ProjectsPage /> },
      { path: "projects/:projectId", element: <ProjectDetailPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
        <Toaster richColors position="top-right" />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
