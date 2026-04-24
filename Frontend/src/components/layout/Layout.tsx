import { Outlet } from "react-router-dom";
import { Navbar } from "./Navbar";

export function Layout() {
  return (
    <div className="min-h-screen flex flex-col pt-0">
      <Navbar />
      <main className="flex-1 flex flex-col w-full">
        <Outlet />
      </main>
      <footer className="border-t border-slate-200 dark:border-slate-800 py-8 text-center text-sm text-slate-500 dark:text-slate-400">
        <div className="container mx-auto px-4">
          © {new Date().getFullYear()} JobHunt AI. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
