# Feature Implementation Plan: Unified Code Quality Workflow

## 📋 Todo Checklist
- [x] Create new `unified-code-quality.yml` workflow file.
- [x] Implement a consolidated Python quality check job.
- [x] Implement a consolidated JavaScript/TypeScript quality check job.
- [x] Standardize auto-fix PR creation for both language jobs.
- [x] Remove old, redundant code quality workflow files.
- [x] Document the new workflow and its usage.
- [x] Final Review and Testing.

## 🔍 Analysis & Investigation

### Codebase Structure
I have inspected the following GitHub Actions workflow files:
- `.github/workflows/code-quality.yml`
- `.github/workflows/gemini-dispatch.yml`
- `.github/workflows/gemini-invoke.yml`
- `.github/workflows/gemini-review.yml`
- `.github/workflows/gemini-scheduled-triage.yml`
- `.github/workflows/gemini-triage.yml`
- `.github/workflows/gemini_lint_and_fix.yml`
- `.github/workflows/pylint.yml`

The investigation reveals multiple workflows (`code-quality.yml`, `gemini_lint_and_fix.yml`, `pylint.yml`) responsible for code quality checks. They are triggered on similar events (`push`, `pull_request`) but operate independently and with different logic.

### Current Architecture
The current setup is fragmented:
- **`code-quality.yml`**: Handles JS/TS files. It uses `npm` scripts and a dedicated Node.js script (`analyze-with-gemini.js`) to analyze issues and creates a new pull request with fixes.
- **`gemini_lint_and_fix.yml`**: Handles Python files. It runs `pylint` and `flake8`, uses an inline Python script to query the Gemini API, applies `black` formatting, and then commits fixes directly to the branch.
- **`pylint.yml`**: A simple workflow that only runs `pylint` across multiple Python versions, which is redundant if other workflows are already performing linting.

This fragmentation leads to maintenance overhead and inconsistent behavior in how automated fixes are applied.

### Dependencies & Integration Points
- **Linters**: `ESLint`, `Stylelint` (for JS/TS), `Pylint`, `Flake8`, `Black` (for Python).
- **GitHub Actions**: `actions/checkout`, `actions/setup-node`, `actions/setup-python`, `peter-evans/create-pull-request`.
- **APIs**: Google Gemini API for code analysis and suggestions.

### Considerations & Challenges
- **Inconsistent Auto-Fix Strategy**: The JS workflow creates a PR (good practice), while the Python workflow commits directly to the feature branch (bad practice, pollutes git history). This must be standardized.
- **Scripting Logic**: The JS workflow uses a standalone script (`.github/scripts/analyze-with-gemini.js`) while the Python workflow uses a large inline script. Consolidating this logic into dedicated scripts in a `.github/scripts/` directory would improve maintainability.
- **Redundancy**: The `pylint.yml` workflow is entirely redundant and should be removed.

The optimal approach is to create a single, unified workflow that orchestrates code quality checks for all languages, standardizes the auto-fix mechanism, and improves maintainability by centralizing scripts.

## 📝 Implementation Plan

### Prerequisites
- Ensure `GEMINI_API_KEY` and `GITHUB_TOKEN` secrets are available to the repository.
- The `peter-evans/create-pull-request` action should be available.

### Step-by-Step Implementation
1. **Create Unified Workflow File**:
   - Files to modify: Create `.github/workflows/unified-code-quality.yml`.
   - Changes needed: Initialize a new workflow file with a descriptive name like "Unified Code Quality". Define the triggers to be `on: [push, pull_request]` for the `main` and `develop` branches.

2. **Implement Python Quality Job**:
   - Files to modify: `.github/workflows/unified-code-quality.yml`.
   - Changes needed:
     - Create a new job named `python-quality`.
     - Add steps to check out the code, set up Python, and install dependencies (`pylint`, `flake8`, `black`, `google-generativeai`).
     - Add a step to run `pylint` and `flake8`, saving their output to report files (e.g., `pylint-report.txt`, `flake8-report.txt`).
     - **(Optional but Recommended)** Create a new script at `.github/scripts/analyze_python.py` that takes the report files as input, queries the Gemini API, and generates a structured list of fixes.
     - Add a step in the workflow to execute this new script.
     - Add a step to run `black .` to format the code.
     - Use the `peter-evans/create-pull-request` action to generate an auto-fix PR if any changes were made by `black` or the Gemini analysis. This standardizes the fixing process.

3. **Implement JS/TS Quality Job**:
   - Files to modify: `.github/workflows/unified-code-quality.yml`.
   - Changes needed:
     - Create a new job named `javascript-quality`.
     - Copy the core logic from the existing `.github/workflows/code-quality.yml`.
     - Ensure it uses the existing `.github/scripts/analyze-with-gemini.js` script and the `peter-evans/create-pull-request` action.
     - Make sure this job runs in parallel with the `python-quality` job.

4. **Deprecate Old Workflows**:
   - Files to modify: None. This is a removal step.
   - Changes needed: Plan for the deletion of the following files in the final implementation PR:
     - `.github/workflows/code-quality.yml`
     - `.github/workflows/gemini_lint_and_fix.yml`
     - `.github/workflows/pylint.yml`

### Testing Strategy
1. Create a new branch for testing.
2. Create a pull request from this branch that contains files with known, simple linting errors for both Python (`.py`) and JavaScript (`.ts`).
3. Push the changes and verify that the `unified-code-quality.yml` workflow is triggered on the PR.
4. Check that both the `python-quality` and `javascript-quality` jobs execute successfully.
5. Verify that the workflow correctly identifies the linting issues.
6. Confirm that a new pull request is automatically created, targeting the test branch, which contains the auto-formatted and auto-fixed code for both languages.
7. Merge the auto-fix PR and then the original test PR to ensure the `main` or `develop` branch remains clean and the workflow functions as expected.

## 🎯 Success Criteria
- A single workflow file, `unified-code-quality.yml`, is responsible for all push/PR-triggered code quality checks.
- The old, redundant workflow files (`code-quality.yml`, `gemini_lint_and_fix.yml`, `pylint.yml`) have been deleted from the repository.
- Automated fixes for both Python and JS/TS are consistently applied via new, separate pull requests rather than direct commits to feature branches.
- The project's CI/CD configuration is more maintainable and easier to understand.
