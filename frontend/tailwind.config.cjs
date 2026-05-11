/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4ff',
          100: '#dbe7ff',
          200: '#b9cfff',
          300: '#89adff',
          400: '#5f89ff',
          500: '#4172ff',
          600: '#3157dc',
          700: '#2844b4',
          800: '#243a92',
          900: '#23357a'
        },
        accent: {
          500: '#00c6ff',
          600: '#00a4d4'
        },
        navy: {
          50: '#f4f7fe',
          100: '#e9eefc',
          200: '#d4ddf7',
          300: '#b3c1ec',
          400: '#8697c4',
          500: '#707eae',
          600: '#5b688f',
          700: '#4a5568',
          800: '#2b3674',
          900: '#1b2559'
        },
        secondaryGray: {
          50: '#f8f9fd',
          100: '#f1f4f9',
          200: '#e9edf7',
          300: '#dfe6f1',
          400: '#c4cfde',
          500: '#a3aed0',
          600: '#8f9bba',
          700: '#707eae',
          800: '#2b3674',
          900: '#1b2559'
        }
      },
      borderRadius: {
        '4xl': '2rem'
      },
      boxShadow: {
        card: '0px 18px 40px rgba(112, 144, 176, 0.12)',
        panel: '0px 20px 44px rgba(112, 144, 176, 0.16)',
        glow: '0px 16px 32px rgba(65, 114, 255, 0.24)',
        'glow-accent': '0px 8px 32px rgba(34, 211, 238, 0.22)',
        'glow-success': '0px 8px 32px rgba(34, 197, 94, 0.22)',
        'glow-danger': '0px 8px 32px rgba(239, 68, 68, 0.22)'
      },
      backgroundImage: {
        'hero-grid':
          'radial-gradient(circle at top right, rgba(65, 114, 255, 0.16), transparent 24%), radial-gradient(circle at bottom left, rgba(0, 198, 255, 0.12), transparent 24%)'
      }
    }
  },
  plugins: []
};
