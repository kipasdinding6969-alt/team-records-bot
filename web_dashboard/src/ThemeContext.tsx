import React, { createContext, useContext, useState, useEffect } from 'react';
import { ThemeMode, Theme, resolveTheme, getTheme, setTheme as saveTheme, applyThemeCssVars } from './theme';

interface ThemeContextProps {
  mode: ThemeMode;
  theme: Theme;
  setMode: (mode: ThemeMode) => void;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextProps | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setModeState] = useState<ThemeMode>(getTheme());

  const theme = resolveTheme(mode);

  const setMode = (newMode: ThemeMode) => {
    setModeState(newMode);
    saveTheme(newMode);
  };

  const toggleTheme = () => {
    setMode(mode === 'light' ? 'dark' : 'light');
  };

  // Sync CSS variables whenever theme changes
  useEffect(() => {
    applyThemeCssVars(theme);
  }, [mode]);

  return (
    <ThemeContext.Provider value={{ mode, theme, setMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
