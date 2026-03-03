import { useVote } from "../hooks/useVote";

export default function VoteButtons({ prediction, onVote }) {
  const { voted, castVote } = useVote(prediction.id);

  const handleVote = async (direction) => {
    if (voted) return;
    try {
      const res = await fetch(`/api/predictions/${prediction.id}/vote`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction }),
      });
      if (res.ok) {
        castVote(direction);
        onVote?.();
      }
    } catch {
      /* ignore */
    }
  };

  const net = (prediction.upvotes || 0) - (prediction.downvotes || 0);

  return (
    <div className="flex items-center gap-1.5 select-none">
      <button
        onClick={() => handleVote("up")}
        disabled={!!voted}
        title="Upvote"
        className={`p-1.5 rounded transition-colors ${
          voted === "up"
            ? "text-green-400"
            : voted
            ? "text-gray-600 cursor-not-allowed"
            : "text-gray-400 hover:text-green-400 hover:bg-gray-800"
        }`}
      >
        ▲
      </button>
      <span className="text-sm tabular-nums w-8 text-center font-medium">
        {net}
      </span>
      <button
        onClick={() => handleVote("down")}
        disabled={!!voted}
        title="Downvote"
        className={`p-1.5 rounded transition-colors ${
          voted === "down"
            ? "text-red-400"
            : voted
            ? "text-gray-600 cursor-not-allowed"
            : "text-gray-400 hover:text-red-400 hover:bg-gray-800"
        }`}
      >
        ▼
      </button>
    </div>
  );
}
