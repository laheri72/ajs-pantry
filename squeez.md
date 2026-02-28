✦ This is a great architectural pivot. You are moving from a simple "calendar of records" to a Knowledge-Driven Kitchen. By shifting the focus
  to a Global Dish Library, we can link feedback, suggestions, and rotating team assignments into a single "Smart Squeeze" for the Pantry Head.

  Here is the strategic plan to evolve the system without breaking existing multi-tenancy or core table structures:


  1. The "Global Dish Library" Refactor
  Currently, Menu is just a record on a calendar. To make it "expert level," we need to treat the Dish as the central entity.
   * The Change: We ensure every Menu record is linked to a Dish ID.
   * Insight: When a PH schedules "Poha" (Dish ID: 5), the system can instantly pull up:
       * Historical Rating: "Avg 4.8 stars on this floor."
       * Suggestions: "Last time, 3 people suggested adding more peanuts."
       * Last Served: "Team B cooked this 3 weeks ago."


  2. The "One-Row" Breakfast Model
  Since you only do Breakfast, we can "Squeeze" the UI.
   * The Structure: Instead of multiple rows per day, a single Menu entry for a date will support a Primary Dish and an optional Side Dish.
   * Implementation: We can add a side_dish_id to the Menu table. This allows the PH to schedule "Idli (Main) + Chutney (Side)" in one click,
     assigned to one Team.


  3. The "Smart Rotation" Engine (Team Turns)
  To eliminate "Who's turn is it?" fatigue:
   * The Logic: The "Schedule" modal will have a "Suggest Next Team" button.
   * How it works: It queries the Menu table to find the most recent date each team was assigned. The team with the oldest "Last Assignment
     Date" is suggested next.
   * Special Buffer: If a "Special Dish" is selected, the PH can toggle a "Buffer Day" switch, which lets them assign individuals instead of
     moving the Team Rotation forward.


  4. Linking Suggestions to Dish "Tags"
  Instead of vague text suggestions, we will link them to the Dish Library.
   * The Integration: When a user creates a suggestion, they can pick a "Dish Tag."
   * The Benefit: When the PH is scheduling the menu for next Tuesday and picks "Upma," a small alert icon appears: "3 New Suggestions for this
     dish." This turns the menu creation from a chore into a performance review.


  5. Strategy: The "Weekly Projection" Flow
  Instead of a complex template system, we implement a "Batch Rotation" tool:
   1. PH selects a start date (e.g., next Monday).
   2. PH selects 7 Main Dishes.
   3. The system Auto-Projects the next 7 teams from the People module.
   4. PH reviews the 7-day list, tweaks any "Individual Buffer" days, and clicks "Project Week."

  ---

  The Proposed Data Evolution (Mental Map)



  ┌─────────────────┬───────────────────┬────────────────────────────────────────────┐
  │ Feature         │ Current State     │ Expert State (The Squeeze)                 │
  ├─────────────────┼───────────────────┼────────────────────────────────────────────┤
  │ Record      │ 1 Row = 1 Dish    │ 1 Row = 1 Complete Breakfast (Main + Side) │
  │ Assignment  │ Manual Selection  │ Auto-Rotation (Next-in-line Team)          │
  │ Suggestions │ Generic Inbox     │ Contextual (Linked to Dish)                │
  │ Feedback    │ Buried in Records │ Aggregated per Dish (Wall of Fame)         │
  └─────────────────┴───────────────────┴────────────────────────────────────────────┘

  Next Step Recommendation:
  I suggest we start by modifying the `Menu` model to support side_dish_id and creating a simple Rotation Helper that tells the PH which team is
  next.


  Would you like me to start by drafting the database migration for these new fields, or should we focus on the "Team Rotation" logic first?

  ✦ This is a sophisticated "Squeeze." We are moving from a transactional system (recording what happened) to an intelligence system (planning
  based on patterns).

  Here is the complete logic and the migration plan to achieve "Expert Level" menu management.

  ---


  1. Architectural Logic: The "Kitchen Brain"

  We will shift the system into four pillars:


  A. The Master Dish Registry (The "Tags")
  Instead of typing names, we use a central Dish library.
   * Global vs. Local: A dish can be "Global" (available to all tenants, e.g., "Poha", "Idli") or "Tenant-Specific".
   * Categories: Every dish is tagged as Main, Side, or Both.
   * Intelligence: Each dish record aggregates its average rating from all historical Feedback across the floor.


  B. The Unified Breakfast Record (1 Row per Day)
  We simplify the Menu table to represent a single "Meal Event":
   * Main & Side: One record now holds dish_id (Main) AND side_dish_id (Side).
   * The Buffer Toggle: A boolean is_buffer. If True, it indicates a "Special Day" (Individual assignment). If False, it’s a "Standard Day" that
     counts toward the Team Rotation.


  C. The Auto-Rotation Engine (Who's Next?)
  The system calculates the "Next Team" using this deterministic logic:
   1. Get all active Teams for the floor.
   2. Look at the Menu history for non-buffer days only.
   3. Identify the last_served_date for each team.
   4. Rank: The team with the oldest last_served_date is the one that is currently "Next."
   5. Conflict Check: The engine checks if any member of the "Next Team" has an approved absence (from the Requests table) for that date and
      warns the PH.


  D. The Suggestion-Dish Loop
   * Contextual Suggestions: When a user makes a suggestion, they must select a Dish tag.
   * The Planning Alert: When a PH selects "Upma" for next Wednesday, the UI immediately shows: "3 users suggested changing the oil brand for
     Upma."

  ---


  2. The Expert Workflow (The Squeeze)


   1. Weekly Projection: The PH opens the "Weekly Planner."
   2. Auto-Populate: The system looks at the next 7 days. It automatically assigns the "Next" team in the rotation for each day (skipping Sunday
      if needed).
   3. Dish Selection: The PH picks the Main/Side dishes for the week.
   4. Buffer Switch: If the PH changes a day from "Team" to "Individual," the system automatically "pushes" the rotation for the subsequent days
      so no team loses their turn.
   5. One-Click Commit: All 7 meals are created at once.

  ---

  3. Migration SQL (PostgreSQL / Supabase)

  This SQL evolves your schema to support the logic above. Run this in your Supabase SQL Editor.




    1 -- 1. Create the Master Dishes Table
    2 CREATE TABLE dishes (
    3     id SERIAL PRIMARY KEY,
    4     name VARCHAR(100) NOT NULL,
    5     category VARCHAR(20) DEFAULT 'main', -- 'main', 'side', 'both'
    6     description TEXT,
    7     tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE, -- NULL for "Global" dishes
    8     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    9 );
   10
   11 -- 2. Add Intelligence Fields to Menu Table
   12 ALTER TABLE menu
   13     ADD COLUMN dish_id INTEGER REFERENCES dishes(id),
   14     ADD COLUMN side_dish_id INTEGER REFERENCES dishes(id),
   15     ADD COLUMN is_buffer BOOLEAN DEFAULT FALSE,
   16     ADD COLUMN dish_type VARCHAR(20) DEFAULT 'main'; -- For backward compatibility
   17
   18 -- 3. Link Suggestions to the Dish Registry
   19 ALTER TABLE suggestions
   20     ADD COLUMN dish_id INTEGER REFERENCES dishes(id);
   21
   22 -- 4. Initial Global Dish Seeding (The "Tags")
   23 INSERT INTO dishes (name, category) VALUES
   24 ('Poha', 'main'),
   25 ('Idli Sambar', 'main'),
   26 ('Upma', 'main'),
   27 ('Aloo Paratha', 'main'),
   28 ('Chutney', 'side'),
   29 ('Sambar', 'side'),
   30 ('Boiled Egg', 'side'),
   31 ('Omelette', 'side');
   32
   33 -- 5. Data Migration (Optional: Link existing menu titles to new dish entries)
   34 -- This logic assumes we try to match names.
   35 -- For new installs, this isn't needed. For live apps, we link them:
   36 INSERT INTO dishes (name, tenant_id)
   37 SELECT DISTINCT title, tenant_id FROM menu
   38 WHERE title IS NOT NULL
   39 ON CONFLICT DO NOTHING;
   40
   41 -- 6. Performance Index for the Rotation Engine
   42 CREATE INDEX idx_menu_rotation ON menu (floor, date, is_buffer, assigned_team_id);


  Next Steps:
   1. Backend Implementation: I will create the get_next_team helper function in blueprints/pantry/routes.py.
   2. UI Upgrade: I will refactor the addMenuModal in menus.html to handle the Main/Side/Buffer logic in one clean view.


  Shall I proceed with implementing the "Next Team" calculation logic in the backend?