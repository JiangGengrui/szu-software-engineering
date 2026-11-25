export default [
  { ignores: ['node_modules/**', '.qoder/**', '.archify/**', '.venv/**', '**/*.ts'] },
  {
    files: ['**/*.js', '**/*.cjs', '**/*.mjs'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        wx: 'readonly', App: 'readonly', Page: 'readonly', Component: 'readonly',
        getApp: 'readonly', getCurrentPages: 'readonly', console: 'readonly',
        setTimeout: 'readonly', clearTimeout: 'readonly', setInterval: 'readonly',
        clearInterval: 'readonly', process: 'readonly', Buffer: 'readonly',
        URL: 'readonly', structuredClone: 'readonly'
      }
    },
    rules: {
      'no-undef': 'error',
      'no-duplicate-case': 'error',
      'no-dupe-args': 'error',
      'no-dupe-keys': 'error',
      'no-unreachable': 'error',
      'valid-typeof': 'error',
      'constructor-super': 'error'
    }
  },
  { files: ['backend/album/static/**/*.js'], languageOptions: { globals: { document: 'readonly', window: 'readonly' } } },
  { files: ['**/*.cjs'], languageOptions: { globals: { __dirname: 'readonly', __filename: 'readonly' } } },
  { files: ['**/*.mjs'], languageOptions: { sourceType: 'module' } }
];
