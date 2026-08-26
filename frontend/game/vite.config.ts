import { defineConfig } from "vite";

export default defineConfig({
  base: "/miniapp-assets/",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
    // Phaser is intentionally a large, stable runtime. Keep it in its own
    // cacheable vendor chunk so normal app updates do not invalidate it.
    chunkSizeWarningLimit: 1_300,
    rollupOptions: {
      output: {
        manualChunks: {
          phaser: ["phaser"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5001",
      "/card-images": "http://127.0.0.1:5001",
    },
  },
});
