import { Link } from "react-router-dom";
import { FileText } from "lucide-react";

/** Top navigation bar. */
export function Header() {
  return (
    <header className="border-b bg-background">
      <div className="container flex h-14 items-center gap-2">
        <Link to="/projects" className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-primary" />
          <span className="text-lg font-semibold tracking-tight">
            WABAG RFQ Automation
          </span>
        </Link>
      </div>
    </header>
  );
}
