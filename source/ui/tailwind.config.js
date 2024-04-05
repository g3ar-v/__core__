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
          700: "#82ad9f",
          800: "#3d6f71",
          950: "#659cc8",
        },
        green: {
          50: "#FAFBEA",
          100: "#F4F5CC",
          200: "#E8E995",
          300: "#DADC56",
          400: "#C9CB29",
          500: "#65D46E",
          600: "#A7A923",
          700: "#92941E",
          800: "#797B19",
          900: "#585912",
          950: "#3F400D",
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
