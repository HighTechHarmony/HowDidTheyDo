/**
 * Collapsible debug log viewer.
 */
export default function DebugLog({ log }) {
  if (!log || log.length === 0) return null;

  let entries;
  if (typeof log === "string") {
    try {
      entries = JSON.parse(log);
    } catch {
      entries = [log];
    }
  } else {
    entries = log;
  }

  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-gray-500 hover:text-gray-300 transition-colors">
        Debug log ({entries.length})
      </summary>
      <pre className="mt-2 p-3 bg-gray-950 border border-gray-800 rounded-lg overflow-x-auto text-gray-400 max-h-60 overflow-y-auto whitespace-pre-wrap">
        {entries.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </pre>
    </details>
  );
}
