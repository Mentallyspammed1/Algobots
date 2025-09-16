#!/bin/bash

# Gemini CLI Installation and Troubleshooting Script for Android/Termux

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Prerequisite Check Function
check_prerequisites() {
    echo -e "${YELLOW}Checking System Prerequisites...${NC}"
    
    # Check Termux and package manager
    if [ ! -f "/data/data/com.termux/files/usr/bin/pkg" ]; then
        echo -e "${RED}Error: Not running in Termux environment${NC}"
        exit 1
    fi

    # Update package lists
    pkg update -y
}

# Node.js and NPM Setup
setup_nodejs() {
    echo -e "${YELLOW}Setting up Node.js and NPM...${NC}"
    
    # Install Node.js LTS and npm
    pkg install nodejs-lts -y

    # Verify Node.js installation
    NODE_VERSION=$(node -v)
    NPM_VERSION=$(npm -v)
    
    echo -e "${GREEN}Node.js Version: $NODE_VERSION${NC}"
    echo -e "${GREEN}NPM Version: $NPM_VERSION${NC}"
}

# Install Android NDK
install_android_ndk() {
    echo -e "${YELLOW}Installing Android NDK...${NC}"
    
    # Install required build tools
    pkg install android-ndk -y

    # Set NDK path
    export ANDROID_NDK_HOME="/data/data/com.termux/files/usr/opt/android-ndk"
    echo "export ANDROID_NDK_HOME=$ANDROID_NDK_HOME" >> ~/.bashrc
}

# Gemini CLI Installation
install_gemini_cli() {
    echo -e "${YELLOW}Installing Google Gemini CLI...${NC}"
    
    # Clean npm cache and global modules
    npm cache clean --force
    
    # Use specific Node.js version compatibility
    npm install -g n
    n lts
    
    # Install Gemini CLI with verbose logging
    npm install -g @google/gemini-cli --verbose
}

# Troubleshooting Wrapper
main() {
    echo -e "${GREEN}🤖 Gemini CLI Installer for Android/Termux 🤖${NC}"
    
    check_prerequisites
    setup_nodejs
    install_android_ndk
    
    # Attempt Gemini CLI installation with error handling
    if ! install_gemini_cli; then
        echo -e "${RED}Gemini CLI installation failed. Manual intervention required.${NC}"
        echo -e "${YELLOW}Possible solutions:
1. Check your internet connection
2. Verify NPM and Node.js configurations
3. Check Gemini CLI compatibility with your Android setup${NC}"
        exit 1
    fi

    echo -e "${GREEN}✅ Gemini CLI installed successfully!${NC}"
}

# Run the main function
main
