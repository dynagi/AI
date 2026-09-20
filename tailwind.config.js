/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/app/**/*.{ts,tsx}", "./src/components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        positive: "hsl(var(--positive))",
        negative: "hsl(var(--negative))",
        warning: "hsl(var(--warning))",
        // fixed retro palette
        mint: { DEFAULT: "#B8F0CF", accent: "#7FE3B5" },
        lavender: { DEFAULT: "#B79AEF", dark: "#A98BE8", light: "#D9C9F7" },
        cream: "#FFF29A",
        win: { DEFAULT: "#E8E8E8", light: "#F5F5F5" },
      },
      borderRadius: { lg: "0", md: "0", sm: "0" },
      fontFamily: {
        sans: ["var(--font-mono)", "Courier New", "monospace"],
        mono: ["var(--font-mono)", "Courier New", "monospace"],
        pixel: ["var(--font-pixel)", "var(--font-mono)", "monospace"],
        vt: ["var(--font-vt)", "var(--font-mono)", "monospace"],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
