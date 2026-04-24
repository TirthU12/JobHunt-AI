import { motion } from "framer-motion";
import { ArrowRight, Search, Zap, CheckCircle2 } from "lucide-react";
import { Button } from "../components/ui/Button";
import {  useNavigate } from "react-router-dom";
import { useState, useRef } from "react";
import { parseResume, searchJobs } from "../lib/api";

export default function Home() {
  const navigate = useNavigate();
  const [isUploading, setIsUploading] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [parsedData, setParsedData] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsUploading(true);
      const data = await parseResume(file);
      setParsedData(data.data);
    } catch (error: any) {
      alert("Error: " + error.message);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSearchJobs = async () => {
    try {
      setIsSearching(true);
      
      // Parse multi-string data right before dispatching
      const finalData = { ...parsedData };
      ["skills", "search_keywords", "job_titles"].forEach(key => {
        if (typeof finalData[key] === "string") {
          finalData[key] = finalData[key].split(",").map((s: string) => s.trim()).filter(Boolean);
        }
      });
      
      const data = await searchJobs(finalData);
      
      navigate("/products", { 
        state: { 
          matches: data.top_matched_jobs,
          local_matches: data.top_local_jobs,
          resume: data.data 
        } 
      });
    } catch (error: any) {
      alert("Error: " + error.message);
      setIsSearching(false);
    }
  };

  const handleArrayEdit = (key: string, value: string) => {
    // Preserve exact user string (including spaces) while they are still typing!
    setParsedData({ ...parsedData, [key]: value });
  };
  return (
    <div className="flex-1 w-full flex flex-col items-center justify-center pt-24 pb-16 px-4 sm:px-6 lg:px-8">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-4xl text-center space-y-8"
      >
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-sm font-medium">
          <Zap className="h-4 w-4" />
          <span>v2.0 is now live</span>
        </div>
        
        {!parsedData ? (
          <>
            <h1 className="text-5xl sm:text-7xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              The smart way to <span className="text-primary block">find your dream job.</span>
            </h1>
            
            <p className="text-lg sm:text-xl text-slate-600 dark:text-slate-400 max-w-2xl mx-auto">
              Upload your resume and let our AI scrape, match, and recommend the best jobs across remote boards and local sites in seconds.
            </p>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload} 
                accept=".pdf,.docx" 
                className="hidden" 
              />
              <Button 
                size="lg" 
                className="w-full sm:w-auto gap-2"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
              >
                {isUploading ? (
                  <span className="animate-pulse">Parsing Resume...</span>
                ) : (
                  <>Upload Resume <ArrowRight className="h-4 w-4" /></>
                )}
              </Button>
            </div>
          </>
        ) : (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-2xl mx-auto bg-white dark:bg-surface border border-slate-200 dark:border-slate-800 rounded-2xl p-8 shadow-xl text-left"
          >
            <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-6">Verify Your Profile</h2>
            <div className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Target City</label>
                <input 
                  type="text" 
                  value={parsedData.location || ""} 
                  onChange={(e) => setParsedData({...parsedData, location: e.target.value})}
                  className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="e.g. Ahmedabad"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Extracted Skills (comma separated)</label>
                <textarea 
                  value={Array.isArray(parsedData.skills) ? parsedData.skills.join(", ") : (parsedData.skills || "")} 
                  onChange={(e) => handleArrayEdit("skills", e.target.value)}
                  className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary min-h-[100px]"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Target Search Keywords (comma separated)</label>
                <textarea 
                  value={Array.isArray(parsedData.search_keywords) ? parsedData.search_keywords.join(", ") : (parsedData.search_keywords || "")} 
                  onChange={(e) => handleArrayEdit("search_keywords", e.target.value)}
                  className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary min-h-[80px]"
                  placeholder="e.g. React Developer, Frontend Engineer"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Experience (Years)</label>
                  <input 
                    type="number" 
                    value={parsedData.experience_years || 0} 
                    onChange={(e) => setParsedData({...parsedData, experience_years: parseInt(e.target.value) || 0})}
                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Desired Job Titles</label>
                  <input 
                    type="text" 
                    value={Array.isArray(parsedData.job_titles) ? parsedData.job_titles.join(", ") : (parsedData.job_titles || "")} 
                    onChange={(e) => handleArrayEdit("job_titles", e.target.value)}
                    className="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              </div>
              <div className="pt-4">
                <Button 
                  size="lg" 
                  className="w-full gap-2"
                  onClick={handleSearchJobs}
                  disabled={isSearching}
                >
                  {isSearching ? (
                    <span className="animate-pulse">Scraping Thousands of Jobs... This may take a minute!</span>
                  ) : (
                    <>Search Best Jobs <Search className="h-4 w-4" /></>
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        )}

        <div className="pt-16 grid grid-cols-1 sm:grid-cols-3 gap-8 text-left">
          {[
            { icon: Search, title: "Automated Scraping", desc: "We aggregate jobs from 10+ platforms including LinkedIn, Indeed, and specific remote boards." },
            { icon: Zap, title: "AI Resume Parsing", desc: "Our system understands your unique skills with LLaMa 3.3 to filter out irrelevant postings." },
            { icon: CheckCircle2, title: "Smart Matching", desc: "Get semantic scoring that tells you exactly why you're a fit for a specific role." }
          ].map((feature, i) => (
            <motion.div 
              key={i}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.2 + i * 0.1 }}
              className="p-6 rounded-2xl bg-white dark:bg-surface border border-slate-200 dark:border-slate-800 shadow-sm"
            >
              <div className="w-12 h-12 bg-primary/10 text-primary rounded-xl flex items-center justify-center mb-4">
                <feature.icon className="h-6 w-6" />
              </div>
              <h3 className="font-semibold text-lg text-slate-900 dark:text-white mb-2">{feature.title}</h3>
              <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">{feature.desc}</p>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
