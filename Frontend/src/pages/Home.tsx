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
          mnc_matches: data.top_mnc_jobs,
          linkedin_matches: data.top_linkedin_jobs,
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
    <div className="flex-1 w-full flex flex-col items-center pt-32 pb-24 px-4 sm:px-6 lg:px-8 relative overflow-hidden">
      {/* Premium Background Blurs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/20 dark:bg-primary/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-secondary/20 dark:bg-secondary/10 rounded-full blur-[120px] pointer-events-none" />

      <motion.div 
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-5xl text-center space-y-10 relative z-10"
      >
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-semibold shadow-sm animate-fade-in-up">
          <Zap className="h-4 w-4" />
          <span>v2.0 is now live with Semantic AI</span>
        </div>
        
        {!parsedData ? (
          <div className="space-y-10 animate-fade-in-up" style={{ animationDelay: '0.1s' }}>
            <h1 className="text-6xl sm:text-7xl lg:text-8xl font-extrabold tracking-tight text-slate-900 dark:text-white leading-[1.1]">
              The smart way to <br className="hidden sm:block" />
              <span className="text-gradient">find your dream job.</span>
            </h1>
            
            <p className="text-lg sm:text-2xl text-slate-600 dark:text-slate-400 max-w-3xl mx-auto font-medium leading-relaxed">
              Upload your resume and let our AI scrape, match, and recommend the best jobs across remote boards and local sites in seconds.
            </p>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-8">
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileUpload} 
                accept=".pdf,.docx" 
                className="hidden" 
              />
              <Button 
                size="lg" 
                className="w-full sm:w-auto gap-3 text-lg h-14 px-8 rounded-2xl shadow-lg shadow-primary/30 hover:shadow-primary/50 transition-all duration-300 hover:scale-105"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
              >
                {isUploading ? (
                  <span className="flex items-center gap-2">
                    <span className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></span>
                    Parsing Resume...
                  </span>
                ) : (
                  <>Upload Resume <ArrowRight className="h-5 w-5" /></>
                )}
              </Button>
            </div>
          </div>
        ) : (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-3xl mx-auto glass-card rounded-3xl p-6 sm:p-10 text-left"
          >
            <div className="flex items-center gap-3 mb-8 pb-6 border-b border-slate-200 dark:border-slate-700/50">
              <div className="bg-primary/10 p-2.5 rounded-xl">
                <CheckCircle2 className="h-6 w-6 text-primary" />
              </div>
              <h2 className="text-3xl font-bold text-slate-900 dark:text-white">Verify Your Profile</h2>
            </div>
            
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Target City</label>
                <input 
                  type="text" 
                  value={parsedData.location || ""} 
                  onChange={(e) => setParsedData({...parsedData, location: e.target.value})}
                  className="w-full px-5 py-3.5 rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white/50 dark:bg-slate-900/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all shadow-sm"
                  placeholder="e.g. Ahmedabad"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Extracted Skills <span className="text-slate-400 font-normal">(comma separated)</span></label>
                <textarea 
                  value={Array.isArray(parsedData.skills) ? parsedData.skills.join(", ") : (parsedData.skills || "")} 
                  onChange={(e) => handleArrayEdit("skills", e.target.value)}
                  className="w-full px-5 py-3.5 rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white/50 dark:bg-slate-900/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all shadow-sm min-h-[120px] resize-y"
                />
              </div>
              <div>
                <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Target Search Keywords <span className="text-slate-400 font-normal">(comma separated)</span></label>
                <textarea 
                  value={Array.isArray(parsedData.search_keywords) ? parsedData.search_keywords.join(", ") : (parsedData.search_keywords || "")} 
                  onChange={(e) => handleArrayEdit("search_keywords", e.target.value)}
                  className="w-full px-5 py-3.5 rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white/50 dark:bg-slate-900/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all shadow-sm min-h-[100px] resize-y"
                  placeholder="e.g. React Developer, Frontend Engineer"
                />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Experience (Years)</label>
                  <input 
                    type="number" 
                    value={parsedData.experience_years || 0} 
                    onChange={(e) => setParsedData({...parsedData, experience_years: parseInt(e.target.value) || 0})}
                    className="w-full px-5 py-3.5 rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white/50 dark:bg-slate-900/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all shadow-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Desired Job Titles</label>
                  <input 
                    type="text" 
                    value={Array.isArray(parsedData.job_titles) ? parsedData.job_titles.join(", ") : (parsedData.job_titles || "")} 
                    onChange={(e) => handleArrayEdit("job_titles", e.target.value)}
                    className="w-full px-5 py-3.5 rounded-xl border border-slate-200 dark:border-slate-700/50 bg-white/50 dark:bg-slate-900/50 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all shadow-sm"
                  />
                </div>
              </div>
              <div className="pt-8">
                <Button 
                  size="lg" 
                  className="w-full gap-3 h-14 text-lg rounded-2xl shadow-lg shadow-primary/30 hover:shadow-primary/50 transition-all duration-300 hover:scale-[1.02]"
                  onClick={handleSearchJobs}
                  disabled={isSearching}
                >
                  {isSearching ? (
                    <span className="flex items-center gap-3">
                      <span className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></span>
                      <span>Scraping Thousands of Jobs...</span>
                    </span>
                  ) : (
                    <>Find the Best Matches <Search className="h-5 w-5" /></>
                  )}
                </Button>
              </div>
            </div>
          </motion.div>
        )}

        <div className="pt-24 grid grid-cols-1 sm:grid-cols-3 gap-6 sm:gap-8 text-left animate-fade-in-up" style={{ animationDelay: '0.3s' }}>
          {[
            { icon: Search, title: "Automated Scraping", desc: "We aggregate jobs from 10+ platforms including LinkedIn, Indeed, and specific remote boards." },
            { icon: Zap, title: "AI Resume Parsing", desc: "Our system understands your unique skills with LLaMa 3.3 to filter out irrelevant postings." },
            { icon: CheckCircle2, title: "Smart Matching", desc: "Get semantic scoring that tells you exactly why you're a fit for a specific role." }
          ].map((feature, i) => (
            <motion.div 
              key={i}
              whileHover={{ y: -5 }}
              className="glass-card rounded-3xl p-8"
            >
              <div className="w-14 h-14 bg-gradient-to-br from-primary/20 to-primary/40 dark:from-primary/30 dark:to-primary/10 rounded-2xl flex items-center justify-center mb-6 shadow-inner">
                <feature.icon className="h-7 w-7 text-primary dark:text-emerald-400" />
              </div>
              <h3 className="font-bold text-xl text-slate-900 dark:text-white mb-3 tracking-tight">{feature.title}</h3>
              <p className="text-slate-600 dark:text-slate-400 text-base leading-relaxed">{feature.desc}</p>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
