-- AnkiPi Production Database Schema Migration Script
-- This script creates the complete database schema for AnkiPi production deployment
-- Based on the actual production schema from ankipi_backup.sql

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone for consistent timestamps
SET timezone = 'UTC';

-- Create function for updating timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create tables in dependency order

-- 1. Profiles table (base table, no dependencies)
CREATE TABLE IF NOT EXISTS profiles (
    profile_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    age_group TEXT,
    personalization TEXT,
    leech_threshold INTEGER,
    timezone TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    anki2_filename TEXT,
    uuid UUID DEFAULT uuid_generate_v4(),
    is_active BOOLEAN
);

-- 2. Recipe prompts table (independent)
CREATE TABLE IF NOT EXISTS recipe_prompts (
    recipe_prompt_id SERIAL,
    name TEXT NOT NULL,
    prompt_text TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    tags TEXT
);

-- 3. Decks table (depends on profiles)
CREATE TABLE IF NOT EXISTS decks (
    deck_id SERIAL PRIMARY KEY,
    mother_deck INTEGER NOT NULL,
    profile_id INTEGER NOT NULL REFERENCES profiles(profile_id),
    name TEXT NOT NULL,
    context TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_trophy_date TIMESTAMP WITH TIME ZONE,
    trophy_enabled BOOLEAN DEFAULT FALSE,
    anki_deck_id BIGINT,
    syllabus TEXT,
    first_review_ts TIMESTAMP WITH TIME ZONE,
    graduated_card_count INTEGER,
    total_time_spent_ms BIGINT,
    CONSTRAINT decks_profile_id_name_key UNIQUE (profile_id, name)
);

-- 4. Cards table (depends on decks)
CREATE TABLE IF NOT EXISTS cards (
    card_id BIGSERIAL,
    deck_id BIGINT NOT NULL REFERENCES decks(deck_id),
    note_id BIGINT,
    anki_note_id BIGINT NOT NULL,
    anki_model_id BIGINT,
    card_ordinal INTEGER,
    front_content TEXT,
    back_content TEXT,
    target_problem TEXT,
    tags TEXT,
    due_number BIGINT NOT NULL,
    is_leech BOOLEAN,
    lapse INTEGER,
    queue INTEGER,
    graduation_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_syllabus_run_ts TIMESTAMP WITH TIME ZONE,
    anki_card_id BIGINT,
    last_not_again_ts TIMESTAMP WITH TIME ZONE,
    ever_not_again BOOLEAN DEFAULT FALSE NOT NULL,
    CONSTRAINT unique_note_per_deck UNIQUE (deck_id, anki_note_id)
);

-- 5. Pass table (depends on profiles, decks)
CREATE TABLE IF NOT EXISTS pass (
    pass_id BIGSERIAL,
    profile_id BIGINT NOT NULL REFERENCES profiles(profile_id),
    deck_id BIGINT NOT NULL REFERENCES decks(deck_id),
    instruction_type TEXT NOT NULL,
    instruction_data JSONB NOT NULL,
    is_completed BOOLEAN,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    target_problem TEXT,
    is_leech_helper BOOLEAN DEFAULT FALSE NOT NULL
);

-- 6. Note types table (depends on profiles)
CREATE TABLE IF NOT EXISTS note_types (
    note_type_id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES profiles(profile_id) ON DELETE CASCADE,
    anki_model_id BIGINT NOT NULL,
    name TEXT NOT NULL,
    fields TEXT,
    last_sync_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ankipi_managed INTEGER DEFAULT 0 NOT NULL,
    ankipi_key TEXT,
    CONSTRAINT note_types_profile_id_anki_model_id_key UNIQUE (profile_id, anki_model_id)
);

