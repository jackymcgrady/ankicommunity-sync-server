#!/bin/bash

# AnkiPi Database Migration Script
# This script handles the complete migration process for AnkiPi database schema

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/migration.log"
BACKUP_DIR="$SCRIPT_DIR/migration_backups"

# Function to print colored output
print_status() {
    local status=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $status in
        "success")
            echo -e "${GREEN}✓${NC} $message"
            echo "[$timestamp] SUCCESS: $message" >> "$LOG_FILE"
            ;;
        "error")
            echo -e "${RED}✗${NC} $message"
            echo "[$timestamp] ERROR: $message" >> "$LOG_FILE"
            ;;
        "warning")
            echo -e "${YELLOW}⚠${NC} $message"
            echo "[$timestamp] WARNING: $message" >> "$LOG_FILE"
            ;;
        "info")
            echo -e "${BLUE}ℹ${NC} $message"
            echo "[$timestamp] INFO: $message" >> "$LOG_FILE"
            ;;
    esac
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

AnkiPi Database Migration Script

OPTIONS:
    -h, --help              Show this help message
    -d, --dry-run          Show what would be done without executing
    -f, --force            Skip confirmation prompts
    -b, --backup           Create backup before migration
    -r, --rollback         Rollback the migration (removes all data)
    -v, --verify           Verify migration after completion
    --skip-verification    Skip post-migration verification

ENVIRONMENT VARIABLES:
    POSTGRES_HOST          PostgreSQL host (required)
    POSTGRES_PORT          PostgreSQL port (default: 5432)
    POSTGRES_DB            Database name (required)
    POSTGRES_USER          Database user (required)
    POSTGRES_PASSWORD      Database password (required)

EXAMPLES:
    # Standard migration with verification
    $0 --backup --verify
    
    # Dry run to see what would happen
    $0 --dry-run
    
    # Force migration without prompts
    $0 --force --backup
    
    # Rollback migration (DANGEROUS)
    $0 --rollback --force

EOF
}

# Function to check prerequisites
check_prerequisites() {
    print_status "info" "Checking prerequisites..."
    
    # Check if psql is available
    if ! command -v psql &> /dev/null; then
        print_status "error" "psql is not installed or not in PATH"
        print_status "info" "Install PostgreSQL client tools first"
        exit 1
    fi
    
    # Check required files
    local required_files=("create_schema.sql" "verify_migration.sh")
    for file in "${required_files[@]}"; do
        if [[ ! -f "$SCRIPT_DIR/$file" ]]; then
            print_status "error" "Required file not found: $file"
            exit 1
        fi
    done
    
    # Check environment variables
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
    
    # Set defaults
    export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
    
    print_status "success" "Prerequisites check completed"
}

# Function to test database connection
test_connection() {
    print_status "info" "Testing database connection..."
    
    if psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;" > /dev/null 2>&1; then
        print_status "success" "Database connection successful"
        
        # Get PostgreSQL version
        local pg_version=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT version();" | head -1 | cut -d',' -f1)
        print_status "info" "Connected to: $pg_version"
    else
        print_status "error" "Failed to connect to database"
        print_status "info" "Check your connection parameters and network connectivity"
        exit 1
    fi
}

# Function to create backup
create_backup() {
    if [[ "$CREATE_BACKUP" != "true" ]]; then
        return 0
    fi
    
    print_status "info" "Creating database backup..."
    
    # Create backup directory
    mkdir -p "$BACKUP_DIR"
    
    # Generate backup filename with timestamp
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_file="$BACKUP_DIR/ankipi_backup_${timestamp}.sql"
    
    # Create backup
    if pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$backup_file" 2>/dev/null; then
        print_status "success" "Database backup created: $backup_file"
        
        # Compress backup
        gzip "$backup_file" 2>/dev/null || true
        if [[ -f "${backup_file}.gz" ]]; then
            print_status "info" "Backup compressed: ${backup_file}.gz"
        fi
    else
        print_status "warning" "Failed to create backup, but continuing with migration"
    fi
}

# Function to check for existing data
check_existing_data() {
    print_status "info" "Checking for existing data..."
    
    # Check if any tables exist
    local table_count=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ' || echo "0")
    
    if [[ $table_count -gt 0 ]]; then
        print_status "warning" "Found $table_count existing tables in the database"
        
        # Check for AnkiPi tables specifically
        local ankipi_tables=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('profiles', 'decks', 'cards');" 2>/dev/null | tr -d ' ' || echo "0")
        
        if [[ $ankipi_tables -gt 0 ]]; then
            print_status "warning" "AnkiPi tables already exist - this may be an upgrade or re-run"
            
            if [[ "$FORCE_MODE" != "true" ]]; then
                read -p "Continue with migration? This may modify existing data (y/N): " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    print_status "info" "Migration cancelled by user"
                    exit 0
                fi
            fi
        fi
    else
        print_status "success" "No existing tables found - clean migration"
    fi
}

