import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/Card";
import { BarChart3, Briefcase, UserCircle, Star } from "lucide-react";
import { motion } from "framer-motion";

export default function Dashboard() {
  const stats = [
    { title: "Jobs Scraped", value: "1,204", icon: BarChart3, change: "+12% this week" },
    { title: "Matched Jobs", value: "84", icon: Star, change: "Top 10% fit" },
    { title: "Applications", value: "12", icon: Briefcase, change: "3 in progress" },
    { title: "Profile Views", value: "48", icon: UserCircle, change: "+2 today" },
  ];

  return (
    <div className="container mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-2">Welcome Back, Alex</h1>
      <p className="text-slate-600 dark:text-slate-400 mb-8">Here is the latest data extracted from your AI pipeline.</p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {stats.map((stat, i) => (
          <motion.div
            key={stat.title}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.1 }}
          >
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400">{stat.title}</CardTitle>
                <stat.icon className="h-4 w-4 text-slate-400 dark:text-slate-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-slate-900 dark:text-white">{stat.value}</div>
                <p className="text-xs text-slate-500 dark:text-slate-500 mt-1">{stat.change}</p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent Job Recommendations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {[1, 2, 3].map((v) => (
                <div key={v} className="flex items-center gap-4 p-4 rounded-lg bg-slate-50 dark:bg-slate-800/50">
                  <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center shrink-0">
                    <Briefcase className="h-5 w-5 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-900 dark:text-white truncate">Full Stack Developer</p>
                    <p className="text-xs text-slate-500 truncate">Vercel • Remote • 94% Match</p>
                  </div>
                  <div className="text-sm font-medium text-primary">View</div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardHeader>
            <CardTitle>Resume Status</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center justify-center py-6 text-center">
              <div className="w-20 h-20 bg-green-100 dark:bg-green-900/30 text-green-600 rounded-full flex items-center justify-center mb-4">
                <CheckCircle className="h-10 w-10" />
              </div>
              <h3 className="font-medium text-slate-900 dark:text-white">Resume Parsed</h3>
              <p className="text-sm text-slate-500 mt-2">Latest upload: 2 hours ago</p>
              <button className="text-primary text-sm font-medium mt-4">Upload New Resume</button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function CheckCircle(props: any) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
    </svg>
  );
}
