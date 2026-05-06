import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Briefcase, PhoneCall, Users, FileText } from "lucide-react";

export function Dashboard() {
  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
      
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Card className="overflow-hidden border border-blue-500/20 bg-blue-500/5 shadow-lg hover:shadow-blue-500/10 transition-all duration-300 group">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-blue-500 transition-colors">Active Jobs</CardTitle>
            <div className="p-2 bg-blue-500/10 rounded-lg group-hover:bg-blue-500/20 transition-colors">
              <Briefcase className="h-4 w-4 text-blue-500" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight">3</div>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <span className="text-green-500 font-medium">+1</span> from last month
            </p>
          </CardContent>
        </Card>

        <Card className="overflow-hidden border border-purple-500/20 bg-purple-500/5 shadow-lg hover:shadow-purple-500/10 transition-all duration-300 group">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-purple-500 transition-colors">Total Candidates</CardTitle>
            <div className="p-2 bg-purple-500/10 rounded-lg group-hover:bg-purple-500/20 transition-colors">
              <Users className="h-4 w-4 text-purple-500" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight">24</div>
            <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
              <span className="text-green-500 font-medium">+12%</span> increase
            </p>
          </CardContent>
        </Card>

        <Card className="overflow-hidden border border-green-500/20 bg-green-500/5 shadow-lg hover:shadow-green-500/10 transition-all duration-300 group">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-green-500 transition-colors">Resumes Parsed</CardTitle>
            <div className="p-2 bg-green-500/10 rounded-lg group-hover:bg-green-500/20 transition-colors">
              <FileText className="h-4 w-4 text-green-500" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight">18</div>
            <p className="text-xs text-muted-foreground mt-1">
              <span className="text-green-500 font-medium">92%</span> accuracy rate
            </p>
          </CardContent>
        </Card>

        <Card className="overflow-hidden border border-orange-500/20 bg-orange-500/5 shadow-lg hover:shadow-orange-500/10 transition-all duration-300 group">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground group-hover:text-orange-500 transition-colors">Calls Completed</CardTitle>
            <div className="p-2 bg-orange-500/10 rounded-lg group-hover:bg-orange-500/20 transition-colors">
              <PhoneCall className="h-4 w-4 text-orange-500" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold tracking-tight">12</div>
            <p className="text-xs text-muted-foreground mt-1">
              <span className="text-orange-500 font-medium">8.5</span> avg score
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