# Function to run migration
run_migration() {
    print_status "info" "Starting database migration..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "info" "DRY RUN: Would execute create_schema.sql"
        print_status "info" "DRY RUN: Would create 12 tables with indexes and constraints"
        return 0
    fi
    
    # Execute migration script
    if psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$SCRIPT_DIR/create_schema.sql" > /dev/null 2>&1; then
        print_status "success" "Database schema migration completed"
    else
        print_status "error" "Migration failed"
        print_status "info" "Check the log file for details: $LOG_FILE"
        
        # Try to get more specific error
        psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$SCRIPT_DIR/create_schema.sql" 2>&1 | tail -10 >> "$LOG_FILE"
        exit 1
    fi
}

# Function to run rollback
run_rollback() {
    print_status "warning" "ROLLBACK MODE: This will delete ALL AnkiPi data!"
    
    if [[ "$FORCE_MODE" != "true" ]]; then
        echo
        read -p "Are you absolutely sure you want to delete all data? Type 'DELETE_ALL_DATA' to confirm: " confirmation
        if [[ "$confirmation" != "DELETE_ALL_DATA" ]]; then
            print_status "info" "Rollback cancelled"
            exit 0
        fi
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "info" "DRY RUN: Would execute rollback_migration.sql"
        print_status "info" "DRY RUN: Would drop all AnkiPi tables and data"
        return 0
    fi
    
    # Execute rollback
    PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -v confirmation="DELETE_ALL_DATA" -f "$SCRIPT_DIR/rollback_migration.sql"
    
    print_status "success" "Database rollback completed"
}

# Function to verify migration
verify_migration() {
    if [[ "$SKIP_VERIFICATION" == "true" ]]; then
        print_status "info" "Skipping verification as requested"
        return 0
    fi
    
    print_status "info" "Running post-migration verification..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "info" "DRY RUN: Would run verification script"
        return 0
    fi
    
    # Run verification script
    if bash "$SCRIPT_DIR/verify_migration.sh"; then
        print_status "success" "Migration verification passed"
    else
        print_status "error" "Migration verification failed"
        exit 1
    fi
}

# Function to show migration summary
show_summary() {
    print_status "info" "Migration Summary:"
    echo "  Database: $POSTGRES_HOST:$POSTGRES_PORT/$POSTGRES_DB"
    echo "  User: $POSTGRES_USER"
    echo "  Mode: $([ "$DRY_RUN" == "true" ] && echo "DRY RUN" || echo "LIVE")"
    echo "  Backup: $([ "$CREATE_BACKUP" == "true" ] && echo "Yes" || echo "No")"
    echo "  Verification: $([ "$SKIP_VERIFICATION" == "true" ] && echo "Skipped" || echo "Yes")"
    echo "  Log file: $LOG_FILE"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        # Show table count
        local table_count=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ' || echo "unknown")
        echo "  Tables created: $table_count"
    fi
}

# Parse command line arguments
DRY_RUN=false
FORCE_MODE=false
CREATE_BACKUP=false
ROLLBACK_MODE=false
VERIFY_MIGRATION=false
SKIP_VERIFICATION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -f|--force)
            FORCE_MODE=true
            shift
            ;;
        -b|--backup)
            CREATE_BACKUP=true
            shift
            ;;
        -r|--rollback)
            ROLLBACK_MODE=true
            shift
            ;;
        -v|--verify)
            VERIFY_MIGRATION=true
            shift
            ;;
        --skip-verification)
            SKIP_VERIFICATION=true
            shift
            ;;
        *)
            print_status "error" "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
main() {
    # Initialize log file
    echo "===========================================" > "$LOG_FILE"
    echo "AnkiPi Database Migration Log" >> "$LOG_FILE"
    echo "Started: $(date)" >> "$LOG_FILE"
    echo "===========================================" >> "$LOG_FILE"
    
    print_status "info" "Starting AnkiPi database migration"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_status "info" "Running in DRY RUN mode - no changes will be made"
    fi
    
    # Run checks
    check_prerequisites
    test_connection
    
    if [[ "$ROLLBACK_MODE" == "true" ]]; then
        run_rollback
    else
        check_existing_data
        create_backup
        run_migration
        
        if [[ "$VERIFY_MIGRATION" == "true" || ("$DRY_RUN" != "true" && "$SKIP_VERIFICATION" != "true") ]]; then
            verify_migration
        fi
    fi
    
    show_summary
    
    if [[ "$DRY_RUN" != "true" ]]; then
        print_status "success" "Migration completed successfully!"
        print_status "info" "Your AnkiPi database is ready for production use"
    else
        print_status "info" "Dry run completed - use without --dry-run to execute"
    fi
}

# Handle script interruption
trap 'print_status "error" "Migration interrupted"; exit 1' INT TERM

# Run main function
main "$@"