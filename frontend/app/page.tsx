import { MobileDashboard } from "@/components/mobile-dashboard";
import { getDashboardData } from "@/lib/data";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function HomePage() {
  const dashboardData = await getDashboardData();
  return <MobileDashboard data={dashboardData} />;
}
