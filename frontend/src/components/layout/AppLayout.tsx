import { Link, Outlet } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { ModeToggle } from "./ModeToggle";

export function AppLayout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <header className="border-b px-6 py-3 flex items-center justify-between sticky top-0 bg-background/80 backdrop-blur-md z-10">
        <div className="flex items-center gap-8">
          <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-primary to-primary/60 bg-clip-text text-transparent">
            RecruiteAI
          </h1>
          <nav className="hidden md:flex gap-6">
            <Link to="/dashboard" className="text-sm font-medium text-muted-foreground hover:text-primary transition-colors">Dashboard</Link>
            <Link to="/jobs" className="text-sm font-medium text-muted-foreground hover:text-primary transition-colors">Jobs</Link>
          </nav>
        </div>
        
        <div className="flex items-center gap-4">
          <ModeToggle />
          <div className="h-4 w-px bg-border mx-1" />
          <span className="text-sm font-medium hidden md:inline-block">
            {user?.full_name}
          </span>
          <Button variant="ghost" size="sm" onClick={logout} className="text-muted-foreground hover:text-destructive">
            Logout
          </Button>
        </div>
      </header>

      <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full">
        <Outlet />
      </main>
    </div>
  );
}
