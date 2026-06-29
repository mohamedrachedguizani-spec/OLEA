// src/hooks/useNotifications.js
//
// Hook qui gère les notifications en temps réel.
// - Charge les notifications au mount
// - Reçoit les nouvelles notifications via onWsNotification (appelé depuis useLiveUpdates)
// - unreadCount est dérivé de la liste notifications (jamais désynchronisé)
// - Expose : notifications, unreadCount, loading, markRead, markAllRead, deleteNotification, refresh, handleWsNotification

import { useState, useEffect, useCallback, useMemo } from 'react';
import ApiService from '../services/api';

export default function useNotifications(enabled = true) {
    const [notifications, setNotifications] = useState([]);
    const [loading, setLoading] = useState(false);

    // ─── unreadCount dérivé directement de la liste ───
    const unreadCount = useMemo(
        () => notifications.filter(n => !n.is_read).length,
        [notifications]
    );

    // ─── Charger les notifications depuis l'API ───
    const refresh = useCallback(async () => {
        if (!enabled) return;
        setLoading(true);
        try {
            const notifData = await ApiService.getNotifications(50, 0);
            setNotifications(notifData.items || []);
        } catch {
            // silently fail
        } finally {
            setLoading(false);
        }
    }, [enabled]);

    // ─── Handler pour les notifications WebSocket (appelé depuis App.js via useLiveUpdates) ───
    const handleWsNotification = useCallback((action, payload) => {
        if (action === 'new' && payload) {
            setNotifications(prev => {
                // Déduplication par id
                if (payload.id && prev.some(n => n.id === payload.id)) {
                    return prev;
                }
                return [payload, ...prev].slice(0, 50);
            });
        } else if (action === 'delete' && payload) {
            setNotifications(prev => prev.filter(n => n.id !== payload.id));
        } else if (action === 'read' && payload) {
            setNotifications(prev =>
                prev.map(n => n.id === payload.id ? { ...n, is_read: true } : n)
            );
        } else if (action === 'read_all') {
            setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
        }
    }, []);

    useEffect(() => {
        if (enabled) {
            refresh();
        } else {
            setNotifications([]);
        }
    }, [enabled, refresh]);

    // ─── Actions ───
    const markRead = useCallback(async (id) => {
        try {
            await ApiService.markNotificationRead(id);
            setNotifications(prev =>
                prev.map(n => n.id === id ? { ...n, is_read: true } : n)
            );
        } catch {
            // ignore
        }
    }, []);

    const markAllRead = useCallback(async () => {
        try {
            await ApiService.markAllNotificationsRead();
            setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
        } catch {
            // ignore
        }
    }, []);

    const deleteNotification = useCallback(async (id) => {
        try {
            await ApiService.deleteNotification(id);
            setNotifications(prev => prev.filter(n => n.id !== id));
        } catch {
            // ignore
        }
    }, []);

    return {
        notifications,
        unreadCount,
        loading,
        markRead,
        markAllRead,
        deleteNotification,
        refresh,
        handleWsNotification,
    };
}
