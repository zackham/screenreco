#!/bin/bash

# screenreco installation script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================"
echo "  screenreco Installation"
echo "================================"
echo

# Check for required dependencies
echo "Checking dependencies..."

check_command() {
    if command -v "$1" >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $1 found"
        return 0
    else
        echo -e "${RED}✗${NC} $1 not found"
        return 1
    fi
}

missing_deps=0
check_command wf-recorder || missing_deps=1
check_command slurp || missing_deps=1
check_command wl-copy || missing_deps=1
check_command curl || missing_deps=1
check_command gcc || missing_deps=1
check_command make || missing_deps=1
check_command pkg-config || missing_deps=1
check_command wayland-scanner || missing_deps=1

if [ $missing_deps -eq 1 ]; then
    echo
    echo -e "${RED}Error: Missing required dependencies${NC}"
    echo "Please install the missing packages using your package manager."
    echo
    echo "For Arch Linux:"
    echo "  sudo pacman -S wf-recorder slurp wl-clipboard curl wayland wayland-protocols gtk3"
    echo "  yay -S wlr-protocols"
    echo
    echo "For other distributions, see README.md"
    exit 1
fi

echo
echo "Building screenreco..."

# Build the project
if make clean && make; then
    echo -e "${GREEN}✓${NC} Build successful"
else
    echo -e "${RED}✗${NC} Build failed"
    exit 1
fi

echo
echo "Installing screenreco..."

# Default to /usr/local if no PREFIX specified
PREFIX="${PREFIX:-/usr/local}"

# Check if we need sudo
if [ -w "$PREFIX/bin" ]; then
    make install PREFIX="$PREFIX"
else
    echo "Need sudo privileges to install to $PREFIX"
    sudo make install PREFIX="$PREFIX"
fi

echo
echo -e "${GREEN}Installation complete!${NC}"
echo
echo "Usage:"
echo "  screenreco              # Record screen area"
echo "  screenreco --with-audio # Record with audio"
echo
echo "Add these keybindings to your Hyprland config:"
echo "  bind = SUPER SHIFT, R, exec, screenreco"
echo "  bind = SUPER CTRL, R, exec, screenreco --with-audio"
echo
echo "See README.md for more configuration options."