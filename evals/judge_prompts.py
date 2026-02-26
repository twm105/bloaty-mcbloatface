"""Prompts for evaluation scoring with LLM-as-judge."""

INGREDIENT_MATCH_JUDGE_PROMPT = """You are an ingredient matching judge for a food tracking app evaluation.

Your task: Score how well a predicted ingredient matches against a list of expected ingredients.

## Scoring Rules

Return a JSON object with these fields:
- "score": 0, 0.5, or 1.0
- "matched_to": the expected ingredient name that best matches, or null if no match
- "reasoning": brief explanation (1 sentence)

### Score 1.0 - Exact/Equivalent Match
Same ingredient with different naming conventions:
- "parmesan cheese" = "parmesan" = "parmigiano" = "parmigiano-reggiano"
- "olive oil" = "extra virgin olive oil" = "EVOO"
- "chicken" = "chicken meat"
- "tomatoes" = "tomato"
- "cilantro" = "coriander" (in leaf form)

### Score 0.5 - Partial Match
The predicted is a reasonable subset or superset of an expected ingredient:
- "chicken" ~ "chicken breast" (species matches but cut is more specific)
- "cheese" ~ "cheddar cheese" (category matches but type is more specific)
- "onion" ~ "red onion" (ingredient matches but variety is more specific)
- "peppers" ~ "bell pepper" (category matches)

### Score 0.0 - No Match
The predicted ingredient doesn't appear in the expected list:
- "mushrooms" when expected has no mushrooms (false positive/hallucination)
- "beef" when expected only has "chicken"
- Completely unrelated ingredients

## Response Format

Always respond with valid JSON only, no other text:
{"score": 1.0, "matched_to": "ingredient_name", "reasoning": "explanation"}
"""

INGREDIENT_MATCH_USER_TEMPLATE = """Predicted ingredient: "{predicted}"

Expected ingredients:
{expected_list}

Score this prediction."""


# --- E2E Diagnosis Judge Prompts ---

CROSS_REFERENCING_JUDGE_PROMPT = """You are evaluating whether a food diagnosis explanation demonstrates cross-referencing across a user's meal history.

SCENARIO CONTEXT:
{scenario_description}

GROUND TRUTH:
- Real triggers: {triggers}
- Innocent bystanders: {bystanders}
- Key disambiguating evidence: {key_evidence}

SYSTEM OUTPUT FOR {ingredient_name}:
- Decision: {decision}
- Explanation: {diagnosis_summary}
- Recommendations: {recommendations_summary}

SCORING:
- 1.0: Explanation explicitly references patterns across multiple meals, mentions disambiguating evidence, explains why co-occurring foods were ruled in or out
- 0.5: Mentions the ingredient's own stats but doesn't reference patterns from other meals or other ingredients
- 0.0: Generic explanation with no reference to the user's specific history

Return ONLY a JSON object: {{"score": 0.0, "reasoning": "..."}}
Score must be exactly 0.0, 0.5, or 1.0."""

MEDICAL_ACCURACY_JUDGE_PROMPT = """You are evaluating whether a food diagnosis explanation contains accurate medical information.

INGREDIENT: {ingredient_name}
MEDICAL CONTEXT (ground truth): {medical_context}

SYSTEM OUTPUT:
- Explanation: {diagnosis_summary}
- Recommendations: {recommendations_summary}

SCORING:
- 1.0: Medical mechanisms are correct and specific (e.g., names fructans for garlic, lactose for dairy). No false claims.
- 0.5: Generally correct direction but vague or missing key mechanisms. No dangerous misinformation.
- 0.0: Contains incorrect medical claims or dangerous advice.

Return ONLY a JSON object: {{"score": 0.0, "reasoning": "..."}}
Score must be exactly 0.0, 0.5, or 1.0."""

PLAIN_ENGLISH_JUDGE_PROMPT = """You are evaluating whether a food diagnosis explanation is readable and actionable for a non-medical user.

SYSTEM OUTPUT FOR {ingredient_name}:
- Explanation: {diagnosis_summary}
- Recommendations: {recommendations_summary}

SCORING:
- 1.0: Clear, non-technical language. Avoids jargon or explains it. Actionable advice the user can follow.
- 0.5: Mostly readable but includes some unexplained technical terms or is vague about next steps.
- 0.0: Dense medical jargon, no actionable advice, or confusing structure.

Return ONLY a JSON object: {{"score": 0.0, "reasoning": "..."}}
Score must be exactly 0.0, 0.5, or 1.0."""

APPROPRIATE_UNCERTAINTY_JUDGE_PROMPT = """You are evaluating whether a food diagnosis explanation uses appropriate confidence language.

INGREDIENT: {ingredient_name}
CONFIDENCE LEVEL: {confidence_level}
EVIDENCE STRENGTH: {evidence_summary}

SYSTEM OUTPUT:
- Decision: {decision}
- Explanation: {diagnosis_summary}

SCORING:
- 1.0: Language matches confidence level. High confidence = clear statements. Medium/low = qualified language ("may", "could", "worth investigating"). Mixed evidence = acknowledges contradictions.
- 0.5: Somewhat appropriate but either too confident for weak evidence or too hedged for strong evidence.
- 0.0: Confidence language mismatches evidence. E.g., "definitely causes" for low-confidence data, or "might possibly" for 100% correlation.

Return ONLY a JSON object: {{"score": 0.0, "reasoning": "..."}}
Score must be exactly 0.0, 0.5, or 1.0."""
