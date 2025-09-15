# Unified Code Quality Workflow

This document outlines the unified code quality workflow for this project.

## Overview

The `unified-code-quality.yml` workflow is a single, centralized workflow that handles code quality checks for both Python and JavaScript/TypeScript code. It is triggered on every push and pull request to the `main` and `develop` branches.

The workflow consists of two parallel jobs:

*   `python-quality`: This job checks the quality of Python code using `pylint`, `flake8`, and `black`.
*   `javascript-quality`: This job checks the quality of JavaScript/TypeScript code using `eslint` and `stylelint`.

If any of these jobs find linting errors, they will automatically create a new pull request with the fixes.

## Usage

To use this workflow, simply push your code to a branch that has a pull request open against `main` or `develop`. The workflow will automatically run and report any linting errors. If there are any auto-fixable errors, a new pull request will be created with the fixes.
