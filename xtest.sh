#!/bin/bash

# Colors for better visibility
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Setting up test environment...${NC}"

# Check for Python 3.11
if ! command -v python3.11 &> /dev/null; then
    echo -e "${RED}Python 3.11 is required but not installed!${NC}"
    exit 1
fi

# Name our test venv differently to avoid conflicts
VENV_NAME="test_venv"

# Remove existing test venv if it exists
if [ -d "$VENV_NAME" ]; then
    echo -e "${YELLOW}Removing existing test virtual environment...${NC}"
    rm -rf "$VENV_NAME"
fi

# Create new venv
echo -e "${YELLOW}Creating new virtual environment with Python 3.11...${NC}"
python3.11 -m venv "$VENV_NAME"

# Activate venv
echo -e "${YELLOW}Activating virtual environment...${NC}"
source "$VENV_NAME/bin/activate"

# Install minimal requirements
echo -e "${YELLOW}Installing required packages...${NC}"
pip install playwright python-dotenv

# Install Playwright dependencies
echo -e "${YELLOW}Installing Playwright browser...${NC}"
playwright install chromium

# Create convenience script to run test
echo -e "${YELLOW}Creating test runner script...${NC}"
cat > run_test.sh << 'EOL'
#!/bin/bash
source test_venv/bin/activate
python xtest.py
EOL

# Make scripts executable
chmod +x setup_test_env.sh run_test.sh

echo -e "${GREEN}Setup complete! Run ./run_test.sh to start the test${NC}"