-- 7. Card templates table (depends on note_types)
CREATE TABLE IF NOT EXISTS card_templates (
    card_template_id SERIAL PRIMARY KEY,
    note_type_id INTEGER NOT NULL REFERENCES note_types(note_type_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    front_template TEXT,
    back_template TEXT,
    last_sync_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    css TEXT,
    anki_template_id TEXT,
    CONSTRAINT card_templates_note_type_id_ordinal_key UNIQUE (note_type_id, ordinal)
);

-- 8. Leech helper history table (depends on cards and pass)
CREATE TABLE IF NOT EXISTS leech_helper_history (
    history_id SERIAL,
    card_id INTEGER NOT NULL REFERENCES cards(card_id),
    helper_pass_id INTEGER NOT NULL REFERENCES pass(pass_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 9. Check-in table (independent)
CREATE TABLE IF NOT EXISTS check_in (
    check_in_id SERIAL PRIMARY KEY,
    module_name TEXT NOT NULL,
    check_in_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_in_module_name_check CHECK (module_name = ANY (ARRAY['chef'::TEXT, 'waiter'::TEXT]))
);

-- 10. Deck recipe prompts association table (depends on decks and recipe_prompts)
CREATE TABLE IF NOT EXISTS deck_recipe_prompts (
    deck_recipe_prompt_id SERIAL PRIMARY KEY,
    deck_id INTEGER NOT NULL REFERENCES decks(deck_id),
    recipe_prompt_id INTEGER NOT NULL REFERENCES recipe_prompts(recipe_prompt_id),
    is_selected BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 11. Deck stats table (depends on decks and profiles)
CREATE TABLE IF NOT EXISTS deck_stats (
    id SERIAL PRIMARY KEY,
    deck_id INTEGER NOT NULL REFERENCES decks(deck_id),
    profile_id INTEGER NOT NULL REFERENCES profiles(profile_id),
    stat_date DATE NOT NULL,
    reviews_count INTEGER DEFAULT 0,
    time_spent_total_minutes DOUBLE PRECISION DEFAULT 0.0,
    learning_cards_count_old INTEGER DEFAULT 0,
    mature_cards_count_old INTEGER DEFAULT 0,
    new_cards_seen INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    young_cards_count INTEGER DEFAULT 0,
    mature_cards_count_new INTEGER DEFAULT 0,
    learning_cards_count INTEGER DEFAULT 0,
    mature_cards_count INTEGER DEFAULT 0,
    CONSTRAINT unique_deck_stats_per_day UNIQUE (deck_id, stat_date)
);

-- 12. Old problems table (mentioned in README)
CREATE TABLE IF NOT EXISTS old_problems (
    id SERIAL,
    target_problem_uuid UUID NOT NULL,
    old_problem_front TEXT NOT NULL,
    old_problem_back TEXT NOT NULL,
    saved_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance (based on backup file)
CREATE INDEX IF NOT EXISTS idx_profiles_uuid ON profiles(uuid);
CREATE INDEX IF NOT EXISTS idx_pass_leech_helper_pending ON pass(is_completed, instruction_type, created_at);
CREATE INDEX IF NOT EXISTS idx_old_problems_uuid ON old_problems(target_problem_uuid);
CREATE INDEX IF NOT EXISTS idx_decks_graduated_count ON decks(graduated_card_count);
CREATE INDEX IF NOT EXISTS idx_deck_stats_profile_date ON deck_stats(profile_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_deck_stats_deck_date ON deck_stats(deck_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_cards_last_not_again ON cards(last_not_again_ts);

-- Create trigger for deck_stats updated_at
CREATE TRIGGER update_deck_stats_updated_at
    BEFORE UPDATE ON deck_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Set proper ownership (commented out - adjust based on your database user)
-- ALTER TABLE profiles OWNER TO ankipi;
-- ALTER TABLE decks OWNER TO ankipi;
-- ALTER TABLE cards OWNER TO ankipi;
-- ALTER TABLE pass OWNER TO ankipi;
-- ALTER TABLE note_types OWNER TO ankipi;
-- ALTER TABLE card_templates OWNER TO ankipi;
-- ALTER TABLE leech_helper_history OWNER TO ankipi;
-- ALTER TABLE check_in OWNER TO ankipi;
-- ALTER TABLE deck_recipe_prompts OWNER TO ankipi;
-- ALTER TABLE deck_stats OWNER TO ankipi;
-- ALTER TABLE recipe_prompts OWNER TO ankipi;
-- ALTER TABLE old_problems OWNER TO ankipi;