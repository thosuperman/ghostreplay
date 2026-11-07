import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const SUPPORT = process.env.GHOSTREPLAY_SUPPORT_URL ?? "http://127.0.0.1:8101";
const DEVOPS = process.env.GHOSTREPLAY_DEVOPS_URL ?? "http://127.0.0.1:8102";

const proxy = {
  "/lab/support": { target: SUPPORT, changeOrigin: true, rewrite: (p: string) => p.replace(/^\/lab\/support/, "") },
  "/lab/devops": { target: DEVOPS, changeOrigin: true, rewrite: (p: string) => p.replace(/^\/lab\/devops/, "") },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { host: "127.0.0.1", port: 5173, proxy },
  preview: { host: "127.0.0.1", port: 4173, proxy },
});
