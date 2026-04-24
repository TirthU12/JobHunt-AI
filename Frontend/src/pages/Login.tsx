import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Button } from "../components/ui/Button";

export default function Login() {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      navigate("/dashboard");
    }, 1000);
  };

  return (
    <div className="flex-1 flex items-center justify-center px-4 pt-10 pb-20">
      <motion.div 
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="bg-white dark:bg-surface border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl overflow-hidden">
          <div className="p-8">
            <div className="text-center mb-8">
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Welcome Back</h2>
              <p className="text-slate-500">Sign in to your JobHunt account</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Email</label>
                <input 
                  type="email" 
                  required 
                  className="w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent text-slate-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all"
                  placeholder="you@example.com"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">Password</label>
                <input 
                  type="password" 
                  required 
                  className="w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent text-slate-900 dark:text-white focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all"
                  placeholder="••••••••"
                />
              </div>

              <div className="flex items-center justify-between text-sm">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" className="rounded border-slate-300 text-primary focus:ring-primary" />
                  <span className="text-slate-600 dark:text-slate-400">Remember me</span>
                </label>
                <a href="#" className="font-medium text-primary hover:text-primary/80">Forgot password?</a>
              </div>

              <Button type="submit" className="w-full" size="lg" disabled={loading}>
                {loading ? "Signing in..." : "Sign In"}
              </Button>
            </form>
          </div>
          
          <div className="bg-slate-50 dark:bg-slate-800/50 p-6 text-center border-t border-slate-200 dark:border-slate-800">
            <p className="text-slate-600 dark:text-slate-400 text-sm">
              Don't have an account? <Link to="/signup" className="font-medium text-primary hover:text-primary/80">Sign up</Link>
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
