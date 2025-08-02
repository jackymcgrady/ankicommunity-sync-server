#!/bin/bash
#
# Wrapper script for resetting user collections.
# This script runs the Python reset script inside the Docker container.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_usage() {
    echo "Usage: $0 <username> [options]"
    echo ""
    echo "Reset a user's Anki collection and media data on the sync server."
    echo ""
    echo "Options:"
    echo "  --confirm           Actually perform the reset (required for safety)"
    echo "  --keep-media-files  Keep physical media files, only reset database tracking"
    echo "  --help             Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 john.doe                    # Dry run (shows what would be deleted)"
    echo "  $0 john.doe --confirm          # Actually perform the reset"
    echo "  $0 john.doe --confirm --keep-media-files  # Reset but keep media files"
    echo ""
    echo "WARNING: This operation is DESTRUCTIVE and cannot be undone!"
}

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null; then
    print_color $RED "Error: docker-compose not found. Please install Docker Compose."
    exit 1
fi

# Check if we're in the right directory
if [[ ! -f "$PROJECT_ROOT/docker-compose.latest.yml" ]]; then
    print_color $RED "Error: docker-compose.latest.yml not found. Please run this script from the project root."
    exit 1
fi

# Parse arguments
if [[ $# -eq 0 ]] || [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    print_usage
    exit 0
fi

USERNAME="$1"
shift

# Check if username is valid
if [[ -z "$USERNAME" ]] || [[ "$USERNAME" =~ ^- ]]; then
    print_color $RED "Error: Please provide a valid username."
    print_usage
    exit 1
fi

# Check if containers are running
if ! docker-compose -f "$PROJECT_ROOT/docker-compose.latest.yml" ps | grep -q "Up"; then
    print_color $YELLOW "Starting Docker containers..."
    cd "$PROJECT_ROOT"
    docker-compose -f docker-compose.latest.yml up -d
    sleep 5
fi

# Build the command
PYTHON_CMD="python3 /app/scripts/reset_user_collection.py $USERNAME"

# Add any additional arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --confirm)
            PYTHON_CMD="$PYTHON_CMD --confirm"
            shift
            ;;
        --keep-media-files)
            PYTHON_CMD="$PYTHON_CMD --keep-media-files"
            shift
            ;;
        *)
            print_color $RED "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

print_color $BLUE "Executing reset script for user: $USERNAME"
print_color $BLUE "Command: $PYTHON_CMD"
echo ""

# Execute the command inside the container
cd "$PROJECT_ROOT"
if docker-compose -f docker-compose.latest.yml exec anki-sync-server-nginx bash -c "$PYTHON_CMD"; then
    if [[ "$PYTHON_CMD" == *"--confirm"* ]]; then
        print_color $GREEN "✅ User reset completed successfully!"
    else
        print_color $YELLOW "ℹ️  Dry run completed. Use --confirm to actually perform the reset."
    fi
else
    print_color $RED "❌ Reset operation failed. Check the output above for details."
    exit 1
fi