import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

const SourceFiles = ["src/**/*.ts", "src/**/*.test.ts"];

export default tseslint.config(
    {
        extends: [js.configs.recommended],
        files: SourceFiles,
    },
    {
        extends: [tseslint.configs.recommendedTypeChecked],
        files: SourceFiles,
    },
    {
        files: SourceFiles,
        languageOptions: {
            globals: { ...globals.browser, ...globals.node },
            parserOptions: {
                projectService: true,
                tsconfigRootDir: import.meta.dirname,
            },
        },
        rules: {
            "@typescript-eslint/no-non-null-assertion": 0,
            "@typescript-eslint/restrict-template-expressions": 0,
            "@typescript-eslint/prefer-literal-enum-member": 0,
            "@typescript-eslint/consistent-type-imports": "error",
            "@typescript-eslint/no-import-type-side-effects": "error",

            "@typescript-eslint/no-unused-expressions": 0, // it keeps flagging logtape log calls

            "no-unused-private-class-members": "warn",

            "no-unused-vars": "off",
            "@typescript-eslint/no-unused-vars": [
                "warn",
                {
                    argsIgnorePattern: "^_",
                    caughtErrorsIgnorePattern: "^_",
                    varsIgnorePattern: "^_",
                },
            ],

            camelcase: [
                "error",
                {
                    allow: ["content_type"],
                },
            ],

            "no-eval": "error",
            "no-implied-eval": "error",
            "no-invalid-this": "error",
            "@typescript-eslint/no-shadow": "error",
            "no-shadow": 0,
            "@typescript-eslint/promise-function-async": "error",
            "prefer-promise-reject-errors": "error",
            "require-atomic-updates": 0, // wayyy too many false positives
            "no-template-curly-in-string": "error",
            "no-unmodified-loop-condition": "error",
            "no-useless-assignment": "warn",
            eqeqeq: "warn",
            "prefer-const": 0,

            "@typescript-eslint/no-unsafe-enum-comparison": "warn", // TODO
            "@typescript-eslint/no-explicit-any": "warn", // TODO
        },
    },
);
