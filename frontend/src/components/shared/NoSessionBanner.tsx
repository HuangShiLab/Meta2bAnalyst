import { Link } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

/**
 * Shown on analysis pages when no data has been uploaded yet.
 *
 * Without this the pages render fully populated but every control is inert and
 * every request fails — the state that the old hardcoded "mock-session" id made
 * invisible.
 */
export function NoSessionBanner() {
  return (
    <Alert variant="destructive" className="mb-4">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>No data loaded</AlertTitle>
      <AlertDescription>
        Analyses need an active session. Upload a feature table — and a metadata
        file if you want to compare groups — on the{" "}
        <Link to="/upload" className="underline font-medium">
          Upload page
        </Link>{" "}
        first.
      </AlertDescription>
    </Alert>
  );
}
