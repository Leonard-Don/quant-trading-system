/**
 * 股票收藏夹 Hook
 * 管理用户收藏的股票列表，使用 localStorage 持久化
 */

import { useState, useEffect, useCallback } from 'react';

const STORAGE_KEY = 'quant_stock_favorites';
const MAX_FAVORITES = 20;

/**
 * 股票收藏夹 Hook
 * @returns {{
 *   favorites: string[],
 *   addFavorite: (symbol: string) => boolean,
 *   removeFavorite: (symbol: string) => void,
 *   isFavorite: (symbol: string) => boolean,
 *   toggleFavorite: (symbol: string) => void,
 *   clearFavorites: () => void
 * }}
 */
export const useFavorites = () => {
    const [favorites, setFavorites] = useState([]);

    // 初始化时从 localStorage 加载
    useEffect(() => {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (Array.isArray(parsed)) {
                    setFavorites(parsed);
                }
            }
        } catch (error) {
            console.warn('Failed to load favorites from localStorage:', error);
        }
    }, []);

    // 保存到 localStorage
    const saveFavorites = useCallback((newFavorites) => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(newFavorites));
        } catch (error) {
            console.warn('Failed to save favorites to localStorage:', error);
        }
    }, []);

    /**
     * 添加收藏
     * @param {string} symbol - 股票代码
     * @returns {boolean} 是否添加成功
     */
    const addFavorite = useCallback((symbol) => {
        const upperSymbol = symbol.toUpperCase().trim();

        if (!upperSymbol) return false;
        if (favorites.includes(upperSymbol)) return false;
        if (favorites.length >= MAX_FAVORITES) {
            console.warn(`Maximum favorites (${MAX_FAVORITES}) reached`);
            return false;
        }

        const updated = [...favorites, upperSymbol];
        setFavorites(updated);
        saveFavorites(updated);
        return true;
    }, [favorites, saveFavorites]);

    /**
     * 移除收藏
     * @param {string} symbol - 股票代码
     */
    const removeFavorite = useCallback((symbol) => {
        const upperSymbol = symbol.toUpperCase().trim();
        const updated = favorites.filter(s => s !== upperSymbol);
        setFavorites(updated);
        saveFavorites(updated);
    }, [favorites, saveFavorites]);

    /**
     * 检查是否已收藏
     * @param {string} symbol - 股票代码
     * @returns {boolean}
     */
    const isFavorite = useCallback((symbol) => {
        return favorites.includes(symbol.toUpperCase().trim());
    }, [favorites]);

    /**
     * 切换收藏状态
     * @param {string} symbol - 股票代码
     */
    const toggleFavorite = useCallback((symbol) => {
        if (isFavorite(symbol)) {
            removeFavorite(symbol);
        } else {
            addFavorite(symbol);
        }
    }, [isFavorite, addFavorite, removeFavorite]);

    /**
     * 清空所有收藏
     */
    const clearFavorites = useCallback(() => {
        setFavorites([]);
        saveFavorites([]);
    }, [saveFavorites]);

    return {
        favorites,
        addFavorite,
        removeFavorite,
        isFavorite,
        toggleFavorite,
        clearFavorites
    };
};

export default useFavorites;
