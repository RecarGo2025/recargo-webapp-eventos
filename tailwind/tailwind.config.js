/** Tailwind: se compila a app/static/vibra.css (sin build step en runtime).
 *  Reconstruir con:  ./scripts/build_css.sh
 *  Tokens del Design System RecarGo x Vibra Perú.               */
module.exports = {
  content: ["./app/templates/**/*.html", "./app/static/app.js"],
  theme: {
    extend: {
      colors: {
        coral: { DEFAULT: "#EF5340", 700: "#D63A28" },
        gold: { DEFAULT: "#F6B01D", 700: "#D68F00" },
        teal: { DEFAULT: "#2E9DA6", 700: "#207880" },
        sky: { DEFAULT: "#26A9E0", 700: "#1785B8" },
        grape: { DEFAULT: "#8C4BA0", 700: "#6E3880" },
        ink: { DEFAULT: "#241611", soft: "#4E3B33", mute: "#8A756B" },
        cream: "#FBF5EA",
        paper: "#FFFFFF",
        line: "#EADFCE",
        success: { DEFAULT: "#2FA968", bg: "#E4F6EC" },
        warn: { DEFAULT: "#F6B01D", bg: "#FDF1D6" },
        danger: { DEFAULT: "#D63A28", bg: "#FBE5E1" },
        info: { DEFAULT: "#26A9E0", bg: "#E1F3FB" },
      },
      fontFamily: {
        display: ['"Monument Extended"', "Archivo", "system-ui", "sans-serif"],
        ui: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        sticker: "4px 4px 0 #241611",
        "sticker-sm": "3px 3px 0 #241611",
        card: "0 6px 18px rgba(36,22,17,.10)",
        pop: "0 10px 26px rgba(36,22,17,.20)",
        glow: "0 0 0 4px rgba(246,176,29,.35)",
      },
      borderRadius: { card: "22px", xl2: "30px" },
    },
  },
  plugins: [],
};
