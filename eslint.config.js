import globals from "globals";
import pluginJs from "@eslint/js";

export default [
  pluginJs.configs.recommended,
  {
    files: ["src/**/*.js"],
    languageOptions: {
      globals: {
        ...globals.node,
      },
      sourceType: "commonjs",
    },
    rules: {
      "no-unused-vars": "warn",
      "no-undef": ["error", { "typeof": true }],
    },
  },
];
