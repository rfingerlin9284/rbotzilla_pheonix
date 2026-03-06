#!/bin/bash
# ==============================================================================
# RBOTZILLA PHOENIX - MASTER TURN ON SCRIPT
# ==============================================================================
# This script safely starts the autonomous trading bot in the background
# so that it continues running even if you close VSCode or your terminal.
#
# RUNNING: ./turn_on.sh
# ==============================================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SESSION_NAME="rbot_engine"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}                RBOTZILLA MASTER TURN ON                        ${NC}"
echo -e "${CYAN}================================================================${NC}"

# Check if the virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Error: 'venv' not found. Please run ./setup.sh first.${NC}"
    exit 1
fi

# Check if the process is already running
if pgrep -f "orchestrator_start.py" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️ Notice: The autonomous engine is already running!${NC}"
    echo -e "${GREEN}Use './STATUS.sh' to check on it.${NC}"
    exit 0
fi

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo -e "${RED}❌ Error: 'tmux' is not installed. Please run: sudo apt install tmux${NC}"
    exit 1
fi

echo -e "${YELLOW}Booting up the Autonomous Trading Engine in the background...${NC}"

# Create a new detached tmux session and start the engine
tmux new-session -d -s $SESSION_NAME "source venv/bin/activate && python3 orchestrator_start.py --auto"

echo -e ""
echo -e "${GREEN}✅ SUCCESS: The bot is now turned ON and running autonomously!${NC}"
echo -e ""
echo -e "${CYAN}================= QUICK COMMANDS ==============================${NC}"
echo -e " 👁️  ${YELLOW}View the bot running:${NC}  tmux attach -t rbot_engine"
echo -e " 📊 ${YELLOW}Check portfolio status:${NC} ./STATUS.sh"
echo -e " 🔴 ${YELLOW}Stop the bot safely:${NC}   ./turn_off.sh"
echo -e "${CYAN}================================================================${NC}"
