/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        gh: {
          canvas: "#0d1117",
          "canvas-subtle": "#161b22",
          "canvas-inset": "#010409",
          border: "#30363d",
          "border-muted": "#21262d",
          text: "#c9d1d9",
          "text-muted": "#8b949e",
          "text-secondary": "#6e7681",
          accent: "#58a6ff",
          "accent-muted": "#1f6feb33",
          success: "#3fb950",
          danger: "#f85149",
          warning: "#d29922",
          purple: "#a371f7",
          pink: "#db61a2",
          orange: "#f0883e",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Noto Sans",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "SF Mono", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
