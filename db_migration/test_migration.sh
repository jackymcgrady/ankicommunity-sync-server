#!/bin/bash

# Test script for AnkiPi database migration
# This script tests the migration using a local PostgreSQL instance

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    local status=$1
    local message=$2
    case $status in
        "success") echo -e "${GREEN}✓${NC} $message" ;;
        "error") echo -e "${RED}✗${NC} $message" ;;
        "warning") echo -e "${YELLOW}⚠${NC} $message" ;;
        "info") echo -e "${BLUE}ℹ${NC} $message" ;;
    esac
}

# Test configuration
TEST_DB="ankipi_migration_test"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

print_status "info" "Starting AnkiPi migration test"

# Check if PostgreSQL is running locally
if ! pg_isready -h localhost > /dev/null 2>&1; then
    print_status "error" "PostgreSQL is not running locally"
    print_status "info" "Start PostgreSQL service first: brew services start postgresql"
    exit 1
fi

print_status "success" "PostgreSQL is running"

# Set test environment variables
export POSTGRES_HOST="localhost"
export POSTGRES_PORT="5432"
export POSTGRES_DB="$TEST_DB"
export POSTGRES_USER="${USER}"
export POSTGRES_PASSWORD=""

print_status "info" "Creating test database: $TEST_DB"

# Create test database
createdb "$TEST_DB" 2>/dev/null || {
    print_status "warning" "Database $TEST_DB already exists, dropping and recreating..."
    dropdb "$TEST_DB" 2>/dev/null || true
    createdb "$TEST_DB"
}

print_status "success" "Test database created"

# Test 1: Dry run
print_status "info" "Test 1: Running dry run migration"
if "$SCRIPT_DIR/migrate.sh" --dry-run; then
    print_status "success" "Dry run completed successfully"
else
    print_status "error" "Dry run failed"
    exit 1
fi

# Test 2: Full migration
print_status "info" "Test 2: Running full migration"
if "$SCRIPT_DIR/migrate.sh" --force --verify; then
    print_status "success" "Full migration completed successfully"
else
    print_status "error" "Full migration failed"
    exit 1
fi

# Test 3: Re-run migration (should be idempotent)
print_status "info" "Test 3: Testing migration idempotency"
if "$SCRIPT_DIR/migrate.sh" --force --skip-verification; then
    print_status "success" "Migration re-run completed successfully"
else
    print_status "error" "Migration re-run failed"
    exit 1
fi

# Test 4: Manual verification
print_status "info" "Test 4: Running manual verification"
if "$SCRIPT_DIR/verify_migration.sh"; then
    print_status "success" "Manual verification passed"
else
    print_status "error" "Manual verification failed"
    exit 1
fi

# Test 5: Basic data operations
print_status "info" "Test 5: Testing basic CRUD operations"

# Insert test data
psql -d "$TEST_DB" -c "
INSERT INTO profiles (name, personalization, leech_threshold) 
VALUES ('test_user', 'Test personalization', 8);
" > /dev/null

# Insert deck
psql -d "$TEST_DB" -c "
INSERT INTO decks (mother_deck, profile_id, name, context) 
VALUES (1, 1, 'Test Deck', 'Test context');
" > /dev/null

# Insert card
psql -d "$TEST_DB" -c "
INSERT INTO cards (deck_id, anki_note_id, front_content, back_content, due_number) 
VALUES (1, 12345, 'Test front', 'Test back', 1);
" > /dev/null

# Insert pass
psql -d "$TEST_DB" -c "
INSERT INTO pass (profile_id, deck_id, instruction_type, instruction_data) 
VALUES (1, 1, 'create', '{\"type\": \"test\"}');
" > /dev/null

# Verify data exists
local profile_count=$(psql -d "$TEST_DB" -t -c "SELECT COUNT(*) FROM profiles;" | tr -d ' ')
local deck_count=$(psql -d "$TEST_DB" -t -c "SELECT COUNT(*) FROM decks;" | tr -d ' ')
local card_count=$(psql -d "$TEST_DB" -t -c "SELECT COUNT(*) FROM cards;" | tr -d ' ')
local pass_count=$(psql -d "$TEST_DB" -t -c "SELECT COUNT(*) FROM pass;" | tr -d ' ')

