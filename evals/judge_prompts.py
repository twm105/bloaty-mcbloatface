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
