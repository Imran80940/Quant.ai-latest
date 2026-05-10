/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        bg2: 'var(--bg2)',
        bg3: 'var(--bg3)',
        border1: 'var(--border)',
        border2: 'var(--border2)',
        text1: 'var(--text)',
        text2: 'var(--text2)',
        text3: 'var(--text3)',
        accent: 'var(--accent)',
        green1: 'var(--green)',
        red1: 'var(--red)',
        amber1: 'var(--amber)',
        purple1: 'var(--purple)',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
