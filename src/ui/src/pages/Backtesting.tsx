import { FlaskConical } from "lucide-react";
import { Card } from "../components/ui/Card";

/**
 * Backtesting is temporarily disabled (its router registration is commented out in
 * src/api/main.py). The nav entry (lib/nav.ts) is kept visible but greyed out; this
 * page is a placeholder for anyone who still navigates here directly.
 */
export function Backtesting() {
  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Backtesting</h2>
      <Card className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
        <FlaskConical size={28} className="text-white/30" />
        <p className="text-sm">Backtesting is temporarily disabled.</p>
      </Card>
    </div>
  );
}
