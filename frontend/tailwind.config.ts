import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b1020",
        panel: "#111b34",
        card: "#18294d",
        accent: "#29f0ff",
        textMain: "#e6edf7",
        textMuted: "#8ea0bf",
        riskLow: "#67f7c2",
        riskMid: "#ffd166",
        riskHigh: "#ff6b7a"
      }
    }
  },
  plugins: []
};

export default config;
