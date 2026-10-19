/// <reference types="vitest/config" />
/// <reference types="@vitest/browser/providers/playwright" />
import { closeSync, createReadStream, existsSync, openSync, readdirSync, readSync } from "node:fs";
import { stat } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const kServerRoot = dirname(fileURLToPath(import.meta.url));

const kMimeTypes = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".zip": "application/zip",
};

/** Searches upward from `start` for the repo's `dataset/server` tree.
 *
 *  This server runs both from `servers/javascript/` in a checkout and from
 *  `servers/downloaded/js/<version>/` once the orchestrator has installed it, so the
 *  depth to the repo root varies.
 */
function findFixtureRoot(start) {
    for (let dir = start; ; ) {
        const candidate = join(dir, "dataset", "server");
        if (existsSync(join(candidate, "dbs", "js")) && existsSync(join(candidate, "blobs"))) return candidate;
        const parent = dirname(dir);
        if (parent === dir) return undefined;
        dir = parent;
    }
}

/** True if `dir` holds real blob content rather than unfetched Git LFS pointers.
 *
 *  Blobs are LFS-tracked (see .gitattributes); a clone made without LFS leaves ~130 byte
 *  text stubs in their place, which would otherwise be served as though they were the
 *  images themselves.  Datasets are plain text and never need this check.
 */
function hasRealBlobs(dir) {
    let fd;
    try {
        const names = readdirSync(dir).filter((name) => !name.startsWith("."));
        if (names.length === 0) return false;
        fd = openSync(join(dir, names[0]), "r");
        const header = Buffer.alloc(64);
        const read = readSync(fd, header, 0, header.length, 0);
        return !header.subarray(0, read).toString("utf8").startsWith("version https://git-lfs.github.com/spec/v1");
    } catch {
        return false;
    } finally {
        if (fd !== undefined) closeSync(fd);
    }
}

/** Serves the repo's dataset and blob fixtures, so tests do not depend on GitHub. */
function serveFixtures(mounts) {
    return {
        name: "tdk-serve-fixtures",
        configureServer(server) {
            server.middlewares.use((req, res, next) => {
                const url = new URL(req.url ?? "/", "http://localhost");
                const mount = mounts.find((m) => url.pathname.startsWith(m.prefix));
                if (!mount) return next();

                const file = resolve(mount.dir, decodeURIComponent(url.pathname.slice(mount.prefix.length)));
                // Refuse anything that escapes the mount, e.g. via "..".
                const within = relative(mount.dir, file);
                if (within.startsWith("..") || resolve(mount.dir, within) !== file) {
                    res.statusCode = 403;
                    return res.end("Forbidden");
                }

                stat(file).then(
                    (info) => {
                        if (!info.isFile()) {
                            res.statusCode = 404;
                            return res.end("Not Found");
                        }
                        const ext = file.slice(file.lastIndexOf("."));
                        res.setHeader("Content-Type", kMimeTypes[ext] ?? "application/octet-stream");
                        res.setHeader("Content-Length", info.size);
                        const stream = createReadStream(file);
                        // Without these the dev server dies on a mid-read failure: pipe()
                        // re-emits the error with no listener attached, which is fatal.
                        stream.on("error", () => {
                            if (res.headersSent) res.destroy();
                            else {
                                res.statusCode = 500;
                                res.end("Read Error");
                            }
                        });
                        res.on("close", () => stream.destroy());
                        stream.pipe(res);
                    },
                    () => {
                        res.statusCode = 404;
                        res.end("Not Found");
                    },
                );
            });
        },
    };
}

const fixtureRoot = findFixtureRoot(kServerRoot);
const plugins = [];
const datasetBaseURL = "/datasets/";
const blobBaseURL = "/blobs/";

if (fixtureRoot) {
    // Vite exposes VITE_-prefixed process.env entries on import.meta.env.  ??= so an
    // explicitly supplied URL still wins over the local checkout.
    process.env.VITE_DATASET_BASE_URL ??= datasetBaseURL;
    const mounts = [{ prefix: datasetBaseURL, dir: join(fixtureRoot, "dbs", "js") }];

    const blobDir = join(fixtureRoot, "blobs");
    if (hasRealBlobs(blobDir)) {
        process.env.VITE_BLOB_BASE_URL ??= blobBaseURL;
        mounts.push({ prefix: blobBaseURL, dir: blobDir });
    } else {
        console.warn(
            "[tdk] dataset/server/blobs holds Git LFS pointers; run `git lfs pull`. Fetching blobs from GitHub.",
        );
    }
    plugins.push(serveFixtures(mounts));
} else {
    console.warn("[tdk] No local dataset/server tree found; falling back to the GitHub fixture URLs.");
}

export default defineConfig({
    plugins,
    test: {
        // https://vitest.dev/config/
        include: ["src/**/*.test.ts"],
        browser: {
            instances: [
                {
                    name: "chromium",
                    browser: "chromium",
                    headless: true,
                },
            ],
            provider: "playwright",
        },
    },
});
