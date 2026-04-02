const fs = require('fs');
const path = require('path');

function processDir(dir) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    if (fs.statSync(fullPath).isDirectory()) {
      processDir(fullPath);
    } else if (fullPath.endsWith('.tsx')) {
      let content = fs.readFileSync(fullPath, 'utf8');
      let changed = false;

      // Replace hardcoded light theme colors that slipped in or weren't caught
      const replacements = {
        "'#ffffff'": "theme.cardBg",
        "'#f8fafc'": "theme.inputBg",
        "'#e2e8f0'": "theme.cardBorder",
        "'#2d2a26'": "theme.textPrimary",
        "'#3b82f6'": "theme.accent",
        "'#22c55e'": "theme.badgeGreen",
        "'#3b82f620'": "theme.badgeYellow",
      };

      for (const [old, new_str] of Object.entries(replacements)) {
        if (content.includes(old)) {
           content = content.replace(new RegExp(old.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), new_str);
           changed = true;
        }
      }

      if (changed) {
        // Ensure useTheme is imported if not already (basic check)
        if (!content.includes('useTheme')) {
           // This is tricky to inject automatically if they don't have it, but they should after my generalist run
           console.log(`Warning: useTheme might be missing in ${fullPath}`);
        }
        fs.writeFileSync(fullPath, content, 'utf8');
        console.log(`Updated ${fullPath}`);
      }
    }
  }
}

processDir(path.join(__dirname, 'src', 'pages'));
