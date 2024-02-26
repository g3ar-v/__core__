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
          300: "#949494",
          400: "#828282",
          500: "#787878",
          600: "#5E5E5E",
          700: "#424242",
          800: "#282828",
          900: "#141414",
          950: "#0a0a0a",
        },
        red: {
          50: "#FBE9E5",
          100: "#F9E1DC",
          200: "#F5CBC2",
          300: "#F1B9AC",
          400: "#ECA392",
          500: "#E88D78",
          600: "#E47A62",
          700: "#E06448",
          800: "#DC5132",
          900: "#CD4223",
          950: "#C13F21",
        },
        blue: {
          950: "#659cc8",
        },
        green: {
          50: "#F5F9F8",
          100: "#ECF4F1",
          200: "#D9E8E4",
          300: "#C5DDD6",
          400: "#B2D1C9",
          500: "#9FC6BB",
          600: "#8CBBAD",
          700: "#78AF9F",
          800: "#4A7D6E",
          900: "#243D36",
          950: "#13201C",
        },
        orange: {
          950: "#d36e2d",
        },
        yellow: {
          950: "#dda032",
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
