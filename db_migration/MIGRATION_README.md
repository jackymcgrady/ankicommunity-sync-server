# AnkiPi Database Migration Guide

This guide provides instructions for migrating the AnkiPi PostgreSQL schema to your production server.

## Overview

AnkiPi uses PostgreSQL as its central database with the following key components:
- **12 core tables** storing profiles, decks, cards, passes, and analytics
- **JSONB support** for flexible instruction data
- **UUID extension** for unique identifiers
- **Timezone-aware timestamps** for proper temporal data handling

## Prerequisites

- PostgreSQL 12+ with `uuid-ossp` extension support
- Database user with `CREATE`, `ALTER`, and `INSERT` privileges
- Network connectivity to the target database

## Environment Variables

Set the following environment variables before running the migration:

```bash
export POSTGRES_HOST="your-production-host"
export POSTGRES_PORT="5432"
export POSTGRES_DB="ankipi"
export POSTGRES_USER="ankipi"
export POSTGRES_PASSWORD="your-secure-password"
```

## Migration Steps

### 1. Pre-Migration Checks

Verify database connectivity and permissions:

```bash
# Test connection
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT version();"

# Check for existing tables (should be empty for new deployment)
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"
```

### 2. Run Schema Creation

Execute the schema creation script:

```bash
# Apply the schema
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -f create_schema.sql

# Verify table creation
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"
```

### 3. Verify Migration

Check that all tables and indexes were created successfully:

```bash
# Count tables (should be 12)
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"

# Verify key indexes exist
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT indexname FROM pg_indexes WHERE tablename IN ('profiles', 'cards', 'pass', 'deck_stats');"

# Check extensions
psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT * FROM pg_extension WHERE extname = 'uuid-ossp';"
```

## Table Descriptions

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `profiles` | User profiles and settings | `profile_id`, `uuid`, `name`, `leech_threshold` |
| `decks` | Anki deck hierarchy and metadata | `deck_id`, `profile_id`, `name`, `anki_deck_id` |
| `cards` | Cloud copy of Anki cards | `card_id`, `deck_id`, `anki_note_id`, `is_leech` |
| `pass` | Instruction queue for Waiter | `pass_id`, `instruction_type`, `instruction_data` |
| `note_types` | Anki note type definitions | `note_type_id`, `profile_id`, `anki_model_id` |
| `card_templates` | Card template definitions | `card_template_id`, `note_type_id`, `ordinal` |
| `leech_helper_history` | Leech helper tracking | `history_id`, `card_id`, `helper_pass_id` |
| `check_in` | Module heartbeat logs | `check_in_id`, `module_name`, `check_in_time` |
| `deck_recipe_prompts` | Deck-to-prompt associations | `deck_id`, `recipe_prompt_id`, `is_selected` |
| `deck_stats` | Daily deck statistics | `id`, `deck_id`, `stat_date`, `reviews_count` |
| `recipe_prompts` | AI prompt templates | `recipe_prompt_id`, `name`, `prompt_text` |
| `old_problems` | Archive of modified cards | `id`, `target_problem_uuid`, `old_problem_front` |

## Performance Indexes

The migration creates the following performance indexes:

- `idx_profiles_uuid` - Fast profile lookups by UUID
- `idx_pass_leech_helper_pending` - Efficient pass queue processing
- `idx_deck_stats_profile_date` - Analytics queries by profile and date
- `idx_deck_stats_deck_date` - Analytics queries by deck and date
- `idx_cards_last_not_again` - Card state tracking
- `idx_old_problems_uuid` - Archive lookups by UUID

## Post-Migration Tasks

### 1. Create Initial Data (Optional)

If migrating from an existing system, you may want to create initial recipe prompts:

```sql
-- Example initial recipe prompts
INSERT INTO recipe_prompts (name, prompt_text, description) VALUES
('leech_helper', 'Create a helpful practice card for this leech...', 'Generates helper cards for difficult items'),
('trophy_giver', 'Generate a congratulatory trophy card...', 'Creates celebration cards for milestones'),
('syllabus_helper', 'Rewrite this problem with variation...', 'Diversifies syllabus-based problems');
```

### 2. Set Up User Permissions

Adjust database permissions as needed:

```sql
-- Grant appropriate permissions to application user
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ankipi;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ankipi;
```

### 3. Configure Connection Pooling

For production deployments, consider using connection pooling:
- **PgBouncer** for connection pooling
- **AWS RDS Proxy** for managed connection pooling on AWS
- **Connection pool settings** in your application (current: pool_size=5, max_overflow=10)

## Rollback Procedure

If rollback is needed, drop all tables in reverse dependency order:

```sql
-- WARNING: This will delete all data
DROP TABLE IF EXISTS old_problems;
DROP TABLE IF EXISTS deck_stats;
DROP TABLE IF EXISTS deck_recipe_prompts;
DROP TABLE IF EXISTS check_in;
DROP TABLE IF EXISTS leech_helper_history;
DROP TABLE IF EXISTS card_templates;
DROP TABLE IF EXISTS note_types;
DROP TABLE IF EXISTS pass;
DROP TABLE IF EXISTS cards;
DROP TABLE IF EXISTS decks;
DROP TABLE IF EXISTS recipe_prompts;
DROP TABLE IF EXISTS profiles;
DROP FUNCTION IF EXISTS update_updated_at_column();
```

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure the database user has CREATE privileges
2. **Extension Missing**: Install `uuid-ossp` extension: `CREATE EXTENSION "uuid-ossp";`
3. **Connection Failed**: Verify network connectivity and firewall rules
4. **Constraint Violations**: Check for existing data that conflicts with new constraints

### Monitoring

After migration, monitor these key metrics:
- Table sizes: `SELECT schemaname,tablename,pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables WHERE schemaname = 'public';`
- Index usage: Query `pg_stat_user_indexes` for index efficiency
- Connection counts: Monitor active connections via `pg_stat_activity`

## Support

For migration issues:
1. Check the `logs/log.txt` file for detailed error messages
2. Verify all environment variables are correctly set
3. Ensure PostgreSQL version compatibility (12+ required)
4. Contact the development team with specific error messages and migration context

---

**Migration Script**: `create_schema.sql`  
**Compatible PostgreSQL Versions**: 12+  
**Estimated Migration Time**: < 5 minutes for schema-only migration  
**Dependencies**: `uuid-ossp` extension