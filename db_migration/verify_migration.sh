#!/bin/bash

# AnkiPi Database Migration Verification Script
# This script verifies that the database migration completed successfully

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    case $status in
        "success")
            echo -e "${GREEN}✓${NC} $message"
            ;;
        "error")
            echo -e "${RED}✗${NC} $message"
            ;;
        "warning")
            echo -e "${YELLOW}⚠${NC} $message"
            ;;
        "info")
            echo -e "${YELLOW}ℹ${NC} $message"
            ;;
    esac
}

# Check required environment variables
check_environment() {
    print_status "info" "Checking environment variables..."
    
    local required_vars=("POSTGRES_HOST" "POSTGRES_USER" "POSTGRES_DB")
    local missing_vars=()
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        print_status "error" "Missing required environment variables: ${missing_vars[*]}"
        print_status "info" "Set the following variables:"
        for var in "${missing_vars[@]}"; do
            echo "  export $var=\"your-value\""
        done
        exit 1
    fi
    
    print_status "success" "Environment variables are set"
}

# Test database connectivity
test_connection() {
    print_status "info" "Testing database connection..."
    
    if psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;" > /dev/null 2>&1; then
        print_status "success" "Database connection successful"
    else
        print_status "error" "Failed to connect to database"
        print_status "info" "Check your connection parameters and network connectivity"
        exit 1
    fi
}

# Verify extensions
verify_extensions() {
    print_status "info" "Verifying required extensions..."
    
    local extensions_query="SELECT extname FROM pg_extension WHERE extname = 'uuid-ossp';"
    local extensions_count=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$extensions_query" | wc -l)
    
    if [[ $extensions_count -ge 1 ]]; then
        print_status "success" "uuid-ossp extension is installed"
    else
        print_status "error" "uuid-ossp extension is missing"
        exit 1
    fi
}

# Verify tables exist
verify_tables() {
    print_status "info" "Verifying table creation..."
    
    local expected_tables=(
        "profiles"
        "decks" 
        "cards"
        "pass"
        "note_types"
        "card_templates"
        "leech_helper_history"
        "check_in"
        "deck_recipe_prompts"
        "deck_stats"
        "recipe_prompts"
        "old_problems"
    )
    
    local tables_query="SELECT tablename FROM pg_tables WHERE schemaname = 'public';"
    local existing_tables=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$tables_query" | tr -d ' ')
    
    local missing_tables=()
    for table in "${expected_tables[@]}"; do
        if ! echo "$existing_tables" | grep -q "^$table$"; then
            missing_tables+=("$table")
        fi
    done
    
    if [[ ${#missing_tables[@]} -eq 0 ]]; then
        print_status "success" "All ${#expected_tables[@]} tables created successfully"
    else
        print_status "error" "Missing tables: ${missing_tables[*]}"
        exit 1
    fi
}

# Verify indexes
verify_indexes() {
    print_status "info" "Verifying performance indexes..."
    
    local expected_indexes=(
        "idx_profiles_uuid"
        "idx_pass_leech_helper_pending"
        "idx_deck_stats_profile_date"
        "idx_deck_stats_deck_date"
        "idx_cards_last_not_again"
        "idx_old_problems_uuid"
        "idx_decks_graduated_count"
    )
    
    local indexes_query="SELECT indexname FROM pg_indexes WHERE schemaname = 'public';"
    local existing_indexes=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$indexes_query" | tr -d ' ')
    
    local missing_indexes=()
    for index in "${expected_indexes[@]}"; do
        if ! echo "$existing_indexes" | grep -q "^$index$"; then
            missing_indexes+=("$index")
        fi
    done
    
    if [[ ${#missing_indexes[@]} -eq 0 ]]; then
        print_status "success" "All performance indexes created successfully"
    else
        print_status "warning" "Missing indexes: ${missing_indexes[*]}"
        print_status "info" "Indexes are optional but recommended for performance"
    fi
}

# Verify constraints and foreign keys
verify_constraints() {
    print_status "info" "Verifying database constraints..."
    
    # Check for unique constraints
    local unique_constraints_query="
        SELECT COUNT(*) FROM information_schema.table_constraints 
        WHERE constraint_type = 'UNIQUE' AND table_schema = 'public';
    "
    local unique_count=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$unique_constraints_query" | tr -d ' ')
    
    # Check for foreign key constraints  
    local fk_constraints_query="
        SELECT COUNT(*) FROM information_schema.table_constraints 
        WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public';
    "
    local fk_count=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$fk_constraints_query" | tr -d ' ')
    
    if [[ $unique_count -gt 0 ]] && [[ $fk_count -gt 0 ]]; then
        print_status "success" "Database constraints created successfully ($unique_count unique, $fk_count foreign key)"
    else
        print_status "warning" "Some constraints may be missing (unique: $unique_count, FK: $fk_count)"
    fi
}

# Test basic CRUD operations
test_basic_operations() {
    print_status "info" "Testing basic database operations..."
    
    # Test insert
    local test_profile="test_migration_$(date +%s)"
    local insert_query="INSERT INTO profiles (name, created_at) VALUES ('$test_profile', NOW()) RETURNING profile_id;"
    local profile_id=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$insert_query" | tr -d ' ')
    
    if [[ -n "$profile_id" ]]; then
        print_status "success" "Insert operation successful (profile_id: $profile_id)"
        
        # Test select
        local select_query="SELECT name FROM profiles WHERE profile_id = $profile_id;"
        local selected_name=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$select_query" | tr -d ' ')
        
        if [[ "$selected_name" == "$test_profile" ]]; then
            print_status "success" "Select operation successful"
            
            # Test update
            local update_query="UPDATE profiles SET personalization = 'test migration' WHERE profile_id = $profile_id;"
            psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$update_query" > /dev/null
            print_status "success" "Update operation successful"
            
            # Test delete (cleanup)
            local delete_query="DELETE FROM profiles WHERE profile_id = $profile_id;"
            psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$delete_query" > /dev/null
            print_status "success" "Delete operation successful"
        else
            print_status "error" "Select operation failed"
        fi
    else
        print_status "error" "Insert operation failed"
    fi
}

# Print database statistics
print_statistics() {
    print_status "info" "Database migration statistics:"
    
    # Table count
    local table_count_query="SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"
    local table_count=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$table_count_query" | tr -d ' ')
    echo "  Tables created: $table_count"
    
    # Index count
    local index_count_query="SELECT COUNT(*) FROM pg_indexes WHERE schemaname = 'public';"
    local index_count=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$index_count_query" | tr -d ' ')
    echo "  Indexes created: $index_count"
    
    # Total database size
    local db_size_query="SELECT pg_size_pretty(pg_database_size('$POSTGRES_DB'));"
    local db_size=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$db_size_query" | tr -d ' ')
    echo "  Database size: $db_size"
    
    # PostgreSQL version
    local version_query="SELECT version();"
    local pg_version=$(psql -h "$POSTGRES_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "$version_query" | cut -d',' -f1 | tr -d ' ')
    echo "  PostgreSQL: $pg_version"
}

# Main execution
main() {
    echo "===========================================" 
    echo "AnkiPi Database Migration Verification"
    echo "==========================================="
    echo
    
    check_environment
    test_connection
    verify_extensions
    verify_tables
    verify_indexes
    verify_constraints
    test_basic_operations
    
    echo
    print_statistics
    echo
    print_status "success" "Database migration verification completed successfully!"
    print_status "info" "Your AnkiPi database is ready for production use."
}

# Run main function
main "$@"