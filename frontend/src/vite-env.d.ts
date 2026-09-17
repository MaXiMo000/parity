/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend origin for a split-origin deploy (Phase 3c,
   * DEPLOY.md). Unset in local dev -- api.ts falls back to relative
   * `/api/...` paths, resolved by vite.config.ts's dev-server proxy. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
