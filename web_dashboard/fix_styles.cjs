const fs = require('fs');
const path = require('path');
const dir = '/home/baiwan/team-records-bot/web_dashboard/src/pages';

// Dashboard fix
let dashboard = fs.readFileSync(path.join(dir, 'Dashboard.tsx'), 'utf-8');
dashboard = dashboard.replace('  const { theme } = useTheme()\n', '');
dashboard = dashboard.replace('import { getTheme, resolveTheme } from \'../theme\'', '');
dashboard = dashboard.replace('const theme = resolveTheme(getTheme())', 'const { theme } = useTheme()');
fs.writeFileSync(path.join(dir, 'Dashboard.tsx'), dashboard);

// Move styles inside components
function moveStylesInside(filename, styleNames, componentName) {
  const filepath = path.join(dir, filename);
  let content = fs.readFileSync(filepath, 'utf-8');
  let extractedStyles = [];
  
  for (const styleName of styleNames) {
    // Basic extraction: const styleName: ... = { ... } or const styleName = { ... }
    // This assumes the style object is at the end or we can just regex match it.
    const regex = new RegExp(`const ${styleName}(?:\\s*:\\s*[a-zA-Z\\.<>]+)?\\s*=\\s*\\{[\\s\\S]*?\\n\\}`);
    const match = content.match(regex);
    if (match) {
      extractedStyles.push(match[0]);
      content = content.replace(match[0], '');
    }
  }

  if (extractedStyles.length > 0) {
    // insert inside component
    const componentRegex = new RegExp(`(export\\s+(?:default\\s+)?function\\s+${componentName}\\s*\\([^)]*\\)\\s*\\{\\n)`);
    content = content.replace(componentRegex, `$1  ${extractedStyles.join('\n  ')}\n`);
    fs.writeFileSync(filepath, content);
    console.log(`Moved styles in ${filename}`);
  }
}

moveStylesInside('Login.tsx', ['inputStyle'], 'Login');
moveStylesInside('Setup.tsx', ['inputStyle'], 'Setup');
moveStylesInside('UserManagement.tsx', ['inputStyle'], 'UserManagement');
moveStylesInside('Clients.tsx', ['thStyle', 'tdStyle'], 'Clients');
moveStylesInside('NumberLookup.tsx', ['S'], 'NumberLookup');
moveStylesInside('Performance.tsx', ['styles'], 'Performance');
moveStylesInside('PermissionManager.tsx', ['S'], 'PermissionManager');
moveStylesInside('ClientDetail.tsx', ['S'], 'ClientDetail'); // wait, ClientDetail error was line 21, maybe inside a helper component?

