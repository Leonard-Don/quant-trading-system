import { createContext, useContext, useState, useEffect } from 'react';
import { App as AntdApp, ConfigProvider } from 'antd';
import { buildAntdTheme } from '../design/antdTheme';
import { applyTokens } from '../design/applyTokens';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider = ({ children }) => {
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme-mode');
    return saved !== null ? saved === 'dark' : true;
  });

  useEffect(() => {
    const mode = isDarkMode ? 'dark' : 'light';
    localStorage.setItem('theme-mode', mode);
    document.documentElement.setAttribute('data-theme', mode);
    applyTokens(mode);
  }, [isDarkMode]);

  const toggleTheme = () => setIsDarkMode((prev) => !prev);

  return (
    <ThemeContext.Provider value={{ isDarkMode, toggleTheme }}>
      <ConfigProvider theme={buildAntdTheme(isDarkMode)}>
        <AntdApp>{children}</AntdApp>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
};

export default ThemeProvider;
