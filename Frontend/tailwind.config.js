/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#10B981", // Emerald Green Accent
        secondary: "#34D399", // Lighter Emerald
        background: "#121417", // Deep Charcoal
        surface: "#1A1D21", // Slightly lighter charcoal for cards
        silver: "#E2E8F0", // Sleek Silver
        slateMuted: "#64748B", // Muted Slate
      }
    },
  },
  plugins: [],
}
