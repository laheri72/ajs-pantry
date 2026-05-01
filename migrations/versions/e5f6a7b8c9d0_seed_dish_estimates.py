"""seed dish estimates for 34 main dishes

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-01 10:00:00.000000

Seed data: 30-person ingredient estimates for all current global main dishes.
All quantities are calibrated for a standard pantry/hostel kitchen serving 30 people.
Super admin can edit any estimate via /platform-admin/dishes/<id>/estimate.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from datetime import datetime, timezone

# revision identifiers
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NOW = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)

# Minimal table proxy — only columns needed for INSERT; no FK resolution.
dish_estimate_table = table(
    'dish_estimate',
    column('dish_id',            sa.Integer()),
    column('serving_count',      sa.Integer()),
    column('summary',            sa.Text()),
    column('ingredients_json',   sa.JSON()),
    column('tips_json',          sa.JSON()),
    column('created_at',         sa.DateTime(timezone=True)),
    column('updated_at',         sa.DateTime(timezone=True)),
)

# ---------------------------------------------------------------------------
# Seed rows
# All dish_ids match the production dish table snapshot provided.
# Quantities are for serving_count = 30.
# ---------------------------------------------------------------------------

ESTIMATES = [

    # ── id:1  Omlette ────────────────────────────────────────────────────────
    dict(
        dish_id=1,
        serving_count=30,
        summary=(
            "A plain egg omelette cooked individually or in large batches. "
            "Estimate 2 eggs per person for a satisfying single-dish serving."
        ),
        ingredients_json=[
            {"name": "Eggs",          "qty": "60–65",    "unit": "pcs",  "note": "2 per person"},
            {"name": "Oil / Butter",  "qty": "150–200",  "unit": "ml",   "note": ""},
            {"name": "Onions",        "qty": "500",      "unit": "g",    "note": "finely chopped"},
            {"name": "Green chillies","qty": "10–12",    "unit": "pcs",  "note": "adjust for heat"},
            {"name": "Salt",          "qty": "to taste", "unit": "",     "note": ""},
            {"name": "Black pepper",  "qty": "2",        "unit": "tsp",  "note": ""},
            {"name": "Coriander",     "qty": "1",        "unit": "bunch","note": "garnish"},
        ],
        tips_json=[
            "Beat eggs in batches of 10–12 at a time for consistent texture.",
            "Use a wide non-stick or seasoned iron pan; avoid overcrowding.",
            "Cook on medium-high heat for soft, not rubbery, results.",
            "Pre-chop onions and chillies in one go before starting the run.",
        ],
    ),

    # ── id:2  Beda Khakra ────────────────────────────────────────────────────
    dict(
        dish_id=2,
        serving_count=30,
        summary=(
            "A Parsi breakfast favourite — crisp khakra topped with a spiced "
            "fried egg. One egg on one khakra per person is the standard portion."
        ),
        ingredients_json=[
            {"name": "Eggs",          "qty": "30–35",   "unit": "pcs",   "note": "1 per person"},
            {"name": "Khakra",        "qty": "30–35",   "unit": "pcs",   "note": "plain or masala"},
            {"name": "Butter",        "qty": "250",     "unit": "g",     "note": "for frying eggs"},
            {"name": "Green chillies","qty": "10",      "unit": "pcs",   "note": "finely chopped"},
            {"name": "Onions",        "qty": "300",     "unit": "g",     "note": "finely chopped, optional"},
            {"name": "Salt",          "qty": "to taste","unit": "",      "note": ""},
            {"name": "Black pepper",  "qty": "1",       "unit": "tsp",   "note": ""},
        ],
        tips_json=[
            "Fry eggs in butter over low heat so the yolk stays semi-runny.",
            "Slide the egg directly onto the khakra immediately before serving.",
            "Set up an assembly line: one person fries, one person plates.",
            "Khakra can be warmed in batches in a low oven (150 °C) to keep crisp.",
        ],
    ),

    # ── id:3  Kheema ─────────────────────────────────────────────────────────
    dict(
        dish_id=3,
        serving_count=30,
        summary=(
            "Spiced minced meat (chicken or mutton) dry or semi-dry curry. "
            "Plan 150 g raw mince per person, plus aromatics and spices."
        ),
        ingredients_json=[
            {"name": "Minced meat (chicken/mutton)", "qty": "4.5–5", "unit": "kg", "note": "raw weight"},
            {"name": "Onions",              "qty": "2",      "unit": "kg",  "note": "finely chopped"},
            {"name": "Tomatoes",            "qty": "1.5",    "unit": "kg",  "note": "chopped"},
            {"name": "Ginger-garlic paste", "qty": "200",    "unit": "g",   "note": ""},
            {"name": "Oil",                 "qty": "300",    "unit": "ml",  "note": ""},
            {"name": "Green peas",          "qty": "500",    "unit": "g",   "note": "optional"},
            {"name": "Red chilli powder",   "qty": "3",      "unit": "tbsp","note": ""},
            {"name": "Coriander powder",    "qty": "3",      "unit": "tbsp","note": ""},
            {"name": "Turmeric",            "qty": "1.5",    "unit": "tsp", "note": ""},
            {"name": "Garam masala",        "qty": "2",      "unit": "tbsp","note": ""},
            {"name": "Salt",                "qty": "to taste","unit": "",   "note": ""},
            {"name": "Coriander leaves",    "qty": "2",      "unit": "bunches","note": "garnish"},
        ],
        tips_json=[
            "Sauté onions until deep golden before adding mince — this is the base flavour.",
            "Cook mince on high heat initially to evaporate moisture, then lower to finish.",
            "Add peas in the last 8 minutes to keep them from going mushy.",
            "Resting for 5 minutes off heat deepens the flavour significantly.",
        ],
    ),

    # ── id:4  Butter Chicken ─────────────────────────────────────────────────
    dict(
        dish_id=4,
        serving_count=30,
        summary=(
            "Rich tomato-cream chicken curry. Use 150–180 g boneless chicken per "
            "person. The sauce can be made ahead and reheated without quality loss."
        ),
        ingredients_json=[
            {"name": "Boneless chicken",    "qty": "5–5.5",  "unit": "kg",  "note": "cut into chunks"},
            {"name": "Butter",              "qty": "400",    "unit": "g",   "note": "divided"},
            {"name": "Fresh cream",         "qty": "400",    "unit": "ml",  "note": ""},
            {"name": "Tomatoes",            "qty": "2",      "unit": "kg",  "note": "puréed or canned"},
            {"name": "Onions",              "qty": "1.5",    "unit": "kg",  "note": "sliced"},
            {"name": "Cashews",             "qty": "200",    "unit": "g",   "note": "soaked, for gravy body"},
            {"name": "Ginger-garlic paste", "qty": "200",    "unit": "g",   "note": ""},
            {"name": "Red chilli powder",   "qty": "3",      "unit": "tbsp","note": ""},
            {"name": "Kasuri methi",        "qty": "3",      "unit": "tbsp","note": "crushed"},
            {"name": "Garam masala",        "qty": "2",      "unit": "tbsp","note": ""},
            {"name": "Sugar",               "qty": "2",      "unit": "tsp", "note": "balances acidity"},
            {"name": "Salt",                "qty": "to taste","unit": "",   "note": ""},
        ],
        tips_json=[
            "Marinate chicken in yogurt, ginger-garlic, and spices for at least 2 hours.",
            "Blend the tomato-cashew gravy smooth before adding cream for restaurant texture.",
            "Finish with crushed kasuri methi — this is the signature aroma.",
            "Sauce can be prepared a day ahead; add cream only when reheating.",
        ],
    ),

    # ── id:5  Aloo Paratha ───────────────────────────────────────────────────
    dict(
        dish_id=5,
        serving_count=30,
        summary=(
            "Whole-wheat flatbread stuffed with spiced mashed potato. "
            "Allow 2 parathas per person; each paratha uses roughly 60 g dough "
            "and 50 g filling."
        ),
        ingredients_json=[
            {"name": "Whole wheat flour",   "qty": "2",      "unit": "kg",  "note": "for dough"},
            {"name": "Potatoes",            "qty": "3",      "unit": "kg",  "note": "boiled and mashed"},
            {"name": "Butter / Ghee",       "qty": "500",    "unit": "g",   "note": "for cooking and serving"},
            {"name": "Onions",              "qty": "500",    "unit": "g",   "note": "finely chopped"},
            {"name": "Green chillies",      "qty": "15–20",  "unit": "pcs", "note": ""},
            {"name": "Cumin seeds",         "qty": "2",      "unit": "tbsp","note": ""},
            {"name": "Amchur (dry mango)",  "qty": "2",      "unit": "tbsp","note": "for tang"},
            {"name": "Coriander leaves",    "qty": "2",      "unit": "bunches","note": ""},
            {"name": "Salt",                "qty": "to taste","unit": "",   "note": ""},
            {"name": "Yogurt / Pickle",     "qty": "500",    "unit": "g",   "note": "for serving"},
        ],
        tips_json=[
            "Keep dough slightly soft — stiffer dough tears when stuffing.",
            "Cool mashed potatoes completely before filling to avoid steam tearing the dough.",
            "Use a thick iron tawa; cook on medium-high with generous butter.",
            "Stack cooked parathas in a covered vessel with a cloth to stay soft.",
            "Serve with yogurt and pickle on the side for the classic experience.",
        ],
    ),

    # ── id:6  Stuffed Rice ───────────────────────────────────────────────────
    dict(
        dish_id=6,
        serving_count=30,
        summary=(
            "Rice stuffed or layered with a spiced filling (vegetable or chicken). "
            "Plan 100 g raw rice per person and 100–120 g filling per person."
        ),
        ingredients_json=[
            {"name": "Basmati / long-grain rice", "qty": "3",   "unit": "kg",  "note": "raw"},
            {"name": "Chicken / mixed vegetables", "qty": "2.5","unit": "kg",  "note": "filling"},
            {"name": "Onions",              "qty": "1",      "unit": "kg",  "note": "sliced"},
            {"name": "Tomatoes",            "qty": "1",      "unit": "kg",  "note": "chopped"},
            {"name": "Oil / Ghee",          "qty": "300",    "unit": "ml",  "note": ""},
            {"name": "Ginger-garlic paste", "qty": "150",    "unit": "g",   "note": ""},
            {"name": "Whole spices",        "qty": "1",      "unit": "set", "note": "bay leaf, cloves, cardamom, cinnamon"},
            {"name": "Mixed spice powder",  "qty": "3",      "unit": "tbsp","note": "biryani or garam masala"},
            {"name": "Fresh mint",          "qty": "1",      "unit": "bunch","note": ""},
            {"name": "Coriander leaves",    "qty": "1",      "unit": "bunch","note": ""},
            {"name": "Salt",                "qty": "to taste","unit": "",   "note": ""},
        ],
        tips_json=[
            "Par-cook rice to 70% before layering — it finishes in the dum (steam).",
            "Seal the pot tightly with foil or dough before the final dum steam.",
            "Rest for 10 minutes before opening to let steam redistribute.",
        ],
    ),

    # ── id:7  Alfredo ────────────────────────────────────────────────────────
    dict(
        dish_id=7,
        serving_count=30,
        summary=(
            "Creamy white sauce pasta. Use 80–100 g dry pasta per person. "
            "The sauce is butter, cream, and Parmesan — quality of these three "
            "ingredients determines the result."
        ),
        ingredients_json=[
            {"name": "Pasta (fettuccine/penne)","qty": "2.5–3","unit": "kg", "note": "dry weight"},
            {"name": "Butter",                  "qty": "400",  "unit": "g",  "note": ""},
            {"name": "Heavy cream",             "qty": "1",    "unit": "ltr","note": ""},
            {"name": "Parmesan / cheese",       "qty": "600",  "unit": "g",  "note": "grated"},
            {"name": "Garlic",                  "qty": "100",  "unit": "g",  "note": "minced"},
            {"name": "Milk",                    "qty": "500",  "unit": "ml", "note": "to adjust consistency"},
            {"name": "Black pepper",            "qty": "2",    "unit": "tbsp","note": ""},
            {"name": "Salt",                    "qty": "to taste","unit": "", "note": ""},
            {"name": "Parsley / Coriander",     "qty": "1",    "unit": "bunch","note": "garnish"},
            {"name": "Pasta water",             "qty": "1",    "unit": "cup","note": "reserved for loosening sauce"},
        ],
        tips_json=[
            "Salt the pasta water generously — it is the only chance to season the pasta itself.",
            "Do not let the cream sauce boil after adding cheese or it will split.",
            "Reserve a cup of starchy pasta water to loosen the sauce if it thickens.",
            "Toss pasta into sauce off the heat for the final 2 minutes.",
            "Serve immediately — Alfredo thickens and dulls quickly on standing.",
        ],
    ),

    # ── id:10 Dimsums ────────────────────────────────────────────────────────
    dict(
        dish_id=10,
        serving_count=30,
        summary=(
            "Steamed dumplings with a savoury filling. Allow 6–8 pieces per person "
            "(180–240 total). Chicken or mixed vegetable filling both work well."
        ),
        ingredients_json=[
            {"name": "Dimsum / dumpling wrappers","qty": "200–250","unit": "pcs", "note": "store-bought or fresh"},
            {"name": "Minced chicken / tofu",     "qty": "1.5",    "unit": "kg",  "note": "filling base"},
            {"name": "Cabbage",                   "qty": "700",    "unit": "g",   "note": "finely shredded"},
            {"name": "Carrots",                   "qty": "300",    "unit": "g",   "note": "grated"},
            {"name": "Spring onions",             "qty": "300",    "unit": "g",   "note": ""},
            {"name": "Ginger",                    "qty": "50",     "unit": "g",   "note": "grated"},
            {"name": "Garlic",                    "qty": "50",     "unit": "g",   "note": "minced"},
            {"name": "Soy sauce",                 "qty": "80",     "unit": "ml",  "note": ""},
            {"name": "Sesame oil",                "qty": "50",     "unit": "ml",  "note": ""},
            {"name": "Black pepper",              "qty": "2",      "unit": "tsp", "note": ""},
            {"name": "Cornflour",                 "qty": "3",      "unit": "tbsp","note": "binder"},
            {"name": "Dipping sauce (soy + vinegar + chilli)", "qty": "300","unit": "ml","note": ""},
        ],
        tips_json=[
            "Squeeze all moisture from shredded cabbage with a cloth before mixing filling.",
            "Chill the filling for 30 minutes before wrapping — easier to handle.",
            "Steam in batches of 20–25 on oiled steamers; 12–15 minutes per batch.",
            "Brush steamers with oil so wrappers do not stick.",
            "Prepare dipping sauce in advance: 2 parts soy : 1 part rice vinegar : chilli.",
        ],
    ),

    # ── id:11 Bhurji ─────────────────────────────────────────────────────────
    dict(
        dish_id=11,
        serving_count=30,
        summary=(
            "Classic Indian spiced scrambled eggs (egg bhurji). "
            "Use 2–3 eggs per person; 2 is sufficient as a main with bread."
        ),
        ingredients_json=[
            {"name": "Eggs",              "qty": "60–90",   "unit": "pcs",    "note": "2–3 per person"},
            {"name": "Onions",            "qty": "2",       "unit": "kg",     "note": "finely chopped"},
            {"name": "Tomatoes",          "qty": "1.5",     "unit": "kg",     "note": "chopped"},
            {"name": "Green chillies",    "qty": "15–20",   "unit": "pcs",    "note": ""},
            {"name": "Ginger-garlic paste","qty": "150",    "unit": "g",      "note": ""},
            {"name": "Oil / Butter",      "qty": "250",     "unit": "ml",     "note": ""},
            {"name": "Turmeric",          "qty": "1",       "unit": "tbsp",   "note": ""},
            {"name": "Red chilli powder", "qty": "2",       "unit": "tbsp",   "note": ""},
            {"name": "Garam masala",      "qty": "2",       "unit": "tbsp",   "note": ""},
            {"name": "Salt",              "qty": "to taste","unit": "",       "note": ""},
            {"name": "Coriander leaves",  "qty": "2",       "unit": "bunches","note": "garnish"},
        ],
        tips_json=[
            "Use a very large, wide kadai — overcrowding causes steaming instead of frying.",
            "Sauté onions until golden brown before adding tomatoes for deeper base flavour.",
            "Add eggs only when the onion-tomato masala is fully cooked and oil separates.",
            "Scramble continuously on medium heat; do not overcook or eggs turn rubbery.",
            "A knob of butter or a splash of cream at the end makes it richer.",
        ],
    ),

    # ── id:12 Shakshuka ──────────────────────────────────────────────────────
    dict(
        dish_id=12,
        serving_count=30,
        summary=(
            "Eggs poached in spiced tomato-pepper sauce. Use 2 eggs per person. "
            "Best served directly from the pan with bread for scooping."
        ),
        ingredients_json=[
            {"name": "Eggs",            "qty": "60–65",   "unit": "pcs",    "note": "2 per person"},
            {"name": "Tomatoes",        "qty": "4",       "unit": "kg",     "note": "or 3× 800g canned crushed"},
            {"name": "Bell peppers",    "qty": "1.5",     "unit": "kg",     "note": "red and yellow"},
            {"name": "Onions",          "qty": "1",       "unit": "kg",     "note": "diced"},
            {"name": "Garlic",          "qty": "150",     "unit": "g",      "note": "minced"},
            {"name": "Olive oil",       "qty": "200",     "unit": "ml",     "note": ""},
            {"name": "Cumin seeds",     "qty": "2",       "unit": "tbsp",   "note": ""},
            {"name": "Smoked paprika",  "qty": "3",       "unit": "tbsp",   "note": ""},
            {"name": "Cayenne / chilli","qty": "1",       "unit": "tbsp",   "note": "adjust for heat"},
            {"name": "Salt",            "qty": "to taste","unit": "",       "note": ""},
            {"name": "Feta cheese",     "qty": "300",     "unit": "g",      "note": "optional topping"},
            {"name": "Fresh parsley",   "qty": "2",       "unit": "bunches","note": "garnish"},
        ],
        tips_json=[
            "Build the sauce fully and taste for seasoning before adding eggs.",
            "Make wells in the sauce with a spoon, crack eggs directly into wells.",
            "Cover and cook on low heat 8–10 min for set whites with runny yolks.",
            "Use large wide pans; work in 2–3 pans simultaneously for 30 people.",
            "Serve immediately — eggs continue cooking in residual heat.",
        ],
    ),

    # ── id:13 French Toast ───────────────────────────────────────────────────
    dict(
        dish_id=13,
        serving_count=30,
        summary=(
            "Egg-soaked bread fried until golden. "
            "Allow 2–3 slices per person (60–90 slices total, roughly 4–5 loaves)."
        ),
        ingredients_json=[
            {"name": "Bread (sliced loaves)","qty": "4–5",  "unit": "loaves","note": "60–75 slices"},
            {"name": "Eggs",                 "qty": "20–25","unit": "pcs",   "note": "for the egg wash"},
            {"name": "Milk",                 "qty": "1",    "unit": "ltr",   "note": ""},
            {"name": "Butter",               "qty": "300",  "unit": "g",     "note": "for frying"},
            {"name": "Sugar",                "qty": "200",  "unit": "g",     "note": "in batter"},
            {"name": "Cinnamon powder",      "qty": "3",    "unit": "tbsp",  "note": ""},
            {"name": "Vanilla essence",      "qty": "2",    "unit": "tsp",   "note": ""},
            {"name": "Icing sugar / honey",  "qty": "100",  "unit": "g",     "note": "for serving"},
        ],
        tips_json=[
            "Whisk egg, milk, sugar, and cinnamon in a wide shallow tray for easy dipping.",
            "Soak each slice 10–15 seconds per side — not too long or bread disintegrates.",
            "Cook on medium heat; high heat burns the outside before the inside sets.",
            "Keep finished slices warm in a 120 °C oven while cooking the rest.",
            "Savory version: skip sugar and cinnamon, add salt, pepper, and chilli flakes.",
        ],
    ),

    # ── id:14 Chicken Seekh ──────────────────────────────────────────────────
    dict(
        dish_id=14,
        serving_count=30,
        summary=(
            "Spiced minced chicken kebabs grilled on skewers. "
            "Plan 150 g raw mince per person; each skewer holds roughly 100–120 g."
        ),
        ingredients_json=[
            {"name": "Minced chicken",      "qty": "4.5",    "unit": "kg",     "note": "raw, double-minced"},
            {"name": "Onions",              "qty": "1",      "unit": "kg",     "note": "finely chopped, moisture squeezed"},
            {"name": "Ginger-garlic paste", "qty": "150",    "unit": "g",      "note": ""},
            {"name": "Green chillies",      "qty": "15",     "unit": "pcs",    "note": "minced"},
            {"name": "Roasted chana dal powder","qty": "150","unit": "g",      "note": "binder"},
            {"name": "Garam masala",        "qty": "2",      "unit": "tbsp",   "note": ""},
            {"name": "Cumin powder",        "qty": "2",      "unit": "tbsp",   "note": ""},
            {"name": "Red chilli powder",   "qty": "2",      "unit": "tbsp",   "note": ""},
            {"name": "Fresh coriander",     "qty": "2",      "unit": "bunches","note": "finely chopped"},
            {"name": "Fresh mint",          "qty": "1",      "unit": "bunch",  "note": "finely chopped"},
            {"name": "Oil",                 "qty": "100",    "unit": "ml",     "note": "for basting"},
            {"name": "Salt",                "qty": "to taste","unit": "",      "note": ""},
        ],
        tips_json=[
            "Squeeze all moisture from onions using a cloth before mixing — wet mix won't hold.",
            "Chill the mix for 1 hour before shaping; it firms up and is easier to skewer.",
            "Wet your hands before pressing mix onto skewers to prevent sticking.",
            "Grill at high heat, turning every 2–3 minutes; baste with oil each turn.",
            "Serve with mint chutney and sliced onion rings.",
        ],
    ),

    # ── id:15 Spring Rolls ───────────────────────────────────────────────────
    dict(
        dish_id=15,
        serving_count=30,
        summary=(
            "Crispy deep-fried rolls with a savoury filling. "
            "Allow 4–5 pieces per person (120–150 total)."
        ),
        ingredients_json=[
            {"name": "Spring roll wrappers","qty": "150",   "unit": "pcs",   "note": "6-inch size"},
            {"name": "Cabbage",             "qty": "1",     "unit": "kg",    "note": "shredded"},
            {"name": "Carrots",             "qty": "500",   "unit": "g",     "note": "julienned"},
            {"name": "Bean sprouts",        "qty": "500",   "unit": "g",     "note": ""},
            {"name": "Chicken / paneer",    "qty": "1",     "unit": "kg",    "note": "thinly sliced or shredded"},
            {"name": "Spring onions",       "qty": "200",   "unit": "g",     "note": ""},
            {"name": "Soy sauce",           "qty": "80",    "unit": "ml",    "note": ""},
            {"name": "Sesame oil",          "qty": "3",     "unit": "tbsp",  "note": ""},
            {"name": "Ginger-garlic paste", "qty": "100",   "unit": "g",     "note": ""},
            {"name": "Cornflour",           "qty": "4",     "unit": "tbsp",  "note": "for sealing flap"},
            {"name": "Oil",                 "qty": "1.5",   "unit": "ltr",   "note": "for deep frying"},
            {"name": "Salt & pepper",       "qty": "to taste","unit": "",    "note": ""},
        ],
        tips_json=[
            "Squeeze filling completely dry before rolling — moisture makes wrappers soggy.",
            "Roll tightly with no air pockets; seal the flap with cornflour paste.",
            "Fry in oil at 175–180 °C; lower temperature makes them oily.",
            "Fry in batches of 10–12; do not crowd the oil.",
            "Keep finished rolls in a 120 °C oven uncovered to stay crispy.",
        ],
    ),

    # ── id:17 Poha ───────────────────────────────────────────────────────────
    dict(
        dish_id=17,
        serving_count=30,
        summary=(
            "Flattened rice tempered with mustard, turmeric, and peanuts — "
            "a light, quick breakfast. Use 100 g dry poha per person."
        ),
        ingredients_json=[
            {"name": "Poha (flattened rice)","qty": "3",    "unit": "kg",    "note": "medium or thick variety"},
            {"name": "Onions",               "qty": "1.5",  "unit": "kg",    "note": "finely chopped"},
            {"name": "Oil",                  "qty": "300",  "unit": "ml",    "note": ""},
            {"name": "Mustard seeds",        "qty": "3",    "unit": "tbsp",  "note": ""},
            {"name": "Curry leaves",         "qty": "4",    "unit": "sprigs","note": ""},
            {"name": "Green chillies",       "qty": "15",   "unit": "pcs",   "note": ""},
            {"name": "Turmeric",             "qty": "2",    "unit": "tsp",   "note": ""},
            {"name": "Roasted peanuts",      "qty": "300",  "unit": "g",     "note": ""},
            {"name": "Lemons",               "qty": "5",    "unit": "pcs",   "note": "juice"},
            {"name": "Sugar",                "qty": "2",    "unit": "tsp",   "note": "optional balance"},
            {"name": "Salt",                 "qty": "to taste","unit": "",   "note": ""},
            {"name": "Coriander leaves",     "qty": "1",    "unit": "bunch", "note": "garnish"},
            {"name": "Fresh coconut",        "qty": "100",  "unit": "g",     "note": "grated, optional"},
        ],
        tips_json=[
            "Rinse poha and drain well 5 minutes before cooking — it should be moist but not wet.",
            "Taste a grain; it should feel soft with no crunch. If too hard, sprinkle water and wait.",
            "Temper mustard in hot oil until it splutters before adding onions.",
            "Add poha off the heat to prevent over-cooking — fold gently to coat evenly.",
            "Squeeze lemon and scatter peanuts just before serving.",
        ],
    ),

    # ── id:19 Cheese Omelette ────────────────────────────────────────────────
    dict(
        dish_id=19,
        serving_count=30,
        summary=(
            "Egg omelette filled with melted cheese. "
            "2 eggs per person with 20–25 g cheese each."
        ),
        ingredients_json=[
            {"name": "Eggs",                   "qty": "60–65","unit": "pcs",   "note": "2 per person"},
            {"name": "Processed / cheddar cheese","qty": "600","unit": "g",   "note": "grated or sliced"},
            {"name": "Butter",                 "qty": "250",  "unit": "g",    "note": "for cooking"},
            {"name": "Onions",                 "qty": "400",  "unit": "g",    "note": "finely chopped"},
            {"name": "Green chillies",         "qty": "10",   "unit": "pcs",  "note": "optional"},
            {"name": "Milk",                   "qty": "200",  "unit": "ml",   "note": "splash per batch for fluffiness"},
            {"name": "Salt & white pepper",    "qty": "to taste","unit": "",  "note": ""},
        ],
        tips_json=[
            "Add a splash of milk to each egg batch for a fluffier texture.",
            "Place cheese on one half while the omelette is still wet, then fold.",
            "Cover with a lid for 30 seconds — trapped steam melts the cheese perfectly.",
            "Cook on medium heat; cheese burns fast on high heat.",
        ],
    ),

    # ── id:20 Chicken Sandwich ───────────────────────────────────────────────
    dict(
        dish_id=20,
        serving_count=30,
        summary=(
            "Chicken filling sandwiched in sliced bread. "
            "One generous sandwich per person uses roughly 80–100 g chicken filling."
        ),
        ingredients_json=[
            {"name": "Bread (sliced loaves)","qty": "4–5",  "unit": "loaves","note": "2 slices per sandwich"},
            {"name": "Chicken breast",       "qty": "3",    "unit": "kg",    "note": "cooked and shredded"},
            {"name": "Mayonnaise",           "qty": "500",  "unit": "g",     "note": ""},
            {"name": "Lettuce",              "qty": "2",    "unit": "heads", "note": ""},
            {"name": "Tomatoes",             "qty": "500",  "unit": "g",     "note": "sliced"},
            {"name": "Butter",               "qty": "200",  "unit": "g",     "note": "for bread"},
            {"name": "Black pepper",         "qty": "2",    "unit": "tsp",   "note": ""},
            {"name": "Mustard sauce",        "qty": "100",  "unit": "g",     "note": "optional"},
            {"name": "Salt",                 "qty": "to taste","unit": "",   "note": ""},
        ],
        tips_json=[
            "Season shredded chicken while still warm — it absorbs flavour better.",
            "Mix chicken with mayo and seasoning, then refrigerate before assembling.",
            "Butter bread on both sides to prevent sogginess from filling.",
            "Assemble close to service time; pre-assembled sandwiches go soggy.",
        ],
    ),

    # ── id:21 Utappam ────────────────────────────────────────────────────────
    dict(
        dish_id=21,
        serving_count=30,
        summary=(
            "Thick South Indian rice and lentil pancakes with vegetable toppings. "
            "Allow 2 per person; each uses roughly 120 ml batter."
        ),
        ingredients_json=[
            {"name": "Fermented dosa batter","qty": "5–6",  "unit": "kg",    "note": "or grind 3 kg rice + 1 kg urad dal"},
            {"name": "Onions",               "qty": "1",    "unit": "kg",    "note": "finely chopped"},
            {"name": "Tomatoes",             "qty": "800",  "unit": "g",     "note": "finely chopped"},
            {"name": "Green chillies",       "qty": "15",   "unit": "pcs",   "note": ""},
            {"name": "Coriander leaves",     "qty": "2",    "unit": "bunches","note": ""},
            {"name": "Oil",                  "qty": "400",  "unit": "ml",    "note": "for cooking"},
            {"name": "Salt",                 "qty": "to taste","unit": "",   "note": "if batter is unsalted"},
            {"name": "Coconut chutney",      "qty": "500",  "unit": "g",     "note": "for serving"},
            {"name": "Sambar",               "qty": "2",    "unit": "ltr",   "note": "for serving"},
        ],
        tips_json=[
            "Batter should be slightly thick — thicker than dosa batter.",
            "Pour batter on a medium-hot tawa and do not spread; let it settle naturally.",
            "Scatter toppings immediately while batter is still wet so they embed.",
            "Cover with a lid and cook on medium heat until edges lift, then flip briefly.",
            "Prepare sambar and chutney first — they are the essential accompaniments.",
        ],
    ),

    # ── id:22 Samosa Bhel ────────────────────────────────────────────────────
    dict(
        dish_id=22,
        serving_count=30,
        summary=(
            "Crushed samosas mixed with bhel-style chutneys, sev, and vegetables. "
            "Allow 2–3 samosas per person plus bhel toppings."
        ),
        ingredients_json=[
            {"name": "Samosas",             "qty": "60–90", "unit": "pcs",   "note": "small to medium size"},
            {"name": "Sev",                 "qty": "500",   "unit": "g",     "note": "thin variety"},
            {"name": "Tamarind chutney",    "qty": "400",   "unit": "ml",    "note": ""},
            {"name": "Green chutney",       "qty": "300",   "unit": "ml",    "note": "mint-coriander"},
            {"name": "Onions",              "qty": "500",   "unit": "g",     "note": "finely chopped"},
            {"name": "Tomatoes",            "qty": "400",   "unit": "g",     "note": "chopped"},
            {"name": "Coriander leaves",    "qty": "1",     "unit": "bunch", "note": ""},
            {"name": "Chaat masala",        "qty": "50",    "unit": "g",     "note": ""},
            {"name": "Red chilli powder",   "qty": "1",     "unit": "tbsp",  "note": ""},
            {"name": "Puffed rice",         "qty": "300",   "unit": "g",     "note": "optional bulk"},
            {"name": "Lemon",               "qty": "4",     "unit": "pcs",   "note": "juice"},
        ],
        tips_json=[
            "Assemble just before serving — samosas go soggy quickly once dressed.",
            "Crush samosas roughly; keep some larger pieces for texture.",
            "Adjust chutney quantities to taste: more tamarind for sweet-sour, more green for spicy.",
            "Add sev last, right before serving, to keep it crunchy.",
        ],
    ),

    # ── id:23 Sausage Tarkari ────────────────────────────────────────────────
    dict(
        dish_id=23,
        serving_count=30,
        summary=(
            "Sausages cooked in a spiced onion-tomato gravy. "
            "Allow 2–3 sausages per person (roughly 3 kg total)."
        ),
        ingredients_json=[
            {"name": "Sausages (chicken/pork)","qty": "3",  "unit": "kg",    "note": "sliced or whole"},
            {"name": "Onions",               "qty": "1.5",  "unit": "kg",    "note": "sliced"},
            {"name": "Tomatoes",             "qty": "1",    "unit": "kg",    "note": "chopped"},
            {"name": "Ginger-garlic paste",  "qty": "150",  "unit": "g",     "note": ""},
            {"name": "Oil",                  "qty": "200",  "unit": "ml",    "note": ""},
            {"name": "Red chilli powder",    "qty": "2",    "unit": "tbsp",  "note": ""},
            {"name": "Turmeric",             "qty": "1",    "unit": "tsp",   "note": ""},
            {"name": "Garam masala",         "qty": "1.5",  "unit": "tbsp",  "note": ""},
            {"name": "Bell peppers",         "qty": "500",  "unit": "g",     "note": "optional"},
            {"name": "Salt",                 "qty": "to taste","unit": "",   "note": "sausages are already salted"},
            {"name": "Coriander leaves",     "qty": "1",    "unit": "bunch", "note": "garnish"},
        ],
        tips_json=[
            "Prick sausages before cooking to prevent bursting in the masala.",
            "Brown sausages in a separate pan first; add to gravy to finish — better texture.",
            "Note sausages are already salted; taste before adding extra salt.",
            "Add bell peppers in the last 5 minutes to retain colour and crunch.",
        ],
    ),

    # ── id:24 Paamplet (Pomfret) ─────────────────────────────────────────────
    dict(
        dish_id=24,
        serving_count=30,
        summary=(
            "Pomfret fish — fried, grilled, or in a Goan/Malvani style curry. "
            "Allow one medium fish (250–300 g) per person, or 200 g fillet per person."
        ),
        ingredients_json=[
            {"name": "Pomfret fish",        "qty": "8–9",   "unit": "kg",    "note": "whole, cleaned, scored"},
            {"name": "Red chilli powder",   "qty": "4",     "unit": "tbsp",  "note": ""},
            {"name": "Turmeric",            "qty": "2",     "unit": "tsp",   "note": ""},
            {"name": "Coriander powder",    "qty": "3",     "unit": "tbsp",  "note": ""},
            {"name": "Ginger-garlic paste", "qty": "200",   "unit": "g",     "note": ""},
            {"name": "Lemon juice",         "qty": "150",   "unit": "ml",    "note": "for marinade"},
            {"name": "Oil",                 "qty": "400",   "unit": "ml",    "note": "for frying"},
            {"name": "Onions",              "qty": "1",     "unit": "kg",    "note": "if making curry"},
            {"name": "Coconut milk",        "qty": "500",   "unit": "ml",    "note": "for curry version"},
            {"name": "Kokum / tamarind",    "qty": "50",    "unit": "g",     "note": "souring agent for curry"},
            {"name": "Salt",                "qty": "to taste","unit": "",    "note": ""},
            {"name": "Coriander leaves",    "qty": "1",     "unit": "bunch", "note": "garnish"},
        ],
        tips_json=[
            "Score fish deeply so marinade penetrates to the bone.",
            "Marinate for at least 1 hour; overnight is best for full flavour.",
            "Fry in batches in very hot oil — crowding drops temperature and fish sticks.",
            "For curry: add fish in the last 8–10 minutes; overcooking makes it fall apart.",
            "Serve immediately — fried pomfret loses crispiness quickly.",
        ],
    ),

    # ── id:26 Scramble ───────────────────────────────────────────────────────
    dict(
        dish_id=26,
        serving_count=30,
        summary=(
            "Soft scrambled eggs — simple and fast. "
            "2–3 eggs per person; 2 is sufficient alongside bread."
        ),
        ingredients_json=[
            {"name": "Eggs",          "qty": "60–75",   "unit": "pcs",   "note": "2–3 per person"},
            {"name": "Butter",        "qty": "200",     "unit": "g",     "note": ""},
            {"name": "Milk / cream",  "qty": "500",     "unit": "ml",    "note": "optional for creaminess"},
            {"name": "Salt",          "qty": "to taste","unit": "",      "note": ""},
            {"name": "Black pepper",  "qty": "2",       "unit": "tsp",   "note": ""},
            {"name": "Chives / parsley","qty": "1",     "unit": "bunch", "note": "garnish"},
        ],
        tips_json=[
            "Whisk eggs with a splash of milk until fully combined.",
            "Use medium-low heat and a rubber spatula — patience gives creamier eggs.",
            "Pull pan off heat while eggs still look slightly wet; residual heat finishes them.",
            "Cook in batches of 10–12 eggs for best control.",
        ],
    ),

    # ── id:28 Barbeque Chicken Sandwich ──────────────────────────────────────
    dict(
        dish_id=28,
        serving_count=30,
        summary=(
            "Smoky BBQ-glazed chicken in a toasted bun or bread. "
            "Allow 100–120 g cooked chicken per sandwich."
        ),
        ingredients_json=[
            {"name": "Chicken thighs / breast","qty": "4", "unit": "kg",    "note": "boneless"},
            {"name": "BBQ sauce",            "qty": "600",  "unit": "ml",    "note": "use a good quality sauce"},
            {"name": "Burger buns / bread",  "qty": "30",   "unit": "pcs",   "note": "or 4–5 loaves sliced"},
            {"name": "Coleslaw",             "qty": "1",    "unit": "kg",    "note": "cabbage + carrot + mayo"},
            {"name": "Lettuce",              "qty": "2",    "unit": "heads", "note": ""},
            {"name": "Butter",               "qty": "200",  "unit": "g",     "note": "for toasting buns"},
            {"name": "Smoked paprika",       "qty": "2",    "unit": "tbsp",  "note": "dry rub"},
            {"name": "Garlic powder",        "qty": "1",    "unit": "tbsp",  "note": "dry rub"},
            {"name": "Salt & pepper",        "qty": "to taste","unit": "",   "note": ""},
        ],
        tips_json=[
            "Marinate chicken in half the BBQ sauce overnight for deeper flavour.",
            "Grill or pan-sear on high heat to get char marks, then glaze with remaining sauce.",
            "Shred or slice chicken; toss in residual pan juices before assembling.",
            "Toast buns cut-side down in butter until golden before filling.",
            "Prepare coleslaw a day ahead — it improves as it sits.",
        ],
    ),

    # ── id:29 Scramble Garlic ────────────────────────────────────────────────
    dict(
        dish_id=29,
        serving_count=30,
        summary=(
            "Garlicky scrambled eggs with a punchy aroma. "
            "2–3 eggs per person with generously sautéed garlic."
        ),
        ingredients_json=[
            {"name": "Eggs",          "qty": "60–75",   "unit": "pcs",   "note": "2–3 per person"},
            {"name": "Garlic",        "qty": "200",     "unit": "g",     "note": "thinly sliced or minced"},
            {"name": "Butter",        "qty": "250",     "unit": "g",     "note": ""},
            {"name": "Milk / cream",  "qty": "300",     "unit": "ml",    "note": "optional"},
            {"name": "Black pepper",  "qty": "2",       "unit": "tbsp",  "note": "coarsely cracked"},
            {"name": "Fresh parsley / chives","qty": "1","unit": "bunch","note": ""},
            {"name": "Salt",          "qty": "to taste","unit": "",      "note": ""},
        ],
        tips_json=[
            "Sauté garlic in butter on low heat until golden and fragrant — do not burn.",
            "Remove pan from heat briefly before adding eggs so garlic does not overcook.",
            "Fold eggs gently over low heat; generous garlic butter is the star.",
            "Crack fresh black pepper generously at the end.",
        ],
    ),

    # ── id:30 Egg Curry ──────────────────────────────────────────────────────
    dict(
        dish_id=30,
        serving_count=30,
        summary=(
            "Hard-boiled eggs in a spiced onion-tomato gravy. "
            "2 eggs per person; halve or keep whole depending on gravy consistency."
        ),
        ingredients_json=[
            {"name": "Eggs",              "qty": "60–65",   "unit": "pcs",    "note": "hard-boiled"},
            {"name": "Onions",            "qty": "2",       "unit": "kg",     "note": "finely chopped"},
            {"name": "Tomatoes",          "qty": "1.5",     "unit": "kg",     "note": "chopped or pureed"},
            {"name": "Oil",               "qty": "300",     "unit": "ml",     "note": ""},
            {"name": "Ginger-garlic paste","qty": "150",    "unit": "g",      "note": ""},
            {"name": "Red chilli powder", "qty": "3",       "unit": "tbsp",   "note": ""},
            {"name": "Coriander powder",  "qty": "3",       "unit": "tbsp",   "note": ""},
            {"name": "Turmeric",          "qty": "1.5",     "unit": "tsp",    "note": ""},
            {"name": "Garam masala",      "qty": "2",       "unit": "tbsp",   "note": ""},
            {"name": "Coconut milk",      "qty": "400",     "unit": "ml",     "note": "optional for South Indian style"},
            {"name": "Salt",              "qty": "to taste","unit": "",       "note": ""},
            {"name": "Coriander leaves",  "qty": "2",       "unit": "bunches","note": "garnish"},
        ],
        tips_json=[
            "Lightly fry hard-boiled eggs in turmeric-oil before adding to gravy — better texture.",
            "Make the base gravy first, then score or halve eggs and simmer for 5–8 minutes.",
            "For a richer gravy, blend half the onion-tomato base smooth before adding eggs.",
            "Do not over-simmer once eggs are added — they become rubbery.",
        ],
    ),

    # ── id:32 Lucknawi Tarkari ───────────────────────────────────────────────
    dict(
        dish_id=32,
        serving_count=30,
        summary=(
            "Lucknow-style richly spiced curry — typically egg or chicken — "
            "slow-cooked with whole spices and a cream-yogurt finish."
        ),
        ingredients_json=[
            {"name": "Eggs (boiled) or chicken","qty": "60 eggs or 4 kg chicken","unit": "","note": ""},
            {"name": "Onions",              "qty": "2",      "unit": "kg",     "note": "thinly sliced, fried golden"},
            {"name": "Yogurt",              "qty": "500",    "unit": "g",      "note": "whisked"},
            {"name": "Fresh cream",         "qty": "200",    "unit": "ml",     "note": ""},
            {"name": "Ginger-garlic paste", "qty": "200",    "unit": "g",      "note": ""},
            {"name": "Whole spices",        "qty": "1",      "unit": "set",    "note": "bay leaf, cloves, black cardamom, star anise, mace"},
            {"name": "Red chilli powder",   "qty": "2",      "unit": "tbsp",   "note": "Kashmiri for colour"},
            {"name": "Coriander powder",    "qty": "3",      "unit": "tbsp",   "note": ""},
            {"name": "Garam masala",        "qty": "2",      "unit": "tbsp",   "note": ""},
            {"name": "Kewra water",         "qty": "2",      "unit": "tsp",    "note": "finishing aroma"},
            {"name": "Oil / Ghee",          "qty": "300",    "unit": "ml",     "note": ""},
            {"name": "Salt",                "qty": "to taste","unit": "",      "note": ""},
        ],
        tips_json=[
            "Fry onions very slowly until deep brown — Lucknawi gravy depth comes from this step.",
            "Add whisked yogurt on low heat, stirring constantly to prevent splitting.",
            "Whole spices are the soul of this dish; do not skip or substitute.",
            "Kewra water is the signature finishing touch; add just before serving.",
        ],
    ),

    # ── id:34 Pancakes ───────────────────────────────────────────────────────
    dict(
        dish_id=34,
        serving_count=30,
        summary=(
            "Fluffy breakfast pancakes. "
            "Allow 2–3 pancakes per person; each uses roughly 80 ml batter."
        ),
        ingredients_json=[
            {"name": "All-purpose flour",   "qty": "2.5",    "unit": "kg",    "note": ""},
            {"name": "Eggs",                "qty": "20–25",  "unit": "pcs",   "note": ""},
            {"name": "Milk",                "qty": "3",      "unit": "ltr",   "note": ""},
            {"name": "Butter",              "qty": "400",    "unit": "g",     "note": "melted + extra for pan"},
            {"name": "Sugar",               "qty": "300",    "unit": "g",     "note": ""},
            {"name": "Baking powder",       "qty": "100",    "unit": "g",     "note": "level, not heaped"},
            {"name": "Salt",                "qty": "2",      "unit": "tsp",   "note": ""},
            {"name": "Vanilla essence",     "qty": "2",      "unit": "tbsp",  "note": ""},
            {"name": "Maple syrup / honey", "qty": "500",    "unit": "ml",    "note": "for serving"},
        ],
        tips_json=[
            "Do not over-mix batter — lumps are fine; over-mixing makes pancakes tough.",
            "Rest batter 10 minutes before cooking; baking powder activates.",
            "Cook on medium heat; when bubbles form on top and edges look dry, flip once.",
            "Keep finished pancakes in a 100 °C oven stacked with a cloth on top.",
            "Batter can be made the night before and refrigerated (add baking powder just before cooking).",
        ],
    ),

    # ── id:35 Half Fry Peri Peri ─────────────────────────────────────────────
    dict(
        dish_id=35,
        serving_count=30,
        summary=(
            "Fried eggs (half-fry / sunny-side up) seasoned with peri peri spice. "
            "1 egg per person as a side, 2 if main."
        ),
        ingredients_json=[
            {"name": "Eggs",             "qty": "30–60",   "unit": "pcs",   "note": "1–2 per person"},
            {"name": "Butter / Oil",     "qty": "200",     "unit": "ml",    "note": ""},
            {"name": "Peri peri seasoning","qty": "80–100","unit": "g",     "note": "store-bought or blend"},
            {"name": "Garlic powder",    "qty": "2",       "unit": "tsp",   "note": ""},
            {"name": "Smoked paprika",   "qty": "2",       "unit": "tsp",   "note": ""},
            {"name": "Salt",             "qty": "to taste","unit": "",      "note": "peri peri blends are salted"},
            {"name": "Lemon wedges",     "qty": "5",       "unit": "pcs",   "note": "for serving"},
        ],
        tips_json=[
            "Heat pan well before adding butter for clean whites with no sticking.",
            "Cook on medium heat; cover with a lid for 1 minute to set the white without flipping.",
            "Sprinkle peri peri while egg is still hot so seasoning adheres.",
            "Work in batches of 4–6 eggs per pan for consistent results.",
        ],
    ),

    # ── id:36 Salami Sandwich ────────────────────────────────────────────────
    dict(
        dish_id=36,
        serving_count=30,
        summary=(
            "Cold-cut salami layered with cheese and condiments in sliced bread. "
            "One generous sandwich per person."
        ),
        ingredients_json=[
            {"name": "Bread (sliced loaves)","qty": "4–5",  "unit": "loaves","note": "2 slices per sandwich"},
            {"name": "Salami",               "qty": "1.5",  "unit": "kg",    "note": "thinly sliced"},
            {"name": "Cheese slices / cheddar","qty": "600","unit": "g",     "note": ""},
            {"name": "Mayonnaise",           "qty": "400",  "unit": "g",     "note": ""},
            {"name": "Mustard",              "qty": "150",  "unit": "g",     "note": ""},
            {"name": "Lettuce",              "qty": "2",    "unit": "heads", "note": ""},
            {"name": "Tomatoes",             "qty": "500",  "unit": "g",     "note": "sliced"},
            {"name": "Butter",               "qty": "200",  "unit": "g",     "note": ""},
            {"name": "Black pepper",         "qty": "1",    "unit": "tsp",   "note": ""},
        ],
        tips_json=[
            "Layer salami in slightly overlapping folds — more surface area per bite.",
            "Spread mayo on one slice, mustard on the other for balanced flavour.",
            "Butter the outside of the bread if toasting on a griddle.",
            "Assemble to order where possible; fully built sandwiches go soggy in 30 min.",
        ],
    ),

    # ── id:39 Egg Sandwich ───────────────────────────────────────────────────
    dict(
        dish_id=39,
        serving_count=30,
        summary=(
            "Egg filling (boiled, scrambled, or fried) in sliced bread. "
            "One sandwich per person using 1–2 eggs per sandwich."
        ),
        ingredients_json=[
            {"name": "Eggs",                "qty": "35–40","unit": "pcs",   "note": "boiled or scrambled"},
            {"name": "Bread (sliced loaves)","qty": "4–5", "unit": "loaves","note": ""},
            {"name": "Mayonnaise",          "qty": "400",  "unit": "g",     "note": ""},
            {"name": "Butter",              "qty": "200",  "unit": "g",     "note": ""},
            {"name": "Lettuce",             "qty": "1",    "unit": "head",  "note": ""},
            {"name": "Tomatoes",            "qty": "400",  "unit": "g",     "note": "sliced"},
            {"name": "Black pepper",        "qty": "2",    "unit": "tsp",   "note": ""},
            {"name": "Salt",                "qty": "to taste","unit": "",   "note": ""},
            {"name": "Chilli flakes",       "qty": "1",    "unit": "tsp",   "note": "optional"},
        ],
        tips_json=[
            "For boiled egg filling: chop eggs roughly, mix with mayo and seasoning while warm.",
            "For scrambled: cook slightly underdone — carry-over heat finishes them.",
            "Spread butter on both inner sides to waterproof the bread from wet filling.",
            "Add a thin layer of chilli sauce or mustard for a flavour contrast.",
        ],
    ),

    # ── id:40 Egg Lakhnawi ───────────────────────────────────────────────────
    dict(
        dish_id=40,
        serving_count=30,
        summary=(
            "Lucknow-style spiced egg curry with aromatic whole spices and a "
            "slow-cooked onion-yogurt gravy. 2 eggs per person."
        ),
        ingredients_json=[
            {"name": "Eggs",              "qty": "60–65",   "unit": "pcs",    "note": "hard-boiled"},
            {"name": "Onions",            "qty": "2",       "unit": "kg",     "note": "fried deep golden"},
            {"name": "Yogurt",            "qty": "500",     "unit": "g",      "note": "whisked"},
            {"name": "Ginger-garlic paste","qty": "150",    "unit": "g",      "note": ""},
            {"name": "Whole spices",      "qty": "1",       "unit": "set",    "note": "bay leaf, cloves, cardamom, cinnamon"},
            {"name": "Kashmiri red chilli powder","qty": "3","unit": "tbsp",  "note": "for deep colour"},
            {"name": "Coriander powder",  "qty": "2",       "unit": "tbsp",   "note": ""},
            {"name": "Garam masala",      "qty": "2",       "unit": "tbsp",   "note": ""},
            {"name": "Oil / Ghee",        "qty": "250",     "unit": "ml",     "note": ""},
            {"name": "Kewra / rose water","qty": "1",       "unit": "tsp",    "note": "finishing aroma"},
            {"name": "Salt",              "qty": "to taste","unit": "",       "note": ""},
            {"name": "Coriander leaves",  "qty": "1",       "unit": "bunch",  "note": "garnish"},
        ],
        tips_json=[
            "Score hard-boiled eggs with a fork before adding to gravy — spice penetrates better.",
            "Lightly fry scored eggs in turmeric before adding to curry.",
            "Deep golden onions are non-negotiable for Lakhnawi flavour depth.",
            "Finish with kewra water off the heat — do not cook after adding it.",
        ],
    ),

    # ── id:42 Garlic Bhurji ──────────────────────────────────────────────────
    dict(
        dish_id=42,
        serving_count=30,
        summary=(
            "Intensely garlicky egg bhurji — bold and aromatic. "
            "Same base as regular bhurji but garlic is doubled and roasted first."
        ),
        ingredients_json=[
            {"name": "Eggs",              "qty": "60–90",   "unit": "pcs",    "note": "2–3 per person"},
            {"name": "Garlic",            "qty": "250",     "unit": "g",      "note": "sliced thin — more than standard bhurji"},
            {"name": "Onions",            "qty": "1.5",     "unit": "kg",     "note": "finely chopped"},
            {"name": "Tomatoes",          "qty": "1",       "unit": "kg",     "note": "chopped"},
            {"name": "Butter",            "qty": "250",     "unit": "g",      "note": "butter base gives better garlic flavour than oil"},
            {"name": "Green chillies",    "qty": "10–15",   "unit": "pcs",    "note": ""},
            {"name": "Red chilli powder", "qty": "2",       "unit": "tbsp",   "note": ""},
            {"name": "Turmeric",          "qty": "1",       "unit": "tsp",    "note": ""},
            {"name": "Garam masala",      "qty": "1.5",     "unit": "tbsp",   "note": ""},
            {"name": "Salt",              "qty": "to taste","unit": "",       "note": ""},
            {"name": "Coriander leaves",  "qty": "2",       "unit": "bunches","note": "garnish"},
        ],
        tips_json=[
            "Fry garlic slices slowly in butter until they turn light golden — this is the flavour base.",
            "Do not burn the garlic; remove from heat briefly if colour is moving too fast.",
            "Add onions only after garlic is golden; this layering gives depth.",
            "Finish with a generous knob of butter just before plating.",
        ],
    ),

    # ── id:43 Sev Tarkari ────────────────────────────────────────────────────
    dict(
        dish_id=43,
        serving_count=30,
        summary=(
            "Crispy sev cooked in a spiced onion-tomato-potato gravy — "
            "a Gujarati-style sabzi. Sev softens in the gravy; balance is key."
        ),
        ingredients_json=[
            {"name": "Sev (medium thick)","qty": "600",     "unit": "g",     "note": "added last"},
            {"name": "Potatoes",          "qty": "1.5",     "unit": "kg",    "note": "diced, par-boiled"},
            {"name": "Onions",            "qty": "1.5",     "unit": "kg",    "note": "chopped"},
            {"name": "Tomatoes",          "qty": "1.5",     "unit": "kg",    "note": "chopped"},
            {"name": "Oil",               "qty": "250",     "unit": "ml",    "note": ""},
            {"name": "Mustard seeds",     "qty": "2",       "unit": "tbsp",  "note": ""},
            {"name": "Turmeric",          "qty": "1.5",     "unit": "tsp",   "note": ""},
            {"name": "Red chilli powder", "qty": "2",       "unit": "tbsp",  "note": ""},
            {"name": "Coriander powder",  "qty": "2",       "unit": "tbsp",  "note": ""},
            {"name": "Garam masala",      "qty": "1",       "unit": "tbsp",  "note": ""},
            {"name": "Green chillies",    "qty": "10",      "unit": "pcs",   "note": ""},
            {"name": "Salt",              "qty": "to taste","unit": "",      "note": ""},
            {"name": "Coriander leaves",  "qty": "1",       "unit": "bunch", "note": "garnish"},
        ],
        tips_json=[
            "Add sev only when gravy is thick and almost ready — it absorbs liquid fast.",
            "For bulk cooking, add sev in stages as you serve so it does not go completely soft.",
            "Potatoes should be par-boiled before adding to gravy to cut cooking time.",
            "Keep some sev on the side as a crunchy topping when serving.",
        ],
    ),

    # ── id:44 Peri Peri Half Fry ─────────────────────────────────────────────
    dict(
        dish_id=44,
        serving_count=30,
        summary=(
            "Same preparation as Half Fry Peri Peri (id 35). "
            "Sunny-side-up eggs with peri peri seasoning."
        ),
        ingredients_json=[
            {"name": "Eggs",             "qty": "30–60",   "unit": "pcs",   "note": "1–2 per person"},
            {"name": "Butter / Oil",     "qty": "200",     "unit": "ml",    "note": ""},
            {"name": "Peri peri seasoning","qty": "80–100","unit": "g",     "note": ""},
            {"name": "Garlic powder",    "qty": "2",       "unit": "tsp",   "note": ""},
            {"name": "Smoked paprika",   "qty": "2",       "unit": "tsp",   "note": ""},
            {"name": "Salt",             "qty": "to taste","unit": "",      "note": ""},
            {"name": "Lemon wedges",     "qty": "5",       "unit": "pcs",   "note": "for serving"},
        ],
        tips_json=[
            "Heat pan well before adding butter for clean, non-sticky whites.",
            "Cover with a lid for 1 minute to set the white without flipping.",
            "Sprinkle peri peri while egg is still hot so seasoning sticks.",
            "Note: super admin may wish to merge this with id 35 (Half Fry Peri Peri) as they are the same dish.",
        ],
    ),

    # ── id:45 Chi. Seekh White Sauce Tarkari ─────────────────────────────────
    dict(
        dish_id=45,
        serving_count=30,
        summary=(
            "Chicken seekh kebabs served in or alongside a creamy white sauce gravy. "
            "Allow 2–3 seekh pieces per person plus 150 ml sauce per person."
        ),
        ingredients_json=[
            {"name": "Minced chicken",       "qty": "4",    "unit": "kg",    "note": "double minced for seekh"},
            {"name": "Butter",               "qty": "350",  "unit": "g",     "note": "for sauce base"},
            {"name": "All-purpose flour",    "qty": "200",  "unit": "g",     "note": "for béchamel roux"},
            {"name": "Milk",                 "qty": "1.5",  "unit": "ltr",   "note": "for white sauce"},
            {"name": "Fresh cream",          "qty": "200",  "unit": "ml",    "note": ""},
            {"name": "Onions",               "qty": "1",    "unit": "kg",    "note": "for seekh mix (squeezed dry)"},
            {"name": "Garlic",               "qty": "150",  "unit": "g",     "note": "for both seekh and sauce"},
            {"name": "Green chillies",       "qty": "10",   "unit": "pcs",   "note": "for seekh mix"},
            {"name": "Black pepper",         "qty": "2",    "unit": "tbsp",  "note": "for sauce"},
            {"name": "Garam masala",         "qty": "2",    "unit": "tbsp",  "note": "for seekh mix"},
            {"name": "Fresh coriander",      "qty": "2",    "unit": "bunches","note": ""},
            {"name": "Cheese",               "qty": "200",  "unit": "g",     "note": "grated, optional topping"},
            {"name": "Salt",                 "qty": "to taste","unit": "",   "note": ""},
        ],
        tips_json=[
            "Make the béchamel roux on low heat; stir constantly to avoid lumps.",
            "Grill or pan-fry seekh separately until cooked, then cut into rounds before plating with sauce.",
            "White sauce thickens quickly on standing — keep it slightly loose; it tightens on serving.",
            "Finish the sauce with cracked black pepper and cream just before service.",
            "Garnish with grated cheese and coriander for a visually appealing plate.",
        ],
    ),

]  # end ESTIMATES


def upgrade():
    op.bulk_insert(dish_estimate_table, [
        {**row, "created_at": NOW, "updated_at": NOW}
        for row in ESTIMATES
    ])


def downgrade():
    dish_ids = [row["dish_id"] for row in ESTIMATES]
    ids_literal = ", ".join(str(i) for i in dish_ids)
    op.execute(
        sa.text(f"DELETE FROM dish_estimate WHERE dish_id IN ({ids_literal})")
    )
