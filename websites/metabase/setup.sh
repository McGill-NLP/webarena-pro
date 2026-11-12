#!/bin/bash
# Setup script for Metabase: first-time setup, database, questions, dashboards, docs, and auth state
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Metabase Setup ==="
echo ""

echo "Step 1/6: First-time setup (create admin user)..."
python "$SCRIPT_DIR/setup_scripts/setup_login.py"
echo ""

echo "Step 2/6: Adding database..."
python "$SCRIPT_DIR/setup_scripts/add_database.py"
echo ""

echo "Step 3/6: Creating SQL query..."
python "$SCRIPT_DIR/setup_scripts/add_sql_query.py"
echo ""

echo "Step 4/6: Creating Sales dashboard..."
python "$SCRIPT_DIR/setup_scripts/add_dashboard.py"
echo ""

echo "Step 5/6: Creating AgentLab documentation..."
python "$SCRIPT_DIR/setup_scripts/add_documentation.py"
echo ""

echo "Step 6/6: Saving auth state for browser agent..."
python "$SCRIPT_DIR/setup_scripts/save_auth_state.py"
echo ""

echo "=== Setup Complete ==="
