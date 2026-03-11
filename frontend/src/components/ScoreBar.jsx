/**
 * Horizontal bar representing a score from -10 to +10.
 * Red on the left, green on the right, with a marker.
 */
export default function ScoreBar({ score }) {
  // Normalise -10…+10 → 0…100%
  const pct = ((score + 10) / 20) * 100;
  // Distance from centre (50%). Negative = extends left, positive = extends right.
  const halfPct = pct - 50;
  // Bar starts at the leftmost edge of the range, always anchored at centre.
  const barLeft = Math.min(50, pct);
  const barWidth = Math.abs(halfPct);

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
        {/* centre tick – marks score 0 */}
        <div className="absolute inset-y-0 left-1/2 w-px bg-gray-600" />
        {/* filled portion – extends left or right from centre */}
        <div
          className={`absolute inset-y-0 ${color} rounded-full transition-all`}
          style={{ left: `${barLeft}%`, width: `${barWidth}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 w-6">+10</span>
      <span className="text-sm font-bold ml-1 tabular-nums w-8 text-right">
        {score > 0 ? `+${score}` : score}
      </span>
    </div>
  );
}
