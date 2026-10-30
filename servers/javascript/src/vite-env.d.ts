interface ViteTypeOptions {
    strictImportMetaEnv: unknown;
}

interface ImportMetaEnv {
    readonly VITE_ENCRYPTED_DBS?: string;
    readonly VITE_DATASET_BASE_URL?: string;
    readonly VITE_BLOB_BASE_URL?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
