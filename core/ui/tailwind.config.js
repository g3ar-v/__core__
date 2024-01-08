/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./src/**/*.{html,js,svelte,ts}"],
  theme: {
    extend: {
      colors: {
        gray: {
          50: "#f2f2f2",
          100: "#E3E3E3",
          200: "#C9C9C9",
          300: "#c5c5d2",
          400: "#acacbe",
          500: "#787878",
          600: "#5E5E5E",
          700: "#424242",
          800: "#282828",
          900: "#141414",
          950: "#0a0a0a",
        },
        red: {
          500: "#b1492d",
        },
      },
      typography: {
        DEFAULT: {
          css: {
            pre: false,
            code: false,
            "pre code": false,
            "code::before": false,
            "code::after": false,
          },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
