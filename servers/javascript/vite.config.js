/// <reference types="vitest/config" />
/// <reference types="@vitest/browser/providers/playwright" />
import { defineConfig } from "vite";

export default defineConfig({
    test: {
        // https://vitest.dev/config/
        include: ["src/**/*.test.ts"],
        browser: {
            instances: [{
                name: "chromium",
                browser: "chromium",
                headless: true,
            }],
            provider: "playwright"
        }
    },
});
