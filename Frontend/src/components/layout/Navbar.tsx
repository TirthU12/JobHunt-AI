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
    <nav className="fixed top-0 left-0 right-0 z-50 w-full border-b border-white/20 dark:border-white/5 bg-white/60 dark:bg-slate-900/60 backdrop-blur-2xl shadow-sm transition-all duration-300">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="flex items-center gap-2 group">
            <div className="bg-gradient-premium p-1.5 rounded-xl shadow-lg shadow-primary/30 group-hover:shadow-primary/50 transition-all duration-300 transform group-hover:-translate-y-0.5">
              <Briefcase className="h-5 w-5 text-white" />
            </div>
            <span className="font-extrabold text-2xl tracking-tight text-slate-900 dark:text-white transition-colors duration-300">
              JobHunt <span className="text-gradient">AI</span>
            </span>
          </Link>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setIsDark(!isDark)}
            className="p-2.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-500 hover:text-primary dark:text-slate-400 dark:hover:text-primary transition-all duration-300 hover:shadow-md"
          >
            {isDark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </button>
          
          <button className="md:hidden p-2.5 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 hover:text-primary transition-colors">
            <Menu className="h-5 w-5" />
          </button>
        </div>
      </div>
    </nav>
  );
}
