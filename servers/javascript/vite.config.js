/// <reference types="vitest/config" />
/// <reference types="@vitest/browser/providers/playwright" />
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const datasetJsRoot = path.resolve(__dirname, "../../dataset/server/dbs/js");
const datasetBlobRoot = path.resolve(__dirname, "../../dataset/server/blobs");

function serveDatasetRoot(root) {
    return (req, res, next) => {
        const rel = decodeURIComponent((req.url ?? "/").split("?")[0]);
        const filePath = path.resolve(root, "." + rel);
        if (!filePath.startsWith(root + path.sep) && filePath !== root) {
            res.statusCode = 403;
            res.end("Forbidden");
            return;
        }
        fs.readFile(filePath, (err, data) => {
            if (err) {
                next();
                return;
            }
            if (filePath.endsWith(".json") || filePath.endsWith(".jsonl")) {
                res.setHeader("Content-Type", "application/json");
            }
            res.end(data);
        });
    };
}

export default defineConfig({
    server: {
        fs: {
            allow: [path.resolve(__dirname, "../..")],
        },
    },
    plugins: [
        {
            name: "local-datasets",
            configureServer(server) {
                server.middlewares.use("/local-dataset", serveDatasetRoot(datasetJsRoot));
                server.middlewares.use("/local-blobs", serveDatasetRoot(datasetBlobRoot));
            },
        },
    ],
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
