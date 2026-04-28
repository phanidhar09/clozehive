/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#EEEDFE',
          100: '#D9D8FC',
          200: '#B8B5F9',
          300: '#9793F5',
          400: '#7670F1',
          500: '#6760E8',
          600: '#534AB7',
          700: '#3C3489',
          800: '#2A2460',
          900: '#18143A',
        },
        cream: {
          50:  '#FAFAF7',
          100: '#F5F4F0',
          200: '#EEECe5',
          300: '#E0DED8',
          400: '#C8C5BC',
        },
      },
      fontFamily: {
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
        display: ['"Sora"', '"Inter"', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / .06), 0 4px 16px -2px rgb(0 0 0 / .07)',
        'card-hover': '0 4px 12px 0 rgb(0 0 0 / .08), 0 12px 32px -4px rgb(0 0 0 / .12)',
        glass: 'inset 0 1px 0 0 rgb(255 255 255 / .15)',
      },
      backgroundImage: {
        'gradient-brand': 'linear-gradient(135deg, #534AB7 0%, #7670F1 100%)',
        'gradient-warm': 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
        'gradient-fresh': 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
        'gradient-card': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      },
      animation: {
        'fade-in': 'fadeIn .25s ease',
        'slide-up': 'slideUp .3s cubic-bezier(.16,1,.3,1)',
        'slide-in': 'slideIn .3s cubic-bezier(.16,1,.3,1)',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        fadeIn:    { from: { opacity: '0' },                           to: { opacity: '1' } },
        slideUp:   { from: { opacity: '0', transform: 'translateY(16px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideIn:   { from: { opacity: '0', transform: 'translateX(-16px)' }, to: { opacity: '1', transform: 'translateX(0)' } },
        pulseSoft: { '0%,100%': { opacity: '1' }, '50%': { opacity: '.5' } },
      },
    },
  },
  plugins: [],
}
