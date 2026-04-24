import { useParams, Link, useLocation } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { ArrowLeft, Building, MapPin, Calendar, Clock, CheckCircle2 } from "lucide-react";
import { motion } from "framer-motion";

export default function Detail() {
  const { id } = useParams();
  const location = useLocation();
  const job = location.state?.job || null;
  
  if (!job) {
     return <div className="p-8 text-center">Job not found. Please select a job from the products list.</div>;
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <Link to="/products" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white mb-8 transition-colors">
        <ArrowLeft className="h-4 w-4" /> Back to jobs
      </Link>

      <motion.div 
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="space-y-8"
      >
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6 pb-8 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-slate-900 dark:text-white mb-4">{job.title}</h1>
            <div className="flex flex-wrap items-center gap-4 text-slate-600 dark:text-slate-400">
              <span className="flex items-center gap-1.5"><Building className="h-4 w-4 shrink-0" /> {job.company || "Unknown"}</span>
              <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4 shrink-0" /> {job.location || "Remote"}</span>
              {job.job_type && <span className="flex items-center gap-1.5"><Clock className="h-4 w-4 shrink-0" /> {job.job_type}</span>}
              {job.salary && <span className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-200 dark:bg-slate-800 text-sm">{job.salary}</span>}
            </div>
          </div>
          <div className="flex flex-col gap-3 min-w-[200px]">
            {job.url ? (
               <a href={job.url} target="_blank" rel="noopener noreferrer">
                 <Button size="lg" className="w-full">Apply Now</Button>
               </a>
            ) : (
               <Button size="lg" className="w-full" disabled>Apply Now</Button>
            )}
            <Button variant="outline" size="lg" className="w-full">Save Job</Button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
          <div className="md:col-span-2 space-y-8 text-slate-700 dark:text-slate-300 leading-relaxed">
            <section>
              <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">About the Role</h2>
              <p className="whitespace-pre-wrap">{job.description || "No description provided."}</p>
            </section>
            
            {job.matching_skills && job.matching_skills.length > 0 && (
              <section>
                <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4">Matched Skills</h2>
                <ul className="space-y-3">
                  {job.matching_skills.map((req: string, i: number) => (
                    <li key={i} className="flex items-start gap-3">
                      <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0 mt-0.5" />
                      <span>{req}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
          
          <div className="space-y-6">
            <div className="p-6 rounded-xl bg-slate-100 dark:bg-surface border border-slate-200 dark:border-slate-800">
              <h3 className="font-semibold text-slate-900 dark:text-white mb-4">AI Match Analysis</h3>
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-600 dark:text-slate-400">Total Score</span>
                    <span className="font-semibold text-green-500">{job.match_score || 0}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                    <div className="h-full bg-green-500 transition-all duration-1000" style={{ width: `${job.match_score || 0}%` }} />
                  </div>
                </div>
                {job.match_reason && (
                  <p className="text-sm text-slate-600 dark:text-slate-400 italic">
                    "{job.match_reason}"
                  </p>
                )}
                <div className="pt-2 text-sm font-medium text-slate-800 dark:text-slate-200">
                  <span className="block opacity-70 mb-1">Verdict:</span> {job.apply_recommendation || "Worth applying"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
