/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: '#14212B', soft: '#3C4B57', mute: '#6B7A85' },
        paper: '#EDF0EC',
        line: '#D3DAD4',
        solar: '#F59E0B',
        wind: '#06B6D4',
        hydro: '#3B82F6',
        battery: '#10B981',
        grid: '#EF4444',
        demand: '#8B5CF6',
      },
      fontFamily: {
        display: ['"Bricolage Grotesque Variable"', 'system-ui', 'sans-serif'],
        sans: ['"Instrument Sans Variable"', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
