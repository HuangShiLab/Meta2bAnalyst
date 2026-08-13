import { AlertCircle, CheckCircle, Info, XCircle } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";

interface StatusAlertProps {
  status: "success" | "error" | "warning" | "info";
  title: string;
  description?: string;
  className?: string;
}

const statusConfig = {
  success: {
    icon: <CheckCircle className="h-4 w-4" />,
    variant: "default" as const,
  },
  error: {
    icon: <XCircle className="h-4 w-4" />,
    variant: "destructive" as const,
  },
  warning: {
    icon: <AlertCircle className="h-4 w-4" />,
    variant: "default" as const,
  },
  info: {
    icon: <Info className="h-4 w-4" />,
    variant: "default" as const,
  },
};

export function StatusAlert({
  status,
  title,
  description,
  className,
}: StatusAlertProps) {
  const config = statusConfig[status];

  return (
    <Alert variant={config.variant} className={cn("", className)}>
      {config.icon}
      <AlertTitle>{title}</AlertTitle>
      {description && <AlertDescription>{description}</AlertDescription>}
    </Alert>
  );
}
