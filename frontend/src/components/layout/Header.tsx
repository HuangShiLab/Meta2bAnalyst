import { Code2, BookOpen, FlaskConical, User as UserIcon, LogOut } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";

interface HeaderProps {
  className?: string;
}

export function Header({ className }: HeaderProps) {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const token = useAuthStore((s) => s.token);
  const logout = useAuthStore((s) => s.logout);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <header
      className={cn(
        "sticky top-0 z-50 w-full border-b border-border bg-white/80 backdrop-blur-sm",
        className
      )}
    >
      <div className="flex h-16 items-center px-4 lg:px-8">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-7 w-7 text-primary" />
          <Link
            to="/"
            className="text-xl font-bold tracking-tight text-foreground"
          >
            Meta2bAnalyst
          </Link>
        </div>

        <div className="ml-auto flex items-center gap-4">
          <a
            href="https://meta2banalyst.readthedocs.io"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
          >
            <BookOpen className="h-4 w-4" />
            <span className="hidden sm:inline">Docs</span>
          </a>
          <a
            href="https://github.com/meta2banalyst"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-primary"
          >
            <Code2 className="h-4 w-4" />
            <span className="hidden sm:inline">GitHub</span>
          </a>
          {token ? (
            <>
              <Link
                to="/account"
                className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-slate-200"
                title="My data"
              >
                <UserIcon className="h-4 w-4 text-primary" />
                <span>{user?.username ?? "…"}</span>
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-colors hover:text-destructive"
                title="Sign out"
              >
                <LogOut className="h-4 w-4" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </>
          ) : (
            <>
              <span className="flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1.5 text-sm font-medium text-muted-foreground">
                <UserIcon className="h-4 w-4" />
                Guest
              </span>
              <Link
                to="/login"
                className="flex items-center gap-1.5 text-sm font-medium text-primary transition-colors hover:text-primary/80"
              >
                <LogOut className="h-4 w-4 rotate-180" />
                Sign in
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
