interface ViteTypeOptions {
    strictImportMetaEnv: unknown
}

interface ImportMetaEnv {
    readonly VITE_ENCRYPTED_DBS?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}