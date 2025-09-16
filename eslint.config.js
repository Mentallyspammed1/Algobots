import globals from "globals";
import pluginJs from "@eslint/js";

export default [
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node, // Add Node.js global variables
      },
    },
    rules: {
      "no-unused-vars": "off", // Temporarily turn off for unused variables
      "no-undef": ["error", { "typeof": true }], // Allow typeof for undefined variables
    },
  },
  pluginJs.configs.recommended,
];