if [[ $profile_count -eq 1 && $deck_count -eq 1 && $card_count -eq 1 && $pass_count -eq 1 ]]; then
    print_status "success" "Test data inserted successfully"
else
    print_status "error" "Test data insertion failed (profiles: $profile_count, decks: $deck_count, cards: $card_count, passes: $pass_count)"
    exit 1
fi

# Test 6: Foreign key constraints
print_status "info" "Test 6: Testing foreign key constraints"

# This should fail due to foreign key constraint
if psql -d "$TEST_DB" -c "INSERT INTO cards (deck_id, anki_note_id, due_number) VALUES (999, 54321, 1);" > /dev/null 2>&1; then
    print_status "error" "Foreign key constraint test failed - invalid deck_id was accepted"
    exit 1
else
    print_status "success" "Foreign key constraints working correctly"
fi

# Test 7: Unique constraints
print_status "info" "Test 7: Testing unique constraints"

# This should fail due to unique constraint
if psql -d "$TEST_DB" -c "INSERT INTO cards (deck_id, anki_note_id, due_number) VALUES (1, 12345, 2);" > /dev/null 2>&1; then
    print_status "error" "Unique constraint test failed - duplicate anki_note_id was accepted"
    exit 1
else
    print_status "success" "Unique constraints working correctly"
fi

# Test 8: JSON data
print_status "info" "Test 8: Testing JSONB functionality"

# Test complex JSON data
psql -d "$TEST_DB" -c "
UPDATE pass SET instruction_data = '{
    \"type\": \"leech_helper\",
    \"card_id\": 123,
    \"front\": \"What is the capital of France?\",
    \"back\": \"Paris\",
    \"metadata\": {
        \"difficulty\": \"easy\",
        \"tags\": [\"geography\", \"europe\"]
    }
}' WHERE pass_id = 1;
" > /dev/null

# Query JSON data
local json_result=$(psql -d "$TEST_DB" -t -c "SELECT instruction_data->>'type' FROM pass WHERE pass_id = 1;" | tr -d ' ')
if [[ "$json_result" == "leech_helper" ]]; then
    print_status "success" "JSONB functionality working correctly"
else
    print_status "error" "JSONB functionality failed"
    exit 1
fi

# Test 9: Rollback test (optional - creates a new test database)
print_status "info" "Test 9: Testing rollback functionality"

# Create a separate database for rollback test
TEST_ROLLBACK_DB="ankipi_rollback_test"
export POSTGRES_DB="$TEST_ROLLBACK_DB"

createdb "$TEST_ROLLBACK_DB" 2>/dev/null || {
    dropdb "$TEST_ROLLBACK_DB" 2>/dev/null || true
    createdb "$TEST_ROLLBACK_DB"
}

# Run migration
"$SCRIPT_DIR/migrate.sh" --force --skip-verification > /dev/null

# Insert some test data
psql -d "$TEST_ROLLBACK_DB" -c "INSERT INTO profiles (name) VALUES ('rollback_test');" > /dev/null

# Run rollback
if "$SCRIPT_DIR/migrate.sh" --rollback --force > /dev/null 2>&1; then
    # Check that tables are gone
    local table_count=$(psql -d "$TEST_ROLLBACK_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
    if [[ $table_count -eq 0 ]]; then
        print_status "success" "Rollback functionality working correctly"
    else
        print_status "error" "Rollback failed - $table_count tables still exist"
        exit 1
    fi
else
    print_status "error" "Rollback command failed"
    exit 1
fi

# Cleanup rollback test database
dropdb "$TEST_ROLLBACK_DB" 2>/dev/null || true

# Test summary
print_status "info" "Migration test summary:"
echo "  ✓ Dry run migration"
echo "  ✓ Full migration with verification"
echo "  ✓ Migration idempotency"
echo "  ✓ Manual verification"
echo "  ✓ CRUD operations"
echo "  ✓ Foreign key constraints"
echo "  ✓ Unique constraints"
echo "  ✓ JSONB functionality"
echo "  ✓ Rollback functionality"

print_status "success" "All migration tests passed!"

# Cleanup (optional - comment out if you want to inspect the test database)
print_status "info" "Cleaning up test database"
dropdb "$TEST_DB" 2>/dev/null || true

print_status "success" "Migration testing completed successfully!"
print_status "info" "The migration scripts are ready for production deployment"