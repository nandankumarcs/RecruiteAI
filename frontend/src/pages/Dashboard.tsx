import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Briefcase, PhoneCall, Users, FileText } from "lucide-react";

export function Dashboard() {
  // Placeholder stats - will be fetched from API in future phases
  const stats = [
    { title: "Active Jobs", value: "3", icon: Briefcase },
    { title: "Total Candidates", value: "24", icon: Users },
    { title: "Resumes Parsed", value: "18", icon: FileText },
    { title: "Calls Completed", value: "12", icon: PhoneCall },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-3xl font-bold tracking-tight">Dashboard</h2>
      
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.title}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
