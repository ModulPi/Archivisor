"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
/**
 * Preload 脚本 —— 在渲染进程的上下文中暴露安全的 IPC API。
 * 通过 contextBridge 向渲染进程注入 `window.archivisor` 对象。
 */
const electron_1 = require("electron");
// ---------------------------------------------------------------------------
// 暴露给渲染进程的 API
// ---------------------------------------------------------------------------
electron_1.contextBridge.exposeInMainWorld('archivisor', {
    /**
     * 调用 Python backend 的 JSON-RPC 方法。
     *
     * @example
     *   const result = await window.archivisor.rpc('scan', { root_path: 'C:\\Users\\A\\Desktop' })
     *   const dashboard = await window.archivisor.rpc('query', { type: 'dashboard' })
     */
    rpc: (method, params = {}) => {
        return electron_1.ipcRenderer.invoke('rpc:call', method, params);
    },
    /**
     * 重启 Python backend 进程。
     */
    restartBackend: () => {
        return electron_1.ipcRenderer.invoke('backend:restart');
    },
    /**
     * 获取 backend 状态。
     */
    getBackendStatus: () => {
        return electron_1.ipcRenderer.invoke('backend:status');
    },
    /**
     * 监听 backend 连接状态变化。
     * @param callback - 回调函数，接收 { connected: boolean, reason?: string }
     */
    onBackendStatus: (callback) => {
        electron_1.ipcRenderer.on('backend:status', (_event, status) => {
            callback(status);
        });
    },
});
