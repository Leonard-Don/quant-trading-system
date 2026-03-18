import React, { createContext, useContext, useState, useEffect } from 'react';
import { App as AntdApp, ConfigProvider, theme as antdTheme } from 'antd';

const ThemeContext = createContext();

export const useTheme = () => {
    const context = useContext(ThemeContext);
    if (!context) {
        throw new Error('useTheme must be used within a ThemeProvider');
    }
    return context;
};

// Dark theme - Midnight Fintech style
const darkThemeConfig = {
    algorithm: antdTheme.darkAlgorithm,
    token: {
        colorPrimary: '#38bdf8',
        borderRadius: 6,
        colorBgContainer: '#1e293b',
        colorBgElevated: '#334155',
        colorBgLayout: '#0f172a',
        colorBorder: 'rgba(148, 163, 184, 0.15)',
        colorText: '#f8fafc',
        colorTextSecondary: '#cbd5e1',
    },
    components: {
        Layout: {
            headerBg: 'rgba(15, 23, 42, 0.8)',
            siderBg: 'rgba(15, 23, 42, 0.6)',
            bodyBg: '#0f172a',
        },
        Menu: {
            itemBg: 'transparent',
            itemSelectedBg: 'rgba(56, 189, 248, 0.15)',
            itemSelectedColor: '#38bdf8',
            itemColor: '#cbd5e1',
            itemHoverColor: '#fff',
        },
        Card: {
            colorBgContainer: 'rgba(30, 41, 59, 0.7)',
        },
        Table: {
            colorBgContainer: 'transparent',
            headerBg: 'rgba(255, 255, 255, 0.02)',
        },
        Statistic: {
            colorTextDescription: '#cbd5e1',
        },
        Input: {
            colorBgContainer: 'rgba(15, 23, 42, 0.6)',
        },
        Select: {
            colorBgContainer: 'rgba(15, 23, 42, 0.6)',
        },
    },
};

// Light theme - Clean Professional style
const lightThemeConfig = {
    algorithm: antdTheme.defaultAlgorithm,
    token: {
        colorPrimary: '#2563eb',
        borderRadius: 6,
        colorBgContainer: '#ffffff',
        colorBgElevated: '#f8fafc',
        colorBgLayout: '#f1f5f9',
        colorBorder: 'rgba(100, 116, 139, 0.2)',
        colorText: '#1e293b',
        colorTextSecondary: '#64748b',
    },
    components: {
        Layout: {
            headerBg: '#ffffff',
            siderBg: '#ffffff',
            bodyBg: '#f1f5f9',
        },
        Menu: {
            itemBg: 'transparent',
            itemSelectedBg: 'rgba(37, 99, 235, 0.1)',
            itemSelectedColor: '#2563eb',
            itemColor: '#475569',
            itemHoverColor: '#1e293b',
        },
        Card: {
            colorBgContainer: '#ffffff',
        },
        Table: {
            colorBgContainer: '#ffffff',
            headerBg: 'rgba(241, 245, 249, 0.5)',
        },
        Statistic: {
            colorTextDescription: '#64748b',
        },
        Input: {
            colorBgContainer: '#ffffff',
        },
        Select: {
            colorBgContainer: '#ffffff',
        },
    },
};

export const ThemeProvider = ({ children }) => {
    // Load theme preference from localStorage, default to dark
    const [isDarkMode, setIsDarkMode] = useState(() => {
        const saved = localStorage.getItem('theme-mode');
        return saved !== null ? saved === 'dark' : true;
    });

    // Save theme preference to localStorage
    useEffect(() => {
        localStorage.setItem('theme-mode', isDarkMode ? 'dark' : 'light');
        // Update document class for any additional CSS styling
        document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');
    }, [isDarkMode]);

    const toggleTheme = () => {
        setIsDarkMode(prev => !prev);
    };

    const themeConfig = isDarkMode ? darkThemeConfig : lightThemeConfig;

    return (
        <ThemeContext.Provider value={{ isDarkMode, toggleTheme }}>
            <ConfigProvider theme={themeConfig}>
                <AntdApp>
                    {children}
                </AntdApp>
            </ConfigProvider>
        </ThemeContext.Provider>
    );
};

export default ThemeProvider;
