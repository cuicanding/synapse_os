/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{svelte,js,ts}"],
  theme: {
    extend: {
      colors: {
        cyber: {
          cyan: "#00E5FF",
          violet: "#7C3AED",
          amber: "#FFB800",
          green: "#00FF88",
          red: "#FF3860",
        },
        bg: {
          deep: "#0A0E1A",
          mid: "#111827",
          light: "#1E293B",
        },
        txt: {
          primary: "#F0F9FF",
          secondary: "#94A3B8",
        },
      },
      fontFamily: {
        orbitron: ["Orbitron", "sans-serif"],
        rajdhani: ["Rajdhani", "sans-serif"],
        inter: ["Inter", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
        chinese: ["Noto Sans SC", "sans-serif"],
      },
      boxShadow: {
        cyan: "0 0 20px rgba(0, 229, 255, 0.3)",
        violet: "0 0 20px rgba(124, 58, 237, 0.3)",
        "cyan-lg": "0 0 40px rgba(0, 229, 255, 0.5)",
      },
    },
  },
  plugins: [],
};
