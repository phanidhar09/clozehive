/// <reference types="vite/client" />
/// <reference types="vitest/globals" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string
  readonly VITE_HIDE_NON_MVP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
