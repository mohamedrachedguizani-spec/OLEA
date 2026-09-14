import React, { useEffect, useRef, useState } from 'react';
import { FiBell, FiCheck, FiX } from 'react-icons/fi';

const SEVERITY_LABELS = {
    critical: 'Critique', warning: 'Alerte', info: 'Information', success: 'Succès',
};

function formatDate(dateStr) {
    if (!dateStr) return '';
    return new Intl.DateTimeFormat('fr-FR', {
        dateStyle: 'short', timeStyle: 'short',
    }).format(new Date(dateStr));
}

export default function NotificationBell({
    notifications, unreadCount, onMarkRead, onMarkAllRead, onDelete, onOpen,
}) {
    const [open, setOpen] = useState(false);
    const panelRef = useRef(null);

    useEffect(() => {
        const closeOutside = (event) => {
            if (!panelRef.current?.contains(event.target)) setOpen(false);
        };
        document.addEventListener('mousedown', closeOutside);
        return () => document.removeEventListener('mousedown', closeOutside);
    }, []);

    const openNotification = async (notification) => {
        if (!notification.is_read) await onMarkRead(notification.id);
        setOpen(false);
        onOpen?.(notification);
    };

    return (
        <div className="notif-bell-container" ref={panelRef}>
            <button className="notif-bell-btn" aria-label="Notifications" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
                <FiBell size={19} />
                {unreadCount > 0 && <span className="notif-bell-badge">{unreadCount}</span>}
            </button>

            {open && (
                <section className="notif-panel" aria-label="Centre de notifications">
                    <header className="notif-panel-header">
                        <div><strong>Notifications</strong><span>{unreadCount} non lue(s)</span></div>
                        {unreadCount > 0 && <button className="notif-mark-all-btn" onClick={onMarkAllRead}><FiCheck size={15} /> Tout lire</button>}
                    </header>

                    <div className="notif-panel-list">
                        {notifications.length === 0 ? (
                            <div className="notif-empty"><FiBell size={25} /><span>Aucune notification</span></div>
                        ) : notifications.map((notification) => (
                            <div key={notification.id} className={`notif-item ${notification.is_read ? 'notif-read' : 'notif-unread'} severity-${notification.severity || 'info'}`}>
                                <button className="notif-entry" onClick={() => openNotification(notification)}>
                                    <i aria-hidden="true" />
                                    <span>
                                        <strong>{notification.title}</strong>
                                        <p>{notification.message}</p>
                                        <span className="notif-item-meta">
                                            <time>{formatDate(notification.created_at)}</time>
                                            <em>{SEVERITY_LABELS[notification.severity] || 'Information'}</em>
                                        </span>
                                    </span>
                                </button>
                                <button className="notif-item-delete" aria-label={`Supprimer la notification ${notification.title}`} title="Supprimer" onClick={() => onDelete(notification.id)}>
                                    <FiX size={15} />
                                </button>
                            </div>
                        ))}
                    </div>
                </section>
            )}
        </div>
    );
}
