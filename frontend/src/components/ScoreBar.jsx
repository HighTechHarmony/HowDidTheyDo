/**
 * Horizontal bar representing a score from -10 to +10.
 * Red on the left, green on the right, with a marker.
 */
export default function ScoreBar({ score }) {
  // Normalise -10…+10 → 0…100%
  const pct = ((score + 10) / 20) * 100;

  // Colour by score
  let color;
  if (score >= 5) color = "bg-green-500";
  else if (score >= 1) color = "bg-green-700";
  else if (score >= -1) color = "bg-yellow-500";
  else if (score >= -5) color = "bg-red-700";
  else color = "bg-red-500";

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-500 w-6 text-right">-10</span>
      <div className="flex-1 h-3 bg-gray-800 rounded-full relative overflow-hidden">
        {/* filled portion */}
        <div
          className={`absolute inset-y-0 left-0 ${color} rounded-full transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 w-6">+10</span>
      <span className="text-sm font-bold ml-1 tabular-nums w-8 text-right">
        {score > 0 ? `+${score}` : score}
      </span>
    </div>
  );
}
