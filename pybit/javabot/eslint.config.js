import globals from "globals";
import pluginJs from "@eslint/js";

export default [
  pluginJs.configs.recommended,
  {
    languageOptions: {
      globals: {
        ...globals.node,
      }
    },
    rules: {
      'no-control-regex': 'off',
    }
  },
  {
    files: ["**/*.test.js", "**/tests/**/*.js"],
    languageOptions: {
      globals: {
        ...globals.jest,
      }
    },
    rules: {
      // You might want to add specific rules for test files here
    }
  }
];