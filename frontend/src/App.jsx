import { useState, useEffect, useCallback } from "react";
import PredictionCard from "./components/PredictionCard";

const TABS = [
  { key: "recent", label: "Latest", endpoint: "/api/predictions/recent" },
  { key: "top", label: "Top All-Time", endpoint: "/api/predictions/top" },
];

const POLL_MS = 60_000;

export default function App() {
  const [tab, setTab] = useState("recent");
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);

  const active = TABS.find((t) => t.key === tab);

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(active.endpoint);
      if (res.ok) {
        setPredictions(await res.json());
      }
    } catch {
      /* network error — keep stale data */
    } finally {
      setLoading(false);
    }
  }, [active]);

  useEffect(() => {
    setLoading(true);
    fetchData();
    const id = setInterval(fetchData, POLL_MS);
    return () => clearInterval(id);
  }, [fetchData]);

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-4xl font-bold text-center mb-2 tracking-tight">
        How Did They Do?
      </h1>
      <p className="text-center text-gray-400 mb-8 text-sm">
        Old news predictions scored against what actually happened
      </p>

      {/* Tab bar */}
      <div className="flex gap-2 justify-center mb-8">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-5 py-2 rounded-full text-sm font-medium transition-colors ${
              tab === t.key
                ? "bg-indigo-600 text-white"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="text-center text-gray-500 mt-16">Loading…</p>
      ) : predictions.length === 0 ? (
        <p className="text-center text-gray-500 mt-16">
          No predictions yet. The daemon hasn't run or found any predictions.
        </p>
      ) : (
        <div className="space-y-6">
          {predictions.map((p) => (
            <PredictionCard key={p.id} prediction={p} onVote={fetchData} />
          ))}
        </div>
      )}
    </div>
  );
}
