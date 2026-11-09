import ReplayView from "../components/ReplayView";
import { IS_PUBLIC } from "../lib/mode";

export default function ReplayPage() {
  return <ReplayView linkCharts={!IS_PUBLIC} />;
}
