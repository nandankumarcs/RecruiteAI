import { Link, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { ModeToggle } from "./ModeToggle";
import { Menu, X, LayoutDashboard, Briefcase, LogOut } from "lucide-react";
import { useState } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

export function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const navItems = [
    { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { label: "Jobs", href: "/jobs", icon: Briefcase },
  ];

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans">
      <header className="border-b border-border/40 px-4 md:px-8 h-20 flex items-center justify-between sticky top-0 bg-background/60 backdrop-blur-2xl z-50 transition-all">
        <div className="flex items-center gap-4 md:gap-8">
          {/* Mobile Menu */}
          <div className="md:hidden">
            <DropdownMenu onOpenChange={setIsMobileMenuOpen}>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-9 w-9">
                  {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
                  <span className="sr-only">Toggle menu</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-56 mt-2">
                {navItems.map((item) => (
                  <DropdownMenuItem key={item.href} asChild>
                    <Link to={item.href} className="flex items-center gap-2 cursor-pointer">
                      <item.icon className="h-4 w-4" />
                      <span>{item.label}</span>
                    </Link>
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive cursor-pointer">
                  <LogOut className="h-4 w-4 mr-2" />
                  <span>Logout</span>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <Link to="/dashboard" className="flex items-center gap-3 group">
            <div className="h-10 w-10 bg-primary rounded-lg flex items-center justify-center shadow-sm shadow-primary/10 group-hover:scale-105 group-hover:rotate-3 transition-all duration-300">
              <span className="text-primary-foreground font-black text-xl">R</span>
            </div>
            <h1 className="text-2xl font-black tracking-tighter text-primary hidden sm:block">
              RecruiteAI
            </h1>
          </Link>

          <nav className="hidden md:flex gap-2">
            {navItems.map((item) => (
              <Link 
                key={item.href}
                to={item.href} 
                className={cn(
                  "relative px-4 py-2 text-sm font-black tracking-tight uppercase transition-all duration-300",
                  location.pathname === item.href 
                    ? "text-primary" 
                    : "text-muted-foreground hover:text-foreground"
                )}
              >
                {location.pathname === item.href && (
                  <motion.div
                    layoutId="header-nav"
                    className="absolute inset-0 bg-primary/10 rounded-lg"
                    transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                  />
                )}
                <span className="relative z-10">{item.label}</span>
              </Link>
            ))}
          </nav>
        </div>
        
        <div className="flex items-center gap-3 md:gap-6">
          <ModeToggle />
          <div className="hidden md:flex items-center gap-4 pl-4 border-l border-border/40">
            <div className="flex flex-col items-end">
              <span className="text-sm font-black tracking-tight leading-none uppercase">
                {user?.full_name?.split(' ')[0]}
              </span>
              <Badge variant="outline" className="text-[9px] px-1.5 py-0 rounded-md font-black tracking-widest mt-1.5 border-primary/20 text-primary bg-primary/5">
                PRO
              </Badge>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="relative h-10 w-10 rounded-lg p-0 hover:bg-transparent overflow-hidden border border-border/40 shadow-sm transition-all active:scale-95">
                  <Avatar className="h-10 w-10 rounded-lg">
                    <AvatarFallback className="bg-primary/10 text-primary font-black">
                      {user?.full_name?.charAt(0)}
                    </AvatarFallback>
                  </Avatar>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56 mt-2 rounded-lg border-border/40 bg-background/95 backdrop-blur-2xl shadow-md p-2">
                <div className="px-2 py-2 mb-2 border-b border-border/40">
                  <p className="text-sm font-black tracking-tight">{user?.full_name}</p>
                  <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
                </div>
                <DropdownMenuItem className="rounded-lg h-10 font-bold">
                   <LayoutDashboard className="mr-2 h-4 w-4" /> Profile
                </DropdownMenuItem>
                <DropdownMenuItem onClick={logout} className="rounded-lg h-10 font-bold text-destructive focus:bg-destructive focus:text-destructive-foreground">
                  <LogOut className="mr-2 h-4 w-4" /> Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
      </header>

      <main className="flex-1 p-4 md:p-8 max-w-7xl mx-auto w-full">
        <Outlet />
      </main>
    </div>
  );
}
