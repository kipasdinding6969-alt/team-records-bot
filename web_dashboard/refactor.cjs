const fs = require('fs');
const path = require('path');

const dir = '/home/baiwan/team-records-bot/web_dashboard/src/pages';
const files = fs.readdirSync(dir).filter(f => f.endsWith('.tsx'));

const colorMap = {
  '#1a1a2e': 'theme.bg',
  '#16213e': 'theme.cardBg',
  '#0f3460': 'theme.cardBorder',
  '#e0e0e0': 'theme.textPrimary',
  '#7f848e': 'theme.textSecondary',
  '#00b894': 'theme.accent',
  '#00d2a4': 'theme.accentHover',
  '#fdcb6e': 'theme.chartLine',
  '#00b89433': 'theme.badgeGreen',
  '#fdcb6e33': 'theme.badgeYellow',
  '#d6303133': 'theme.badgeRed',
  '#ff7675': 'theme.badgeRed',
  '#2d1515': 'theme.badgeRed',
  '#00cec9': 'theme.accent',
};

files.forEach(file => {
  const filepath = path.join(dir, file);
  let content = fs.readFileSync(filepath, 'utf-8');
  let original = content;

  // Add the useTheme hook and import first, so we know `theme.` is available
  if (!content.includes('useTheme') && !content.includes('ThemeContext')) {
    const importMatches = [...content.matchAll(/^import .*?from\s+['"].*?['"]/gm)];
    if (importMatches.length > 0) {
      const lastMatch = importMatches[importMatches.length - 1];
      const insertPos = lastMatch.index + lastMatch[0].length;
      content = content.slice(0, insertPos) + "\nimport { useTheme } from '../ThemeContext'" + content.slice(insertPos);
    } else {
      content = "import { useTheme } from '../ThemeContext'\n" + content;
    }
  }

  // Find standard function component to insert hook
  let addedHook = false;
  content = content.replace(/(export\s+(?:default\s+)?function\s+[A-Z][a-zA-Z0-9_]*\s*\([^{]*\)\s*\{\n)/, (match, funcDef) => {
    if (!content.includes('const { theme } = useTheme()')) {
      addedHook = true;
      return `${funcDef}  const { theme } = useTheme()\n`;
    }
    return match;
  });

  // Regex replacement for hex colors:
  
  // 1. Direct properties e.g., background: '#1a1a2e' -> background: theme.bg
  content = content.replace(/:\s*(['"])(#[0-9a-fA-F]{6,8})\1/gi, (match, quote, hex) => {
    const lHex = hex.toLowerCase();
    if (colorMap[lHex]) {
      return `: ${colorMap[lHex]}`;
    }
    return match;
  });

  // 2. Mixed values in object properties: border: '1px solid #0f3460' -> border: `1px solid ${theme.cardBorder}`
  content = content.replace(/:\s*(['"])([^'"]*?#[0-9a-fA-F]{6,8}[^'"]*?)\1/gi, (match, quote, inner) => {
    let replaced = false;
    for (const [hex, themeProp] of Object.entries(colorMap)) {
      const re = new RegExp(hex, 'gi');
      if (re.test(inner)) {
        inner = inner.replace(re, `\${${themeProp}}`);
        replaced = true;
      }
    }
    if (replaced) {
      return `: \`${inner}\``;
    }
    return match;
  });

  // 3. Template literals: `1px solid #0f3460` -> `1px solid ${theme.cardBorder}`
  content = content.replace(/`([^`]*?#[0-9a-fA-F]{6,8}[^`]*?)`/gi, (match, inner) => {
    let replaced = false;
    for (const [hex, themeProp] of Object.entries(colorMap)) {
      const re = new RegExp(hex, 'gi');
      if (re.test(inner)) {
        inner = inner.replace(re, `\${${themeProp}}`);
        replaced = true;
      }
    }
    if (replaced) {
      return `\`${inner}\``;
    }
    return match;
  });
  
  // 4. Props like accent="#00b894" -> accent={theme.accent}
  content = content.replace(/=([\'"])(#[0-9a-fA-F]{6,8})\1/gi, (match, quote, hex) => {
    const lHex = hex.toLowerCase();
    if (colorMap[lHex]) {
      return `={${colorMap[lHex]}}`;
    }
    return match;
  });

  // 5. Props with mixed values like stroke="#0f3460" -> stroke={theme.cardBorder}
  content = content.replace(/=([\'"])([^'"]*?#[0-9a-fA-F]{6,8}[^'"]*?)\1/gi, (match, quote, inner) => {
    let replaced = false;
    for (const [hex, themeProp] of Object.entries(colorMap)) {
      const re = new RegExp(hex, 'gi');
      if (re.test(inner)) {
        inner = inner.replace(re, `\${${themeProp}}`);
        replaced = true;
      }
    }
    if (replaced) {
      return `={\`${inner}\`}`;
    }
    return match;
  });

  if (content !== original) {
    fs.writeFileSync(filepath, content);
    console.log('Refactored', file);
  } else {
    // If we only added the hook but no colors were replaced, maybe revert the hook?
    if (addedHook && !original.includes('const { theme } = useTheme()') && !original.includes('theme.')) {
      fs.writeFileSync(filepath, original);
    }
  }
});
