/// <reference types="vite/client" />

// Music files imported from the repo-level music/ folder (spec 5).
declare module "*.ogg?url" {
  const src: string;
  export default src;
}
