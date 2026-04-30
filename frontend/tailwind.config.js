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
        // Premium surface tokens (dark-mode glass system)
        surface: {
          0:  'rgba(255,255,255,0.02)',
          1:  'rgba(255,255,255,0.04)',
          2:  'rgba(255,255,255,0.07)',
          3:  'rgba(255,255,255,0.10)',
        },
      },
      fontFamily: {
        sans: ['"Inter"', 'system-ui', 'sans-serif'],
        display: ['"Sora"', '"Inter"', 'sans-serif'],
      },
      boxShadow: {
        // Light-mode cards
        card:       '0 1px 3px 0 rgb(0 0 0 / .06), 0 4px 16px -2px rgb(0 0 0 / .07)',
        'card-hover':'0 4px 12px 0 rgb(0 0 0 / .08), 0 12px 32px -4px rgb(0 0 0 / .12)',
        glass:      'inset 0 1px 0 0 rgb(255 255 255 / .08)',
        // Glow shadows
        'glow-sm':  '0 0 12px rgba(99,102,241,0.35)',
        'glow-md':  '0 0 24px rgba(99,102,241,0.40), 0 0 8px rgba(124,58,237,0.25)',
        'glow-lg':  '0 0 40px rgba(99,102,241,0.45), 0 0 16px rgba(124,58,237,0.30)',
        'glow-cyan':'0 0 24px rgba(6,182,212,0.40)',
        // Dark glass card shadow
        'glass-card':'inset 0 1px 0 rgba(255,255,255,0.08), 0 4px 32px -4px rgba(0,0,0,0.5)',
        'glass-card-hover':'inset 0 1px 0 rgba(255,255,255,0.12), 0 0 0 1px rgba(99,102,241,0.25), 0 8px 40px -8px rgba(99,102,241,0.30), 0 4px 32px -4px rgba(0,0,0,0.6)',
      },
      backgroundImage: {
        'gradient-brand':  'linear-gradient(135deg, #534AB7 0%, #7670F1 100%)',
        'gradient-premium':'linear-gradient(135deg, #6366f1 0%, #7c3aed 50%, #06b6d4 100%)',
        'gradient-warm':   'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
        'gradient-fresh':  'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
        'gradient-card':   'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        // Shimmer for loading states
        'shimmer': 'linear-gradient(90deg, transparent, rgba(255,255,255,0.08), transparent)',
      },
      animation: {
        'fade-in':       'fadeIn .25s ease',
        'slide-up':      'slideUp .35s cubic-bezier(.16,1,.3,1)',
        'slide-in':      'slideIn .35s cubic-bezier(.16,1,.3,1)',
        'pulse-soft':    'pulseSoft 2s ease-in-out infinite',
        'spin-slow':     'spin 3s linear infinite',
        'spin-ring':     'spin 8s linear infinite',
        'spin-ring-rev': 'spinRev 5s linear infinite',
        // Background orbs
        'float-1':       'float1 22s ease-in-out infinite',
        'float-2':       'float2 28s ease-in-out infinite',
        'float-3':       'float3 19s ease-in-out infinite',
        // UI interactions
        'glow-pulse':    'glowPulse 2.5s ease-in-out infinite',
        'shimmer':       'shimmer 2.2s linear infinite',
        'stagger-in':    'slideUp .4s cubic-bezier(.16,1,.3,1) both',
      },
      keyframes: {
        fadeIn:    { from: { opacity: '0' },                              to: { opacity: '1' } },
        slideUp:   { from: { opacity: '0', transform: 'translateY(18px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
        slideIn:   { from: { opacity: '0', transform: 'translateX(-18px)' }, to: { opacity: '1', transform: 'translateX(0)' } },
        pulseSoft: { '0%,100%': { opacity: '1' }, '50%': { opacity: '.5' } },
        spinRev:   { from: { transform: 'rotate(360deg)' }, to: { transform: 'rotate(0deg)' } },
        // Slow-drifting background orbs
        float1: {
          '0%,100%': { transform: 'translate(0,0) scale(1)' },
          '33%':     { transform: 'translate(80px,-60px) scale(1.06)' },
          '66%':     { transform: 'translate(-60px,80px) scale(0.94)' },
        },
        float2: {
          '0%,100%': { transform: 'translate(0,0) scale(1)' },
          '40%':     { transform: 'translate(-90px,-70px) scale(1.08)' },
          '75%':     { transform: 'translate(60px,50px) scale(0.96)' },
        },
        float3: {
          '0%,100%': { transform: 'translate(0,0) scale(1)' },
          '30%':     { transform: 'translate(70px,80px) scale(0.92)' },
          '65%':     { transform: 'translate(-80px,-50px) scale(1.05)' },
        },
        glowPulse: {
          '0%,100%': { boxShadow: '0 0 20px rgba(99,102,241,0.35)' },
          '50%':     { boxShadow: '0 0 35px rgba(99,102,241,0.60), 0 0 12px rgba(124,58,237,0.40)' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
      },
    },
  },
  plugins: [],
}
