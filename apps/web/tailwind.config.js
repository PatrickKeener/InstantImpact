/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0b0c10",
          900: "#11131a",
          800: "#1a1d27",
          700: "#252a38",
        },
        accent: {
          DEFAULT: "#8b5cf6",
          soft: "#a78bfa",
          muted: "#6d28d9",
        },
      },
      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
