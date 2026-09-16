import { notFound } from "next/navigation";
import { SurakshConsole, View } from "@/components/SurakshConsole";
const views: View[] = ["registry", "gis", "viewer", "investigations", "watchlists", "integrations", "health", "audit"];
export default async function Page({ params }: { params: Promise<{ view: string }> }) {
  const { view } = await params;
  if (!views.includes(view as View)) notFound();
  return <SurakshConsole view={view as View} />;
}
