import { useState } from "react";
import ScoreBar from "./ScoreBar";
import VoteButtons from "./VoteButtons";
import DebugLog from "./DebugLog";

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function formatDateWithOrdinal(iso) {
  try {
    const d = new Date(iso);
    const month = d.toLocaleString("en-US", { month: "long" });
    const day = ordinal(d.getDate());
    const year = d.getFullYear();
    return `${month} ${day}, ${year}`;
  } catch {
    return iso;
  }
}

function ExternalLinkIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 20 20"
      fill="currentColor"
      className="inline w-4 h-4 align-text-bottom opacity-50 hover:opacity-100 transition-opacity"
    >
      <path
        fillRule="evenodd"
        d="M4.25 5.5a.75.75 0 0 0-.75.75v8.5c0 .414.336.75.75.75h8.5a.75.75 0 0 0 .75-.75v-4a.75.75 0 0 1 1.5 0v4A2.25 2.25 0 0 1 12.75 17h-8.5A2.25 2.25 0 0 1 2 14.75v-8.5A2.25 2.25 0 0 1 4.25 4h4a.75.75 0 0 1 0 1.5h-4ZM11 3.75a.75.75 0 0 1 .75-.75h4.5a.75.75 0 0 1 .75.75v4.5a.75.75 0 0 1-1.5 0V5.56l-5.72 5.72a.75.75 0 1 1-1.06-1.06l5.72-5.72h-2.69A.75.75 0 0 1 11 3.75Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export default function PredictionCard({ prediction: p, onVote }) {
  const [summaryOpen, setSummaryOpen] = useState(false);

  const published = p.published ? formatDateWithOrdinal(p.published) : null;

  // Build Wayback URL from snapshot timestamp + original article URL (preferred)
  const waybackUrl =
    p.snapshot_ts && p.article_url
      ? `https://web.archive.org/web/${p.snapshot_ts}/${p.article_url}`
      : p.snapshot_ts && p.rss_url
      ? `https://web.archive.org/web/${p.snapshot_ts}/${p.rss_url}`
      : null;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 shadow-lg">

      {/* ── Headline ──────────────────────────────────────────────────── */}
      <h2 className="text-2xl font-semibold leading-snug mb-3 flex items-start justify-between">
        <span className="flex-1 pr-4">
          {published && <span>{published}: </span>}
          {p.title}
        </span>
        {waybackUrl && (
          <a
            href={waybackUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-2 text-gray-500 hover:text-indigo-400 transition-colors self-start"
            title="View Wayback Machine snapshot"
          >
            <ExternalLinkIcon />
          </a>
        )}
      </h2>

      {/* ── Prediction quote ──────────────────────────────────────────── */}
      <p className="text-lg text-indigo-300 italic mb-2">
        "{p.prediction}"
      </p>

      {/* ── Timeframe ────────────────────────────────────────────────── */}
      {p.timeframe && (
        <p className="text-sm text-gray-500 mb-4">
          {/* Expected Timeframe: {p.timeframe} */}
          {/* {p.target_year && <span> · {p.target_year}</span>} */}
        </p>
      )}

      {/* ── Collapsible article summary ───────────────────────────────── */}
      {p.summary && (
        <div className="mb-4">
          <button
            onClick={() => setSummaryOpen((o) => !o)}
            className="text-sm text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-2"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className="w-4 h-4 shrink-0"
            >
              <path d="M12.232 4.232a2.5 2.5 0 0 1 3.536 3.536l-1.225 1.224a.75.75 0 0 0 1.061 1.06l1.224-1.224a4 4 0 0 0-5.656-5.656l-3 3a4 4 0 0 0 .225 5.865.75.75 0 0 0 .977-1.138 2.5 2.5 0 0 1-.142-3.667l3-3Z" />
              <path d="M11.603 7.963a.75.75 0 0 0-.977 1.138 2.5 2.5 0 0 1 .142 3.667l-3 3a2.5 2.5 0 0 1-3.536-3.536l1.225-1.224a.75.75 0 0 0-1.061-1.06l-1.224 1.224a4 4 0 1 0 5.656 5.656l3-3a4 4 0 0 0-.225-5.865Z" />
            </svg>
            Article Summary
          </button>
          {summaryOpen && (
            <div
              className="mt-2 text-base text-gray-300 leading-relaxed border-l-2 border-gray-700 pl-3 [&_a]:text-indigo-400 [&_a]:underline [&_p]:mb-2 [&_img]:hidden"
              dangerouslySetInnerHTML={{ __html: p.summary }}
            />
          )}
        </div>
      )}

      {/* ── Consensus ────────────────────────────────────────────────── */}
      {p.score != null && (
        <div className="mb-3">
          <p className="text-xs uppercase tracking-widest text-gray-500 mb-1">Consensus</p>
          <ScoreBar score={p.score} />
        </div>
      )}

      {/* ── Result summary ───────────────────────────────────────────── */}
      {p.explanation && (
        <p className="text-sm text-gray-300 mb-4 mt-2">{p.explanation}</p>
      )}

      {/* ── Footer: votes + debug ─────────────────────────────────────── */}
      <div className="flex items-center justify-between mt-2 pt-3 border-t border-gray-800">
        <VoteButtons prediction={p} onVote={onVote} />
        <DebugLog log={p.debug_log} />
      </div>
    </div>
  );
}
