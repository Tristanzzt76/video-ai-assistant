/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: '#0f1117',
        panel: '#1a1d27',
        border: '#2a2d3a',
        accent: '#6366f1',
      },
    },
  },
  plugins: [],
}
