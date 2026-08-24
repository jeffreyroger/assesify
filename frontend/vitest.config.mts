import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
    plugins: [react()],
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: ["./vitest.setup.ts"],
        css: true,
        exclude: ["node_modules/**", ".next/**"],
        coverage: {
            provider: "v8",
            reporter: ["text", "json-summary"],
            // Application source only: generated types, config, and test
            // scaffolding would otherwise skew the spec §10 (>=75%) number.
            include: ["app/**/*.{ts,tsx}", "components/**/*.{ts,tsx}", "lib/**/*.{ts,tsx}"],
            exclude: [
                "**/__tests__/**",
                "lib/api-types.ts",
                "app/**/layout.tsx",
                "app/**/globals.css",
            ],
        },
    },
    resolve: {
        alias: {
            "@": path.resolve(import.meta.dirname, "./"),
        },
    },
});
