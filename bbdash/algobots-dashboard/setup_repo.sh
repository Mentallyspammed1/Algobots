#!/bin/bash

# This script initializes a new Git repository, adds all files,
# and makes the initial commit. It also includes placeholder commands
# to add a remote and push your code.

# Initialize a new Git repository
echo "Initializing Git repository..."
git init

# Add all files to the staging area
echo "Adding all files..."
git add .

# Create the initial commit
echo "Creating initial commit..."
git commit -m "Initial commit: AI Trading Dashboard"

echo ""
echo "Git repository initialized and initial commit created successfully."
echo ""
echo "Next steps:"
echo "1. Create a new repository on a hosting service (e.g., GitHub, GitLab)."
echo "2. Copy the repository URL."
echo "3. Uncomment and replace the placeholder URL in the commands below."
echo ""

# echo "Adding remote origin..."
# git remote add origin <YOUR_REPOSITORY_URL_HERE>

# echo "Pushing initial commit to remote..."
# git push -u origin master

echo "Done."
