import { Link } from "react-router-dom";
import { Briefcase, Sun, Moon, Menu } from "lucide-react";
import { Button } from "../ui/Button";
import { useEffect, useState } from "react";

export function Navbar() {
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [isDark]);

  return (
    <nav className="sticky top-0 z-50 w-full border-b border-slate-200 dark:border-slate-800 bg-white/50 dark:bg-background/50 backdrop-blur-xl">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Link to="/" className="flex items-center gap-2">
            <div className="bg-primary p-1.5 rounded-lg">
              <Briefcase className="h-5 w-5 text-white" />
            </div>
            <span className="font-bold text-xl tracking-tight text-slate-900 dark:text-white">JobHunt AI</span>
          </Link>
          <div className="hidden md:flex ml-8 items-center gap-6 text-sm font-medium text-slate-600 dark:text-slate-300">
            <Link to="/products" className="hover:text-primary transition-colors">Find Jobs</Link>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setIsDark(!isDark)}
            className="p-2 text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 transition-colors"
          >
            {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          
          <button className="md:hidden p-2 text-slate-500 dark:text-slate-400">
            <Menu className="h-6 w-6" />
          </button>
        </div>
      </div>
    </nav>
  );
}
