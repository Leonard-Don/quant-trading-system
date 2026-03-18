/**
 * 国际化配置
 * 基于 React Context 的轻量级 i18n 实现
 */
import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';

// 导入语言包
import zhCN from './locales/zh-CN.json';
import enUS from './locales/en-US.json';

// 支持的语言
const LANGUAGES = {
    'zh-CN': { name: '中文', data: zhCN },
    'en-US': { name: 'English', data: enUS }
};

// 默认语言
const DEFAULT_LANGUAGE = 'zh-CN';

// 创建 Context
const I18nContext = createContext(null);

/**
 * 获取嵌套对象的值
 * @param {Object} obj - 对象
 * @param {string} path - 路径，如 'common.loading'
 */
const getNestedValue = (obj, path) => {
    return path.split('.').reduce((curr, key) => curr?.[key], obj);
};

/**
 * I18n Provider 组件
 */
export const I18nProvider = ({ children }) => {
    // 从 localStorage 读取保存的语言设置
    const [language, setLanguageState] = useState(() => {
        const saved = localStorage.getItem('app_language');
        return saved && LANGUAGES[saved] ? saved : DEFAULT_LANGUAGE;
    });

    // 当前语言数据
    const translations = useMemo(() => LANGUAGES[language]?.data || zhCN, [language]);

    // 切换语言
    const setLanguage = useCallback((lang) => {
        if (LANGUAGES[lang]) {
            setLanguageState(lang);
            localStorage.setItem('app_language', lang);
            // 更新 HTML lang 属性
            document.documentElement.lang = lang;
        }
    }, []);

    // 翻译函数
    const t = useCallback((key, params = {}) => {
        let text = getNestedValue(translations, key);

        if (text === undefined) {
            console.warn(`Translation missing for key: ${key}`);
            return key;
        }

        // 替换参数 {name} -> value
        Object.entries(params).forEach(([paramKey, value]) => {
            text = text.replace(new RegExp(`\\{${paramKey}\\}`, 'g'), value);
        });

        return text;
    }, [translations]);

    // 获取可用语言列表
    const availableLanguages = useMemo(() =>
        Object.entries(LANGUAGES).map(([code, { name }]) => ({ code, name })),
        []
    );

    const value = useMemo(() => ({
        language,
        setLanguage,
        t,
        availableLanguages
    }), [language, setLanguage, t, availableLanguages]);

    return (
        <I18nContext.Provider value={value}>
            {children}
        </I18nContext.Provider>
    );
};

/**
 * 使用 i18n 的 Hook
 */
export const useI18n = () => {
    const context = useContext(I18nContext);
    if (!context) {
        throw new Error('useI18n must be used within an I18nProvider');
    }
    return context;
};

/**
 * 语言切换组件
 */
export const LanguageSwitcher = ({ style }) => {
    const { language, setLanguage, availableLanguages } = useI18n();

    return (
        <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            style={{
                padding: '4px 8px',
                borderRadius: '4px',
                border: '1px solid rgba(148, 163, 184, 0.3)',
                background: 'rgba(30, 41, 59, 0.8)',
                color: '#f8fafc',
                cursor: 'pointer',
                ...style
            }}
        >
            {availableLanguages.map(({ code, name }) => (
                <option key={code} value={code}>{name}</option>
            ))}
        </select>
    );
};

const i18nExports = { I18nProvider, useI18n, LanguageSwitcher };

export default i18nExports;
