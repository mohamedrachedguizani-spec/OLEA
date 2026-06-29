// src/components/NotificationBell.jsx
import React, { useState, useRef, useEffect } from 'react';

const SEVERITY_CONFIG = {
    critical: { icon: '🔴', color: '#dc3545', label: 'Critique' },
    warning:  { icon: '🟡', color: '#f0ad4e', label: 'Alerte' },
    info:     { icon: '🔵', color: '#5bc0de', label: 'Info' },
    success:  { icon: '🟢', color: '#5cb85c', label: 'Succès' },
};

function timeAgo(dateStr) {
    const now = new Date();
    const date = new Date(dateStr);
    const diff = Math.floor((now - date) / 1000);
    if (diff < 60) return 'À l\'instant';
    if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `il y a ${Math.floor(diff / 3600)}h`;
    return `il y a ${Math.floor(diff / 86400)}j`;
}

export default function NotificationBell({
    notifications,
    unreadCount,
    onMarkRead,
    onMarkAllRead,
    onDelete,
}) {
    const [open, setOpen] = useState(false);
    const panelRef = useRef(null);

    // Fermer le panel si on clique en dehors
    useEffect(() => {
        function handleClickOutside(e) {
            if (panelRef.current && !panelRef.current.contains(e.target)) {
                setOpen(false);
            }
        }
        if (open) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [open]);

    return (
        <div className="notif-bell-container" ref={panelRef}>
            <button
                className="notif-bell-btn"
                onClick={() => setOpen(prev => !prev)}
                title="Notifications"
            >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="22" height="22">
                    <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                    <path d="M13.73 21a2 2 0 0 1-3.46 0" />
                </svg>
                {unreadCount > 0 && (
                    <span className="notif-bell-badge">
                        {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                )}
            </button>

            {open && (
                <div className="notif-panel">
                    <div className="notif-panel-header">
                        <span className="notif-panel-title">Notifications</span>
                        {unreadCount > 0 && (
                            <button
                                className="notif-mark-all-btn"
                                onClick={() => { onMarkAllRead(); }}
                            >
                                Tout marquer lu
                            </button>
                        )}
                    </div>

                    <div className="notif-panel-list">
                        {notifications.length === 0 ? (
                            <div className="notif-empty">Aucune notification</div>
                        ) : (
                            notifications.map((notif) => {
                                const sev = SEVERITY_CONFIG[notif.severity] || SEVERITY_CONFIG.info;
                                return (
                                    <div
                                        key={notif.id}
                                        className={`notif-item ${notif.is_read ? 'notif-read' : 'notif-unread'}`}
                                        onClick={() => { if (!notif.is_read) onMarkRead(notif.id); }}
                                    >
                                        <div className="notif-item-icon">
                                            <span>{sev.icon}</span>
                                        </div>
                                        <div className="notif-item-content">
                                            <div className="notif-item-title">{notif.title}</div>
                                            <div className="notif-item-message">{notif.message}</div>
                                            <div className="notif-item-meta">
                                                <span className="notif-item-time">{timeAgo(notif.created_at)}</span>
                                                <span
                                                    className="notif-item-module"
                                                    style={{ borderColor: sev.color }}
                                                >
                                                    {notif.module}
                                                </span>
                                            </div>
                                        </div>
                                        <button
                                            className="notif-item-delete"
                                            onClick={(e) => { e.stopPropagation(); onDelete(notif.id); }}
                                            title="Supprimer"
                                        >
                                            ×
                                        </button>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
