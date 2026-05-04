import { motion } from "framer-motion";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/Card";
import { Briefcase, Building, MapPin, Star } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import { Button } from "../components/ui/Button";

// Dummy data
const mockJobs = [
  { id: "1", title: "Senior Python Engineer", company: "Stripe", location: "Remote", type: "Full-time", salary: "$150k - $200k", match: 96 },
  { id: "2", title: "React Developer", company: "Vercel", location: "San Francisco, CA", type: "Full-time", salary: "$120k - $160k", match: 92 },
  { id: "3", title: "Backend Systems Engineer", company: "Spotify", location: "Remote", type: "Contract", salary: "$90/hr", match: 88 },
  { id: "4", title: "Full Stack Wizard", company: "Discord", location: "New York, NY", type: "Full-time", salary: "$130k - $180k", match: 85 },
];

export default function Products() {
  const location = useLocation();
  const navigate = useNavigate();

  // Pick up data injected by the Home page's FastAPI request
  let stateData = location.state as { matches: any[], local_matches: any[], mnc_matches: any[], resume: any } | null;
  
  // Persist jobs to SessionStorage to handle 'Back' navigation or refreshes
  if (stateData) {
    sessionStorage.setItem("ai_jobs_cache", JSON.stringify(stateData));
  } else {
    const cached = sessionStorage.getItem("ai_jobs_cache");
    if (cached) {
      stateData = JSON.parse(cached);
    }
  }

  // Tab selector State
  const [activeTab, setActiveTab] = useState<"pan_india" | "local" | "mnc" | "linkedin" | "all_relevant">("pan_india");
  
  // Decide which source of jobs to run through filtering logic
  const topJobs = stateData?.matches || mockJobs;
  const localJobs = stateData?.local_matches || [];
  const mncJobs = stateData?.mnc_matches || [];
  const linkedinJobs = (stateData as any)?.linkedin_matches || [];
  
  let jobs = activeTab === "pan_india" ? topJobs : 
             activeTab === "local" ? localJobs : 
             activeTab === "mnc" ? mncJobs : 
             activeTab === "linkedin" ? linkedinJobs : [];
             
  if (activeTab === "all_relevant") {
      // Merge all jobs and filter for ONLY those that didn't get deeply AI scored
      const merged = [...topJobs, ...localJobs, ...mncJobs, ...linkedinJobs];
      jobs = merged.filter((j: any) => j.llm_score === 0 || (j.match_score && j.match_score < 60));
  }

  let userName = stateData?.resume?.name ? `for ${stateData.resume.name}` : "";
  
  // Extract user city from resume to generate dynamic filter
  let userCity = "";
  if (stateData?.resume?.location) {
     userCity = stateData.resume.location.split(",")[0].trim();
  }

  const [activeFilter, setActiveFilter] = useState("All");
  const [visibleCount, setVisibleCount] = useState(6);
  const [searchCity, setSearchCity] = useState("");

  // Generate filter buttons dynamically based on Tab Selection
  let filterOptions = ["All"];
  if (activeTab === "pan_india") {
      filterOptions = ["All", "Pan India", "Remote"];
  } else if (activeTab === "local") {
      filterOptions = ["All", "Company Website", "Job Board"];
  } else if (activeTab === "mnc") {
      filterOptions = ["All", "Remote", "Company Website"];
  } else {
      filterOptions = ["All", "Remote"];
  }

  const filteredJobs = jobs.filter((job: any) => {
    const jobLoc = (job.location || "").toLowerCase();
    
    // Pan India specific filters
    if (activeTab === "pan_india") {
        if (activeFilter === "Remote") {
          return jobLoc.includes("remote") || job.job_type?.toLowerCase().includes("remote") || job.title?.toLowerCase().includes("remote");
        }
        if (activeFilter === "Pan India") {
          return jobLoc === "india" || jobLoc.includes("india") || jobLoc.includes("pan india") || jobLoc.includes("anywhere in india");
        }
    }
    
    // Local City specific filters
    if (activeTab === "local") {
        if (activeFilter === "Company Website") {
           return job.source_type === "website" || job.source === "company_website";
        }
        if (activeFilter === "Job Board") {
           return job.source_type === "board" || job.source !== "company_website";
        }
    }

    // MNC specific filters
    if (activeTab === "mnc") {
        if (activeFilter === "Remote") {
            return jobLoc.includes("remote") || job.job_type?.toLowerCase().includes("remote") || job.title?.toLowerCase().includes("remote");
        }
        if (activeFilter === "Company Website") {
            return job.source === "workday_scraper" || job.source === "custom_career_page";
        }
    }

    // All Relevant specific filters
    if (activeTab === "all_relevant") {
        if (searchCity && !jobLoc.includes(searchCity.toLowerCase())) {
            return false;
        }
        if (activeFilter === "Remote") {
            return jobLoc.includes("remote") || job.job_type?.toLowerCase().includes("remote") || job.title?.toLowerCase().includes("remote");
        }
    }
    
    return true;
  });

  const visibleJobs = filteredJobs.slice(0, visibleCount);

  return (
    <div className="container mx-auto px-4 py-12">
      <Link to="/" className="inline-flex items-center gap-2 text-sm text-slate-500 hover:text-primary dark:text-slate-400 dark:hover:text-primary mb-6 transition-colors">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6"/></svg>
        Back to Home
      </Link>
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end mb-8 gap-4 border-b border-slate-200 dark:border-slate-800 pb-6">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-4">Recommended Jobs {userName}</h1>
          <div className="flex gap-4 overflow-x-auto whitespace-nowrap">
             <button 
                onClick={() => { setActiveTab("pan_india"); setActiveFilter("All"); setVisibleCount(6); }}
                className={`pb-2 border-b-2 font-medium transition-all ${activeTab === "pan_india" ? "border-primary text-primary" : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"}`}
             >
                 Pan India Matches
             </button>
             <button 
                onClick={() => { setActiveTab("local"); setActiveFilter("All"); setVisibleCount(6); }}
                className={`pb-2 border-b-2 font-medium transition-all ${activeTab === "local" ? "border-primary text-primary" : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"}`}
             >
                 Local City Matches ({userCity || "Strict"})
             </button>
             <button 
                onClick={() => { setActiveTab("mnc"); setActiveFilter("All"); setVisibleCount(6); }}
                className={`pb-2 border-b-2 font-medium transition-all ${activeTab === "mnc" ? "border-primary text-primary" : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"}`}
             >
                 Top MNC Matches
             </button>
             <button 
                onClick={() => { setActiveTab("linkedin"); setActiveFilter("All"); setVisibleCount(6); }}
                className={`pb-2 border-b-2 font-medium transition-all ${activeTab === "linkedin" ? "border-primary text-primary" : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"}`}
             >
                 LinkedIn Matches
             </button>
             <button 
                onClick={() => { setActiveTab("all_relevant"); setActiveFilter("All"); setVisibleCount(6); }}
                className={`pb-2 border-b-2 font-medium transition-all ${activeTab === "all_relevant" ? "border-primary text-primary" : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"}`}
             >
                 All Relevant (Generic Matches)
             </button>
          </div>
        </div>
        <div className="flex flex-col md:flex-row gap-3 w-full md:w-auto items-start md:items-center">
          {activeTab === "all_relevant" && (
            <input
              type="text"
              placeholder="Search by city..."
              value={searchCity}
              onChange={(e) => { setSearchCity(e.target.value); setVisibleCount(6); }}
              className="px-3 py-1.5 border border-slate-300 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-900 focus:outline-none focus:border-primary"
            />
          )}
          <div className="flex gap-2 overflow-x-auto pb-2 md:pb-0">
          {filterOptions.map(filter => (
            <span 
              key={filter} 
              onClick={() => { setActiveFilter(filter); setVisibleCount(6); }}
              className={`px-4 py-1.5 rounded-full text-sm font-medium cursor-pointer transition-colors ${
                activeFilter === filter 
                  ? "bg-primary text-white" 
                  : "bg-slate-200 dark:bg-slate-800 hover:bg-primary/80 hover:text-white"
              }`}
            >
              {filter}
            </span>
          ))}
        </div>
      </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {visibleJobs.map((job: any, i: number) => (
          <motion.div
            key={job.id}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: i * 0.1 }}
          >
            <div onClick={() => navigate(`/products/${job.id}`, { state: { job } })}>
              <Card className="h-full hover:border-primary/50 transition-colors cursor-pointer group">
                <CardHeader className="pb-4">
                  <div className="flex justify-between items-start mb-2">
                    <div className="p-2 bg-slate-100 dark:bg-slate-800 rounded-lg group-hover:bg-primary/10 transition-colors">
                      <Briefcase className="h-6 w-6 text-slate-700 dark:text-slate-300 group-hover:text-primary transition-colors" />
                    </div>
                    <span className="flex items-center gap-1 text-sm font-semibold text-green-600 bg-green-100 dark:bg-green-900/30 px-2.5 py-0.5 rounded-full">
                      <Star className="h-3 w-3 fill-current" /> {job.match_score || job.match || 0}% Match
                    </span>
                  </div>
                  <CardTitle className="text-xl mb-1 group-hover:text-primary transition-colors line-clamp-1">{job.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2 text-sm text-slate-600 dark:text-slate-400 truncate">
                    <div className="flex items-center gap-2 truncate"><Building className="h-4 w-4 shrink-0" /> {job.company || "Unknown Company"}</div>
                    <div className="flex items-center gap-2 truncate"><MapPin className="h-4 w-4 shrink-0" /> {job.location || "Location not given"}</div>
                  </div>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {job.job_type && <span className="text-xs px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 font-medium">{job.job_type}</span>}
                    {job.salary && <span className="text-xs px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 font-medium">{job.salary}</span>}
                  </div>
                </CardContent>
              </Card>
            </div>
          </motion.div>
        ))}
      </div>

      {visibleCount < filteredJobs.length && (
        <div className="flex justify-center mt-12">
          <Button variant="outline" size="lg" onClick={() => setVisibleCount(c => c + 6)}>
            Load More Jobs
          </Button>
        </div>
      )}
      
      {filteredJobs.length === 0 && (
        <div className="text-center py-12 text-slate-500">
          No jobs found matching the active filter. Try "All".
        </div>
      )}
    </div>
  );
}
