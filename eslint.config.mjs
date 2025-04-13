import pluginJs from "@eslint/js";
import pluginTs from "typescript-eslint";
import pluginReact from "eslint-plugin-react";
import pluginReactHooks from "eslint-plugin-react-hooks";
import pluginNext from "@next/eslint-plugin-next";
import pluginPrettier from "eslint-config-prettier";
import globals from "globals";

export default [
  { ignores: [".next"] },
  {
    languageOptions: {
      globals: globals.browser,
      parser: {
        ts: pluginTs.parser,
      },
    },
  },
  pluginJs.configs.recommended,
  ...pluginTs.configs.recommended,
  {
    files: ["**/*.{tsx,jsx,js,ts}"],
    languageOptions: {
      parserOptions: {
        ecmaFeatures: {
          jsx: true,
        },
      },
    },
    plugins: {
      react: pluginReact.configs.flat.recommended,
      "react-hooks": pluginReactHooks.configs.recommended,
      "@next/next": {
        ...pluginNext.configs.recommended,
        ...pluginNext.configs["core-web-vitals"],
      },
    },
    settings: {
      version: "detect",
    },
  },
  pluginPrettier,
];
