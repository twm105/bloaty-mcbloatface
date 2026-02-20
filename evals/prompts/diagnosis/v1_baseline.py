"""
Version: v1_baseline
Hypothesis: Original prompt - baseline measurement (no medical context passed)
Created: 2026-02-20
Result: Accuracy=0.927, P=0.864, R=1.000, F1=0.927 (41 cases, run ID 5, v2 dataset)
"""

ROOT_CAUSE_CLASSIFICATION_PROMPT = """You are evaluating whether a food is a real digestive trigger or an innocent bystander that should be discarded from results.

TASK: Decide if this ingredient should be KEPT as a likely trigger or DISCARDED as a false alarm.

KEY PRINCIPLE: Most foods that show statistical correlation are NOT actually causing symptoms. Be aggressive about discarding foods that are medically unlikely to cause digestive issues.

DECISION RULES:

**ALWAYS DISCARD** foods from the LOW-RISK list unless there's STRONG medical evidence:
- Plain cooked proteins: chicken, beef, pork, fish, turkey, lamb
- Basic starches: rice, plain potatoes, pasta, bread (unless gluten issue)
- Simple cooked vegetables: carrots, green beans, zucchini, spinach, peas
- Common seasonings: salt, black pepper, most dried herbs
- Low-FODMAP fruits: bananas, berries, grapes, citrus

**ONLY KEEP** foods from the HIGH-RISK list:
- High-FODMAP: garlic, onion, leeks, wheat, beans, lentils, lactose dairy
- Known allergens: peanuts, tree nuts, shellfish, eggs, soy
- Common intolerances: caffeine, alcohol, very spicy foods, fried foods
- High-fat dairy: butter, cream, full-fat cheese
- Nightshades (for some): tomatoes, peppers, eggplant

THE KEY INSIGHT: Foods like chicken, carrots, peas, and black pepper are eaten by billions of people daily with no digestive issues. They almost NEVER cause bloating or cramping. If they show correlation in someone's data, it's because they're eaten with actual triggers (onion, garlic, dairy, wheat). DISCARD them.

OUTPUT FORMAT (JSON only):
{
  "root_cause": true|false,
  "discard_justification": "Plain English explanation (or null if keeping)",
  "confounded_by": "likely_trigger_name or null",
  "medical_reasoning": "Brief medical explanation"
}

EXAMPLE - DISCARD (chicken):
{
  "root_cause": false,
  "discard_justification": "Chicken is a plain protein that almost never causes bloating or stomach problems. It's one of the most commonly recommended foods for people with digestive issues because it's so easy to digest. The correlation in your data is almost certainly from sauces, seasonings, or sides eaten with the chicken.",
  "confounded_by": null,
  "medical_reasoning": "Plain chicken contains no FODMAPs, fiber, or compounds linked to bloating. It's recommended even on elimination diets for IBS."
}

EXAMPLE - DISCARD (green peas):
{
  "root_cause": false,
  "discard_justification": "Green peas are a well-tolerated vegetable for most people. While legumes can cause issues, green peas are actually low-FODMAP in normal portions. Your symptoms are more likely from other foods in the same meals.",
  "confounded_by": null,
  "medical_reasoning": "Green peas in standard portions are low-FODMAP according to Monash University testing."
}

EXAMPLE - KEEP (leeks):
{
  "root_cause": true,
  "discard_justification": null,
  "confounded_by": null,
  "medical_reasoning": "Leeks are high-FODMAP, containing fructans that ferment in the gut and cause bloating and gas in sensitive people."
}

EXAMPLE - KEEP (butter):
{
  "root_cause": true,
  "discard_justification": null,
  "confounded_by": null,
  "medical_reasoning": "Butter is high in fat and contains lactose. Both can slow digestion and cause bloating, especially in people with lactose intolerance or fat malabsorption."
}

DEFAULT TO DISCARD: When in doubt, discard. Only keep foods with clear medical evidence as triggers.

Return ONLY valid JSON."""
