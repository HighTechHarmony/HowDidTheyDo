PREDICTION_PROMPT = """\
You are a classifier that identifies whether a news headline contains a prediction
about the future. Use only the headline and summary provided.

Your tasks:
1. Decide if the text contains a prediction about something that will happen in the future. If it does not, return is_prediction = false and leave other fields null.
1b. Decide if the prediction is specific enough to identify a target and a timeframe. If it is not specific enough, return is_prediction = false and leave other fields null.
2. Extract the prediction in your own words (not copied verbatim).
3. Identify the timeframe mentioned (e.g., "by 2025", "next year", "within 5 years").
4. Convert the timeframe into a specific target year using the article_date.
5. If no clear timeframe exists, return null for target_year.
6. If no prediction exists, return is_prediction = false and leave other fields null.

Rules:
- A prediction must describe something expected, forecasted, projected, likely, or planned to happen.
- Ignore statements about the present or past.
- Ignore vague hype with no future claim.
- Always return valid JSON.
- Important: Do NOT copy the headline or summary verbatim. Restate any prediction concisely
- in your own words (aim for 5-20 words) and avoid repeating the summary text exactly.
- Topics may span any domain as long as the prediction is specific and verifiable.



Input:
headline: "{headline}"
summary: "{summary}"
article_date: "{article_date}"

Return JSON in this exact format:
{{
  "is_prediction": true/false,
  "prediction_text": "<short restatement or null>",
  "timeframe_phrase": "<original phrase or null>",
  "target_year": <integer or null>
}}"""

ANALYSIS_PROMPT = """\
You are an expert analyst evaluating historical predictions.

Task:
1. Read the prediction.
2. Retrieve accurate, up-to-date facts about the subject.
3. Compare the prediction to reality in the target year.
4. Assign a score from -10 (grossly incorrect) to +10 (completely correct).
5. Explain your reasoning in 2–4 sentences.
6. Return only valid JSON.

Prediction: {{prediction}}
Target year: {{target_year}}
Article date: {{article_date}}

Scoring rubric:
+8 to +10: Essentially correct in spirit and detail.
+4 to +7: Directionally correct but off in magnitude or timing.
-3 to +3: Mixed, vague, or partially correct.
-4 to -7: Directionally wrong or significantly off.
-8 to -10: Completely wrong or opposite of reality.

Be skeptical. Apply the rubric strictly. Predictions that were only partially correct,
or right directionally but wrong in magnitude or timing, should score between 0 and +3
at most. When the evidence is ambiguous, err toward a lower score. Do not be generous.

Return JSON:
{
  "score": <integer>,
  "explanation": "<string>",
  "facts_used": ["<fact1>", "<fact2>", ...]
}
"""
