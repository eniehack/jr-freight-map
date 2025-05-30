import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";
import vike from "vike/plugin";

export default defineConfig({
  plugins: [vike(), react({}), tailwindcss()],
  base: process.env.MODE === "production" ? "/jr-freight-map/" : "/",
  build: {
    target: "es2022",
  },
});
