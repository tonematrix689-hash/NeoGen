import fs from 'node:fs/promises';
import path from 'node:path';

const SKIP_DIRS = new Set(['.git','node_modules','.next','dist','build','coverage','.cache']);
const TEXT_EXTENSIONS = new Set(['.js','.mjs','.cjs','.ts','.tsx','.jsx','.json','.md','.html','.css','.scss','.py','.rs','.go','.java','.c','.h','.cpp','.hpp','.sh','.yml','.yaml','.toml','.xml','.sql']);

const LANGUAGE_BY_EXTENSION = {
  '.js':'JavaScript','.mjs':'JavaScript','.cjs':'JavaScript','.jsx':'JavaScript',
  '.ts':'TypeScript','.tsx':'TypeScript','.json':'JSON','.md':'Markdown',
  '.html':'HTML','.css':'CSS','.scss':'SCSS','.py':'Python','.rs':'Rust',
  '.go':'Go','.java':'Java','.c':'C','.h':'C/C++ Header','.cpp':'C++','.hpp':'C++ Header',
  '.sh':'Shell','.yml':'YAML','.yaml':'YAML','.toml':'TOML','.xml':'XML','.sql':'SQL'
};

async function walk(root, current = root, output = []) {
  const entries = await fs.readdir(current, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isDirectory() && SKIP_DIRS.has(entry.name)) continue;
    const absolute = path.join(current, entry.name);
    if (entry.isDirectory()) await walk(root, absolute, output);
    else output.push(path.relative(root, absolute));
  }
  return output;
}

function extractImports(content, extension) {
  const imports = new Set();
  const patterns = extension === '.py'
    ? [/^\s*import\s+([\w.]+)/gm, /^\s*from\s+([\w.]+)\s+import/gm]
    : [/\bfrom\s+['"]([^'"]+)['"]/g, /\brequire\(\s*['"]([^'"]+)['"]\s*\)/g, /\bimport\(\s*['"]([^'"]+)['"]\s*\)/g];
  for (const pattern of patterns) {
    for (const match of content.matchAll(pattern)) imports.add(match[1]);
  }
  return [...imports];
}

function extractSymbols(content, extension) {
  const symbols = [];
  const patterns = extension === '.py'
    ? [
        { type: 'function', regex: /^\s*def\s+([A-Za-z_]\w*)\s*\(/gm },
        { type: 'class', regex: /^\s*class\s+([A-Za-z_]\w*)/gm }
      ]
    : [
        { type: 'function', regex: /\bfunction\s+([A-Za-z_$][\w$]*)\s*\(/g },
        { type: 'class', regex: /\bclass\s+([A-Za-z_$][\w$]*)/g },
        { type: 'function', regex: /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>/g }
      ];
  for (const { type, regex } of patterns) {
    for (const match of content.matchAll(regex)) symbols.push({ type, name: match[1] });
  }
  return symbols;
}

function detectFrameworks(files, packageJson) {
  const frameworks = new Set();
  const dependencies = { ...(packageJson?.dependencies || {}), ...(packageJson?.devDependencies || {}) };
  const names = Object.keys(dependencies);
  const checks = {
    React: ['react'], Next.js: ['next'], Vue: ['vue'], Express: ['express'], Vite: ['vite'],
    Jest: ['jest'], Vitest: ['vitest'], TypeScript: ['typescript'], Tailwind: ['tailwindcss']
  };
  for (const [framework, packages] of Object.entries(checks)) {
    if (packages.some((pkg) => names.includes(pkg))) frameworks.add(framework);
  }
  if (files.includes('server.js') && !frameworks.has('Express')) frameworks.add('Node.js HTTP');
  return [...frameworks];
}

export async function buildRepositoryIndex(root) {
  const filePaths = await walk(root);
  const files = [];
  const languageCounts = {};
  let packageJson = null;

  for (const relativePath of filePaths) {
    const extension = path.extname(relativePath).toLowerCase();
    const stat = await fs.stat(path.join(root, relativePath));
    const record = { path: relativePath, extension, size: stat.size, language: LANGUAGE_BY_EXTENSION[extension] || 'Other', imports: [], symbols: [] };
    languageCounts[record.language] = (languageCounts[record.language] || 0) + 1;

    if (TEXT_EXTENSIONS.has(extension) && stat.size <= 500000) {
      try {
        const content = await fs.readFile(path.join(root, relativePath), 'utf8');
        record.imports = extractImports(content, extension);
        record.symbols = extractSymbols(content, extension);
        record.searchText = `${relativePath}\n${content}`.toLowerCase();
        if (relativePath === 'package.json') packageJson = JSON.parse(content);
      } catch {
        record.searchText = relativePath.toLowerCase();
      }
    } else {
      record.searchText = relativePath.toLowerCase();
    }
    files.push(record);
  }

  const symbols = files.flatMap((file) => file.symbols.map((symbol) => ({ ...symbol, path: file.path })));
  const imports = files.flatMap((file) => file.imports.map((target) => ({ path: file.path, target })));

  return {
    generatedAt: new Date().toISOString(),
    root,
    summary: {
      fileCount: files.length,
      totalBytes: files.reduce((sum, file) => sum + file.size, 0),
      languages: Object.entries(languageCounts).sort((a, b) => b[1] - a[1]).map(([language, count]) => ({ language, count })),
      frameworks: detectFrameworks(filePaths, packageJson),
      symbolCount: symbols.length,
      importCount: imports.length
    },
    files,
    symbols,
    imports
  };
}

export function searchRepositoryIndex(index, query, limit = 50) {
  const terms = String(query || '').toLowerCase().trim().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  return index.files
    .map((file) => ({ file, score: terms.reduce((score, term) => score + (file.searchText?.includes(term) ? 1 : 0), 0) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.file.path.localeCompare(b.file.path))
    .slice(0, limit)
    .map(({ file, score }) => ({ path: file.path, language: file.language, size: file.size, symbols: file.symbols, imports: file.imports, score }));
}
