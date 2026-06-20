/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// @fontsource-variable/inter ships CSS only (no type declarations).
declare module "@fontsource-variable/inter";
