-- Create test data for diagnosis feature
-- This creates realistic meal-symptom correlations for testing

-- Scenario: User has onion intolerance (immediate reaction)
-- Create 5 meals with raw onion, each followed by bloating 0.5-1.5 hours later

-- Meal 1: Feb 3, 2026 10:00 AM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-03 10:00:00+00:00', 'BREAKFAST', 'Onion omelette', 'published')
RETURNING id;

-- Get the last inserted meal_id (run this separately to get ID)
-- Assume meal_id = 22

-- Add onion ingredient to meal 22
INSERT INTO ingredients (normalized_name, created_by_user_id)
VALUES ('onion', '00000000-0000-0000-0000-000000000000')
ON CONFLICT (normalized_name) DO NOTHING;

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 22, id, 'RAW', 1, 'medium'
FROM ingredients WHERE normalized_name = 'onion';

-- Add symptom 1 hour later: bloating
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-03 11:00:00+00:00',
    NULL,
    '[{"name": "bloating", "severity": 7}]'::jsonb
);

-- Meal 2: Feb 3, 2026 6:00 PM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-03 18:00:00+00:00', 'DINNER', 'Salad with raw onion', 'published');
-- Assume meal_id = 23

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 23, id, 'RAW', 0.5, 'medium'
FROM ingredients WHERE normalized_name = 'onion';

-- Symptom 45 minutes later
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-03 18:45:00+00:00',
    NULL,
    '[{"name": "bloating", "severity": 6}, {"name": "cramping", "severity": 5}]'::jsonb
);

-- Meal 3: Feb 4, 2026 12:00 PM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-04 12:00:00+00:00', 'LUNCH', 'Sandwich with raw onion', 'published');
-- Assume meal_id = 24

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 24, id, 'RAW', 0.25, 'medium'
FROM ingredients WHERE normalized_name = 'onion';

-- Symptom 1.5 hours later
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-04 13:30:00+00:00',
    NULL,
    '[{"name": "bloating", "severity": 8}]'::jsonb
);

-- Meal 4: Feb 5, 2026 7:00 AM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-05 07:00:00+00:00', 'BREAKFAST', 'Veggie omelette with onion', 'published');
-- Assume meal_id = 25

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 25, id, 'RAW', 1, 'small'
FROM ingredients WHERE normalized_name = 'onion';

-- Symptom 1 hour later
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-05 08:00:00+00:00',
    NULL,
    '[{"name": "bloating", "severity": 7}, {"name": "gas", "severity": 6}]'::jsonb
);

-- Meal 5: Feb 5, 2026 1:00 PM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-05 13:00:00+00:00', 'LUNCH', 'Burrito with raw onion', 'published');
-- Assume meal_id = 26

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 26, id, 'RAW', 0.5, 'medium'
FROM ingredients WHERE normalized_name = 'onion';

-- Symptom 50 minutes later
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-05 13:50:00+00:00',
    NULL,
    '[{"name": "bloating", "severity": 9}, {"name": "cramping", "severity": 7}]'::jsonb
);

-- Scenario 2: User has milk intolerance (delayed reaction)
-- Create 5 meals with milk, each followed by symptoms 6-18 hours later

-- Create milk ingredient
INSERT INTO ingredients (normalized_name, created_by_user_id)
VALUES ('milk', '00000000-0000-0000-0000-000000000000')
ON CONFLICT (normalized_name) DO NOTHING;

-- Meal 1: Feb 3, 2026 8:00 AM (coffee with milk)
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-03 08:00:00+00:00', 'BREAKFAST', 'Coffee with milk', 'published');
-- Assume meal_id = 27

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 27, id, 'PROCESSED', 100, 'ml'
FROM ingredients WHERE normalized_name = 'milk';

-- Symptom 8 hours later (4PM): gas, cramping
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-03 16:00:00+00:00',
    NULL,
    '[{"name": "gas", "severity": 6}, {"name": "cramping", "severity": 5}]'::jsonb
);

-- Meal 2: Feb 4, 2026 9:00 AM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-04 09:00:00+00:00', 'BREAKFAST', 'Cereal with milk', 'published');
-- Assume meal_id = 28

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 28, id, 'PROCESSED', 200, 'ml'
FROM ingredients WHERE normalized_name = 'milk';

-- Symptom 10 hours later (7PM)
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-04 19:00:00+00:00',
    NULL,
    '[{"name": "gas", "severity": 7}, {"name": "bloating", "severity": 6}]'::jsonb
);

-- Meal 3: Feb 5, 2026 7:30 AM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-05 07:30:00+00:00', 'BREAKFAST', 'Latte', 'published');
-- Assume meal_id = 29

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 29, id, 'PROCESSED', 150, 'ml'
FROM ingredients WHERE normalized_name = 'milk';

-- Symptom 12 hours later (7:30 PM)
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-05 19:30:00+00:00',
    NULL,
    '[{"name": "gas", "severity": 8}, {"name": "cramping", "severity": 7}, {"name": "diarrhea", "severity": 6}]'::jsonb
);

-- Meal 4: Feb 6, 2026 8:00 AM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-06 08:00:00+00:00', 'BREAKFAST', 'Yogurt parfait with milk', 'published');
-- Assume meal_id = 30

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 30, id, 'PROCESSED', 100, 'ml'
FROM ingredients WHERE normalized_name = 'milk';

-- Symptom 6 hours later (2PM)
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-06 14:00:00+00:00',
    NULL,
    '[{"name": "bloating", "severity": 7}, {"name": "cramping", "severity": 6}]'::jsonb
);

-- Meal 5: Feb 6, 2026 10:00 AM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-06 10:00:00+00:00', 'SNACK', 'Cappuccino', 'published');
-- Assume meal_id = 31

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 31, id, 'PROCESSED', 120, 'ml'
FROM ingredients WHERE normalized_name = 'milk';

-- Symptom 14 hours later (midnight)
INSERT INTO symptoms (user_id, start_time, end_time, tags)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '2026-02-07 00:00:00+00:00',
    NULL,
    '[{"name": "gas", "severity": 8}, {"name": "bloating", "severity": 7}]'::jsonb
);

-- Control ingredient: chicken (no correlation)
-- Appears in 3 meals but WITHOUT subsequent symptoms

INSERT INTO ingredients (normalized_name, created_by_user_id)
VALUES ('chicken', '00000000-0000-0000-0000-000000000000')
ON CONFLICT (normalized_name) DO NOTHING;

-- Meal 1: Feb 3, 2026 12:30 PM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-03 12:30:00+00:00', 'LUNCH', 'Grilled chicken salad', 'published');
-- Assume meal_id = 32

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 32, id, 'COOKED', 150, 'g'
FROM ingredients WHERE normalized_name = 'chicken';

-- Meal 2: Feb 4, 2026 6:30 PM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-04 18:30:00+00:00', 'DINNER', 'Chicken breast with veggies', 'published');
-- Assume meal_id = 33

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 33, id, 'COOKED', 200, 'g'
FROM ingredients WHERE normalized_name = 'chicken';

-- Meal 3: Feb 5, 2026 7:00 PM
INSERT INTO meals (user_id, timestamp, type, notes, status)
VALUES ('00000000-0000-0000-0000-000000000000', '2026-02-05 19:00:00+00:00', 'DINNER', 'Chicken stir fry', 'published');
-- Assume meal_id = 34

INSERT INTO meal_ingredients (meal_id, ingredient_id, state, quantity, unit)
SELECT 34, id, 'COOKED', 180, 'g'
FROM ingredients WHERE normalized_name = 'chicken';

-- NO symptoms follow chicken meals (control)

COMMIT;
