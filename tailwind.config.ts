import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        sentinel: {
          bg: "#050505",
          panel: "#0a0a0a",
          line: "#153824",
          glow: "#00ff88",
          amber: "#f59e0b",
          red: "#ef4444"
        }
      },
      boxShadow: {
        terminal: "0 0 0 1px rgba(0,255,136,0.16), 0 24px 80px rgba(0,0,0,0.55)"
      },
      keyframes: {
        "scan-line": {
          "0%": { top: "0%" },
          "100%": { top: "100%" }
        },
        blink: {
          "0%, 100%": { opacity: "0.2" },
          "50%": { opacity: "1" }
        }
      },
      animation: {
        "scan-line": "scan-line 4s linear infinite",
        blink: "blink 1.25s step-end infinite"
      }
    }
  },
  plugins: []
};

export default config;
