/**
 * 前端日志服务
 * 提供错误收集、用户行为追踪和性能指标上报
 */

// 日志级别
const LOG_LEVELS = {
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3
};

// 当前日志级别（生产环境只记录 WARN 以上）
const currentLevel = process.env.NODE_ENV === 'production' ? LOG_LEVELS.WARN : LOG_LEVELS.DEBUG;

// 日志存储
const logBuffer = [];
const MAX_BUFFER_SIZE = 100;

/**
 * 日志服务类
 */
class LoggerService {
    constructor() {
        this.sessionId = this.generateSessionId();
        this.userId = null;
        this.setupGlobalErrorHandler();
        this.setupPerformanceObserver();
    }

    /**
     * 生成会话 ID
     */
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * 设置用户 ID
     */
    setUserId(userId) {
        this.userId = userId;
    }

    /**
     * 创建日志条目
     */
    createLogEntry(level, message, data = {}) {
        return {
            timestamp: new Date().toISOString(),
            level,
            message,
            data,
            sessionId: this.sessionId,
            userId: this.userId,
            url: window.location.href,
            userAgent: navigator.userAgent
        };
    }

    /**
     * 添加到缓冲区
     */
    addToBuffer(entry) {
        logBuffer.push(entry);
        if (logBuffer.length > MAX_BUFFER_SIZE) {
            logBuffer.shift();
        }

        // 存储到 localStorage（最近 50 条）
        try {
            const recentLogs = logBuffer.slice(-50);
            localStorage.setItem('app_logs', JSON.stringify(recentLogs));
        } catch (e) {
            // localStorage 可能已满
        }
    }

    /**
     * 调试日志
     */
    debug(message, data = {}) {
        if (currentLevel <= LOG_LEVELS.DEBUG) {
            console.debug(`[DEBUG] ${message}`, data);
            this.addToBuffer(this.createLogEntry('DEBUG', message, data));
        }
    }

    /**
     * 信息日志
     */
    info(message, data = {}) {
        if (currentLevel <= LOG_LEVELS.INFO) {
            console.info(`[INFO] ${message}`, data);
            this.addToBuffer(this.createLogEntry('INFO', message, data));
        }
    }

    /**
     * 警告日志
     */
    warn(message, data = {}) {
        if (currentLevel <= LOG_LEVELS.WARN) {
            console.warn(`[WARN] ${message}`, data);
            this.addToBuffer(this.createLogEntry('WARN', message, data));
        }
    }

    /**
     * 错误日志
     */
    error(message, error = null, data = {}) {
        if (currentLevel <= LOG_LEVELS.ERROR) {
            console.error(`[ERROR] ${message}`, error, data);

            const errorData = {
                ...data,
                errorMessage: error?.message,
                errorStack: error?.stack,
                errorName: error?.name
            };

            this.addToBuffer(this.createLogEntry('ERROR', message, errorData));

            // 生产环境可以上报到服务器
            if (process.env.NODE_ENV === 'production') {
                this.reportError(message, errorData);
            }
        }
    }

    /**
     * 用户行为追踪
     */
    trackEvent(eventName, eventData = {}) {
        const entry = this.createLogEntry('EVENT', eventName, {
            ...eventData,
            eventType: 'user_action'
        });
        this.addToBuffer(entry);
        this.debug(`Event: ${eventName}`, eventData);
    }

    /**
     * 页面访问追踪
     */
    trackPageView(pageName) {
        this.trackEvent('page_view', { pageName });
    }

    /**
     * 功能使用追踪
     */
    trackFeatureUsage(featureName, details = {}) {
        this.trackEvent('feature_usage', { featureName, ...details });
    }

    /**
     * 设置全局错误处理器
     */
    setupGlobalErrorHandler() {
        // 捕获未处理的 Promise 错误
        window.addEventListener('unhandledrejection', (event) => {
            this.error('Unhandled Promise Rejection', event.reason);
        });

        // 捕获全局错误
        window.addEventListener('error', (event) => {
            this.error('Global Error', new Error(event.message), {
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno
            });
        });
    }

    /**
     * 设置性能监控
     */
    setupPerformanceObserver() {
        if ('PerformanceObserver' in window) {
            try {
                // 监控长任务
                const longTaskObserver = new PerformanceObserver((list) => {
                    for (const entry of list.getEntries()) {
                        if (entry.duration > 50) {
                            this.warn('Long Task Detected', {
                                duration: entry.duration,
                                startTime: entry.startTime
                            });
                        }
                    }
                });
                longTaskObserver.observe({ entryTypes: ['longtask'] });
            } catch (e) {
                // 某些浏览器可能不支持
            }
        }
    }

    /**
     * 获取性能指标
     */
    getPerformanceMetrics() {
        const navigation = performance.getEntriesByType('navigation')[0];
        const paint = performance.getEntriesByType('paint');

        const metrics = {
            // 页面加载时间
            pageLoadTime: navigation ? navigation.loadEventEnd - navigation.startTime : null,
            // DOM 解析完成时间
            domContentLoaded: navigation ? navigation.domContentLoadedEventEnd - navigation.startTime : null,
            // 首次绘制
            firstPaint: paint.find(p => p.name === 'first-paint')?.startTime,
            // 首次内容绘制
            firstContentfulPaint: paint.find(p => p.name === 'first-contentful-paint')?.startTime
        };

        return metrics;
    }

    /**
     * 上报错误到服务器（生产环境）
     */
    async reportError(message, errorData) {
        try {
            // 这里可以替换为实际的错误上报服务
            // await fetch('/api/logs/error', {
            //   method: 'POST',
            //   headers: { 'Content-Type': 'application/json' },
            //   body: JSON.stringify({ message, ...errorData, sessionId: this.sessionId })
            // });
            console.log('[Logger] Error would be reported:', message);
        } catch (e) {
            // 上报失败，静默处理
        }
    }

    /**
     * 获取所有日志
     */
    getLogs() {
        return [...logBuffer];
    }

    /**
     * 清空日志
     */
    clearLogs() {
        logBuffer.length = 0;
        localStorage.removeItem('app_logs');
    }

    /**
     * 导出日志
     */
    exportLogs() {
        const logs = this.getLogs();
        const blob = new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `app_logs_${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }
}

// 全局单例
const logger = new LoggerService();

export default logger;
export { LOG_LEVELS };
