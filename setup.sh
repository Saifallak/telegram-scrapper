#!/bin/bash
# Telegram Product Scraper - Setup Script
# This script automates the initial setup process

set -e  # Exit on error

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   🤖 Telegram Product Scraper - Setup Script             ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check Python version
echo -e "${BLUE}[1/6]${NC} Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION found"
else
    echo -e "${RED}✗${NC} Python 3 not found. Please install Python 3.8+"
    exit 1
fi

# Create virtual environment
echo ""
echo -e "${BLUE}[2/6]${NC} Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
else
    echo -e "${YELLOW}!${NC} Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo -e "${BLUE}[3/6]${NC} Activating virtual environment..."
source venv/bin/activate 2>/dev/null || . venv/Scripts/activate 2>/dev/null || {
    echo -e "${RED}✗${NC} Failed to activate virtual environment"
    exit 1
}
echo -e "${GREEN}✓${NC} Virtual environment activated"

# Install dependencies
echo ""
echo -e "${BLUE}[4/6]${NC} Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo -e "${GREEN}✓${NC} Dependencies installed"

# Setup .env file
echo ""
echo -e "${BLUE}[5/6]${NC} Setting up configuration..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓${NC} Created .env file from template"
    echo -e "${YELLOW}!${NC} Please edit .env with your credentials:"
    echo ""
    echo "  Required:"
    echo "    • TELEGRAM_API_ID"
    echo "    • TELEGRAM_API_HASH"
    echo "    • TELEGRAM_PHONE"
    echo ""
    echo "  Optional:"
    echo "    • GEMINI_API_KEY (for AI extraction)"
    echo "    • BACKEND_URL (for API integration)"
    echo ""
else
    echo -e "${YELLOW}!${NC} .env file already exists"
fi

# Create directories
echo ""
echo -e "${BLUE}[6/6]${NC} Creating directories..."
mkdir -p downloaded_images
echo -e "${GREEN}✓${NC} Created downloaded_images directory"

# Summary
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║   ✅ Setup Complete!                                      ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1. Edit configuration:"
echo -e "     ${BLUE}nano .env${NC}"
echo ""
echo "  2. Get Telegram credentials:"
echo -e "     ${BLUE}https://my.telegram.org${NC}"
echo ""
echo "  3. (Optional) Get Gemini API key:"
echo -e "     ${BLUE}https://makersuite.google.com/app/apikey${NC}"
echo ""
echo "  4. Test Gemini API (optional):"
echo -e "     ${BLUE}python test_gemini.py${NC}"
echo ""
echo "  5. Run the scraper:"
echo -e "     ${BLUE}python scraper.py${NC}"
echo ""
echo "📚 For more information, see README.md"
echo ""
