import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'data']),

  // 服务端与构建脚本跑在 Node 里：需要 process / Buffer / __dirname 等全局，
  // 且不适用 React 相关规则（原先只声明了浏览器全局，导致这些文件误报 no-undef）
  {
    files: ['server/**/*.js', 'scripts/**/*.{js,mjs}', '*.config.js'],
    extends: [js.configs.recommended],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: globals.node,
      parserOptions: { sourceType: 'module' },
    },
    rules: {
      // Express 的错误处理中间件签名必须是 4 个参数，末位 next 常不使用
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^[A-Z_]' }],
    },
  },

  {
    files: ['src/**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    rules: {
      // varsIgnorePattern 只作用于变量声明，不含解构出来的参数，
      // 所以 ({ icon: Icon }) 这种组件 prop 会被误报（JSX 里其实用了 <Icon />）。
      // 加上 destructuredArrayIgnorePattern 与 argsIgnorePattern 覆盖这两类。
      'no-unused-vars': [
        'error',
        {
          varsIgnorePattern: '^[A-Z_]',
          args: 'after-used',
          argsIgnorePattern: '^(_|[A-Z])',
          destructuredArrayIgnorePattern: '^_',
          caughtErrors: 'none',
        },
      ],
    },
  },
])
