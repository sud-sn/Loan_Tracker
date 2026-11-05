import containerQueries from "@tailwindcss/container-queries";

/** Design tokens live in src/index.css as CSS variables; Tailwind only maps names to them. */
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        sunken: "rgb(var(--sunken) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        brand: { DEFAULT: "rgb(var(--brand) / <alpha-value>)", ink: "rgb(var(--brand-ink) / <alpha-value>)",
                 soft: "rgb(var(--brand-soft) / <alpha-value>)" },
        paid: { DEFAULT: "rgb(var(--paid) / <alpha-value>)", soft: "rgb(var(--paid-soft) / <alpha-value>)" },
        due: { DEFAULT: "rgb(var(--due) / <alpha-value>)", soft: "rgb(var(--due-soft) / <alpha-value>)" },
        late: { DEFAULT: "rgb(var(--late) / <alpha-value>)", soft: "rgb(var(--late-soft) / <alpha-value>)" },
        moneyin: "rgb(var(--money-in) / <alpha-value>)",
        moneyout: "rgb(var(--money-out) / <alpha-value>)",
      },
      fontFamily: { sans: ['"Noto Sans"', '"Noto Sans Tamil"', "system-ui", "sans-serif"] },
      borderRadius: { xl: "var(--radius)", "2xl": "calc(var(--radius) + 4px)" },
      minHeight: { touch: "48px" },
      minWidth: { touch: "48px" },
      boxShadow: { card: "0 1px 2px rgb(var(--shadow) / 0.06), 0 2px 8px rgb(var(--shadow) / 0.05)" },
    },
  },
  // Container queries: panels adapt to the space they actually get, not only to the window size.
  plugins: [containerQueries],
};
