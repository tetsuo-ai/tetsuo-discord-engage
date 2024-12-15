#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Starting setup...${NC}"

# Check for Python 3.11
if ! command -v python3.11 &> /dev/null; then
    echo -e "${RED}Python 3.11 is required but not installed!${NC}"
    exit 1
fi

# Remove existing venv if it exists
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Removing existing virtual environment...${NC}"
    rm -rf .venv
fi

# Create new venv
echo -e "${YELLOW}Creating new virtual environment with Python 3.11...${NC}"
python3.11 -m venv .venv

# Activate venv
echo -e "${YELLOW}Activating virtual environment...${NC}"
source .venv/bin/activate

# Upgrade pip
echo -e "${YELLOW}Upgrading pip...${NC}"
pip install --upgrade pip

# Install requirements
echo -e "${YELLOW}Installing requirements...${NC}"
pip install -r requirements.txt

# Install Playwright dependencies
echo -e "${YELLOW}Installing Playwright dependencies...${NC}"
sudo /home/tetsuo-engage/tetsuo-discord-engage/.venv/bin/playwright install --with-deps --only-shell

echo -e "${GREEN}Setup complete! You can now run 'python main.py'${NC}"

# Create a convenience script to start the bot
echo -e "${YELLOW}Creating start script...${NC}"
cat > start.sh << 'EOL'
#!/bin/bash
source .venv/bin/activate
python main.py
EOL

# Make start script executable
chmod +x start.sh

echo -e "${GREEN}Created start.sh - you can now run ./start.sh to start the bot${NC}"