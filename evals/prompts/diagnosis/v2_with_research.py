"""
Version: v2_with_research
Hypothesis: Medical context from research step enables evidence-based classification
    instead of hardcoded DISCARD/KEEP lists. Should fix gap foods (olive oil, oats, etc.)
    that v1 misclassifies because they appear in neither list.
Created: 2026-02-20
Result: Accuracy=1.000, P=1.000, R=1.000, F1=1.000 (41 cases, run ID 7, v2 dataset)
"""

ROOT_CAUSE_CLASSIFICATION_PROMPT = """You are evaluating whether a food is a real digestive trigger or an innocent bystander that should be discarded from results.

TASK: Decide if this ingredient should be KEPT as a likely trigger or DISCARDED as a false alarm.

KEY PRINCIPLE: Most foods that show statistical correlation are NOT actually causing symptoms. Be aggressive about discarding foods that are medically unlikely to cause digestive issues.

DECISION FRAMEWORK:

You will be given:
1. **Statistical data** — how often the food was eaten, how often symptoms followed, co-occurrence with other foods
2. **Medical context** — expert medical assessment of whether this food is a known digestive trigger

**CRITICAL: Weight the MEDICAL CONTEXT heavily.** It contains specific evidence about FODMAP content, allergen status, known intolerance mechanisms, and clinical guidance. Use it as your primary decision signal. Statistical correlation alone is not causation — foods eaten alongside real triggers will show spurious correlation.

DECISION RULES:

1. **If the medical context says "low_risk" or "no_known_risk"** → DISCARD the food. Statistical correlation is almost certainly from co-occurring trigger foods, not this ingredient itself.

2. **If the medical context says "high_risk"** with specific mechanisms (e.g., FODMAPs, allergens, lactose, histamine) → KEEP the food.

3. **If co-occurrence data shows the food is usually eaten with a known trigger** (garlic, onion, dairy, wheat, etc.) → this strengthens the case for DISCARD.

4. **If there is no co-occurrence** with known triggers but medical evidence says the food itself is a trigger → KEEP.

5. **When in doubt, defer to the medical context.** If the medical research says a food is safe and well-tolerated, discard it regardless of how strong the statistical correlation looks.

OUTPUT FORMAT (JSON only):
{
  "root_cause": true|false,
  "discard_justification": "Plain English explanation (or null if keeping)",
  "confounded_by": "likely_trigger_name or null",
  "medical_reasoning": "Brief medical explanation citing the medical context provided"
}

EXAMPLE - DISCARD (olive oil with medical context saying low-risk):
{
  "root_cause": false,
  "discard_justification": "Olive oil is a monounsaturated fat with no FODMAPs, no allergens, and no known digestive intolerance mechanisms. It's recommended on elimination diets. The correlation in your data is from foods cooked in the olive oil, not the oil itself.",
  "confounded_by": "garlic",
  "medical_reasoning": "Medical research confirms olive oil contains no FODMAPs and is well-tolerated even by IBS patients. It is the recommended cooking fat on low-FODMAP diets."
}

EXAMPLE - KEEP (garlic with medical context saying high-risk):
{
  "root_cause": true,
  "discard_justification": null,
  "confounded_by": null,
  "medical_reasoning": "Garlic is high-FODMAP containing fructans that ferment in the gut. Monash University testing confirms it as a common trigger for bloating and gas in IBS patients."
}

DEFAULT TO DISCARD: When in doubt, discard. Only keep foods with clear medical evidence as triggers.

Return ONLY valid JSON."""
