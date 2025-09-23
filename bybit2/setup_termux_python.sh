#!/bin/bash

# Pyrmethus, the Termux Coding Wizard, channels the arcane energies to prepare your Python realm!

echo -e "\033[1;35m# Initiating the ritual to set up Python development environment in Termux...\033[0m"

# Update and upgrade the sacred scrolls (packages)
echo -e "\033[0;36m# Updating and upgrading Termux packages...\033[0m"
pkg update -y && pkg upgrade -y
echo -e "\033[1;32m# Termux packages are now in harmony!\033[0m"

# Install Python and pip, the essential components
echo -e "\033[0;36m# Installing Python and pip, the core of your incantations...\033[0m"
pkg install python -y
echo -e "\033[1;32m# Python and pip have been successfully summoned!\033[0m"

# Install essential Python libraries using pip
echo -e "\033[0;36m# Forging essential Python libraries: requests, python-bybit, and colorama...\033[0m"
pip install requests python-bybit colorama python-dotenv
echo -e "\033[1;32m# All required Python libraries have been woven into your environment!\033[0m"

echo -e "\033[1;35m# The Python development environment in Termux is now fully enchanted!\033[0m"
echo -e "\033[0;33m# You can now begin crafting your Bybit API spells.\033[0m"
echo -e "\033[0;33m# Remember to run this script with: bash setup_termux_python.sh\033[0m"
