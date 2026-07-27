import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// All-in-one on nemesis: bind 0.0.0.0 so chamber (or any LAN client) can open the UI.
// Override API proxy target with VITE_API_PROXY if needed.
const apiTarget = process.env.VITE_API_PROXY || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": apiTarget,
    },
  },
});
