import { MobileDashboard } from "@/components/mobile-dashboard";
import { getDashboardData } from "@/lib/data";

export const revalidate = 300;

export default async function HomePage() {
  const dashboardData = await getDashboardData();
  return <MobileDashboard data={dashboardData} />;
}
