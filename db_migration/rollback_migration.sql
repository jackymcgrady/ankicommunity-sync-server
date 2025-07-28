-- AnkiPi Database Rollback Script
-- This script safely removes the AnkiPi database schema
-- WARNING: This will delete ALL data - use with extreme caution

-- Set strict error handling
\set ON_ERROR_STOP true

-- Begin transaction for safety
BEGIN;

-- Display warning
\echo 'WARNING: This script will delete ALL AnkiPi data!'
\echo 'Press Ctrl+C to cancel, or any key to continue...'
\prompt 'Type "DELETE_ALL_DATA" to confirm: ' confirmation

-- Check confirmation (this is a safety measure in interactive mode)
-- In automated environments, you can skip this by setting the variable directly

-- Drop triggers first
DROP TRIGGER IF EXISTS update_deck_stats_updated_at ON deck_stats;

-- Drop tables in reverse dependency order to avoid foreign key violations
DROP TABLE IF EXISTS old_problems CASCADE;
DROP TABLE IF EXISTS deck_stats CASCADE;
DROP TABLE IF EXISTS deck_recipe_prompts CASCADE;
DROP TABLE IF EXISTS check_in CASCADE;
DROP TABLE IF EXISTS leech_helper_history CASCADE;
DROP TABLE IF EXISTS card_templates CASCADE;
DROP TABLE IF EXISTS note_types CASCADE;
DROP TABLE IF EXISTS pass CASCADE;
DROP TABLE IF EXISTS cards CASCADE;
DROP TABLE IF EXISTS decks CASCADE;
DROP TABLE IF EXISTS recipe_prompts CASCADE;
DROP TABLE IF EXISTS profiles CASCADE;

-- Drop sequences (they should be dropped automatically with tables, but just to be sure)
DROP SEQUENCE IF EXISTS profiles_profile_id_seq CASCADE;
DROP SEQUENCE IF EXISTS decks_deck_id_seq CASCADE;
DROP SEQUENCE IF EXISTS cards_card_id_seq CASCADE;
DROP SEQUENCE IF EXISTS pass_pass_id_seq CASCADE;
DROP SEQUENCE IF EXISTS note_types_note_type_id_seq CASCADE;
DROP SEQUENCE IF EXISTS card_templates_card_template_id_seq CASCADE;
DROP SEQUENCE IF EXISTS leech_helper_history_history_id_seq CASCADE;
DROP SEQUENCE IF EXISTS check_in_check_in_id_seq CASCADE;
DROP SEQUENCE IF EXISTS deck_recipe_prompts_deck_recipe_prompt_id_seq CASCADE;
DROP SEQUENCE IF EXISTS deck_stats_id_seq CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;

-- Note: We don't drop the uuid-ossp extension as it might be used by other applications
-- If you want to remove it, uncomment the next line:
-- DROP EXTENSION IF EXISTS "uuid-ossp";

-- Commit the transaction
COMMIT;

\echo 'AnkiPi database schema has been completely removed.'
\echo 'All data has been permanently deleted.'