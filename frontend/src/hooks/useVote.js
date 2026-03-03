import { useState } from "react";

const STORAGE_KEY = "hdtd_votes";

function getVotes() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

/**
 * Track whether the current browser has already voted on a prediction.
 * Returns { voted: "up"|"down"|null, castVote(direction) }.
 */
export function useVote(predictionId) {
  const [votes, setVotes] = useState(getVotes);

  const voted = votes[predictionId] || null;

  const castVote = (direction) => {
    const updated = { ...votes, [predictionId]: direction };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    setVotes(updated);
  };

  return { voted, castVote };
}
