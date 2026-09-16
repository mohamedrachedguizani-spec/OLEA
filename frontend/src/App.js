// src/App.jsx
import React, { useState, useCallback, useEffect } from 'react';
import { useAuth } from './contexts/AuthContext';
import useLiveUpdates from './hooks/useLiveUpdates';
import useNotifications from './hooks/useNotifications';
import Login from './components/Login';
import SaisieCaisse from './components/SaisieCaisse';
import ExportCSV from './components/ExportCSV';
import SageBfcParser from './components/SageBfcParser';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import UserManagement from './components/UserManagement';
import RoleManagement from './components/RoleManagement';
import AuditLogs from './components/AuditLogs';
import Reporting from './components/Reporting';
import Configuration from './components/Configuration';
import SaisieBancaire from './components/SaisieBancaire';
import RapprochementBancaire from './components/RapprochementBancaire';
import NotificationBell from './components/NotificationBell';
import oleaLogo from './assets/olea-logo.svg';

const ACTIVE_TAB_STORAGE_KEY = 'olea-active-module';
const APP_TABS = [
    'dashboard', 'saisie', 'export', 'rapprochement',
    'rapprochement_bancaire', 'sage-bfc', 'reporting',
    'configuration', 'users', 'roles', 'audit',
];

function App() {
    const { user, loading, has, hasPermission } = useAuth();
    const [activeTab, setActiveTab] = useState(() => {
        if (typeof window === 'undefined') return 'dashboard';
        const storedTab = window.localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
        return APP_TABS.includes(storedTab) ? storedTab : 'dashboard';
    });
    const [darkMode, setDarkMode] = useState(() => {
        if (typeof window === 'undefined') return false;
        return window.localStorage.getItem('olea-theme') === 'dark';
    });
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
    const [refreshTrigger, setRefreshTrigger] = useState(0);
    const [migrationRefresh, setMigrationRefresh] = useState(0);
    const [sageBfcRefresh, setSageBfcRefresh] = useState(0);
    const [forecastRefresh, setForecastRefresh] = useState(0);
    const [reportingRefresh, setReportingRefresh] = useState(0);
    const [configurationRefresh, setConfigurationRefresh] = useState(0);
    const [configurationInitialTab, setConfigurationInitialTab] = useState('comptes');
    const [notificationTarget, setNotificationTarget] = useState(null);

    const openMappingConfiguration = useCallback(() => {
        setConfigurationInitialTab('mapping');
        setActiveTab('configuration');
    }, []);

    const canAccessTab = useCallback((tab) => ({
        dashboard: has('dashboard.read') || has('admin.dashboard.read'),
        reporting: hasPermission('reporting'),
        saisie: hasPermission('saisie_caisse'),
        export: hasPermission('export_csv'),
        'sage-bfc': hasPermission('sage_bfc'),
        configuration: hasPermission('configuration'),
        rapprochement: hasPermission('saisie_bancaire'),
        rapprochement_bancaire: hasPermission('rapprochement_bancaire'),
        users: has('admin.users.read'),
        roles: has('admin.roles.read'),
        audit: has('admin.audit.read'),
    }[tab] || false), [has, hasPermission]);

    const openNotificationTarget = useCallback((notification) => {
        if (!notification?.route) return;
        const targetUrl = new URL(notification.route, window.location.origin);
        const routeToTab = {
            '/sage-bfc': 'sage-bfc',
            '/saisie-bancaire': 'rapprochement',
            '/rapprochement-bancaire': 'rapprochement_bancaire',
            '/users': 'users',
            '/audit': 'audit',
        };
        const targetTab = routeToTab[targetUrl.pathname];
        if (!targetTab || !canAccessTab(targetTab)) return;
        setNotificationTarget({
            key: `${notification.id}-${Date.now()}`,
            tab: targetTab,
            params: Object.fromEntries(targetUrl.searchParams.entries()),
            entityType: notification.entity_type,
            entityId: notification.entity_id,
        });
        setActiveTab(targetTab);
    }, [canAccessTab]);

    const consumeNotificationTarget = useCallback((targetKey) => {
        setNotificationTarget((current) => current?.key === targetKey ? null : current);
    }, []);

    useEffect(() => {
        if (!user || canAccessTab(activeTab)) return;
        const firstAllowed = APP_TABS.find(canAccessTab);
        if (firstAllowed) setActiveTab(firstAllowed);
    }, [activeTab, canAccessTab, user]);

    useEffect(() => {
        if (!user || !canAccessTab(activeTab) || typeof window === 'undefined') return;
        window.localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
    }, [activeTab, canAccessTab, user]);

    useEffect(() => {
        if (typeof window !== 'undefined') {
            window.localStorage.setItem('olea-theme', darkMode ? 'dark' : 'light');
        }
        if (typeof document !== 'undefined') {
            document.body.classList.toggle('dark-mode', darkMode);
            document.body.classList.toggle('light-mode', !darkMode);
        }
    }, [darkMode]);

    const handleMigrationComplete = useCallback(() => {
        setRefreshTrigger(prev => prev + 1);
    }, []);

    // ─── Notifications temps réel ───
    const {
        notifications: notifList,
        unreadCount: notifUnread,
        markRead: notifMarkRead,
        markAllRead: notifMarkAllRead,
        deleteNotification: notifDelete,
        handleWsNotification,
    } = useNotifications(Boolean(user));

    // ─── Temps réel : WebSocket pour synchroniser plusieurs comptables ───
    useLiveUpdates({
        caisse: () => {
            setRefreshTrigger(prev => prev + 1);
            setMigrationRefresh(prev => prev + 1);
        },
        migration: () => {
            setRefreshTrigger(prev => prev + 1);
            setMigrationRefresh(prev => prev + 1);
        },
        sage_bfc: () => {
            setSageBfcRefresh(prev => prev + 1);
            setReportingRefresh(prev => prev + 1);
        },
        forecast: () => {
            setForecastRefresh(prev => prev + 1);
            setReportingRefresh(prev => prev + 1);
        },
        configuration: () => {
            setConfigurationRefresh(prev => prev + 1);
            setMigrationRefresh(prev => prev + 1);
        },
        notifications: handleWsNotification,
    }, { enabled: Boolean(user) });

    // Écran de chargement initial
    if (loading) {
        return (
            <div className={`app ${darkMode ? 'dark-mode' : 'light-mode'}`}>
                <div className="app-loading">
                    <img
                        src={oleaLogo}
                        alt="OLEA Insurance Solutions Africa"
                        className="app-loading-logo"
                    />
                </div>
            </div>
        );
    }

    // Si pas connecté → page login
    if (!user) {
        return (
            <div className={`app ${darkMode ? 'dark-mode' : 'light-mode'}`}>
                <Login />
            </div>
        );
    }

    // Connecté → application normale
    return (
        <div className={`app ${darkMode ? 'dark-mode' : 'light-mode'}`}>
            <Sidebar 
                activeTab={activeTab}
                setActiveTab={setActiveTab}
                darkMode={darkMode}
                setDarkMode={setDarkMode}
                sidebarOpen={sidebarOpen}
                setSidebarOpen={setSidebarOpen}
                sidebarCollapsed={sidebarCollapsed}
                setSidebarCollapsed={setSidebarCollapsed}
            />

            <main className={`main-content ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
                <header className="top-header">
                    <button 
                        className="menu-toggle"
                        onClick={() => setSidebarOpen(true)}
                    >
                        ☰
                    </button>
                    <div className="header-title">
                        <div className="header-user-info">
                            <div className="header-user-avatar">
                                {user.full_name?.charAt(0).toUpperCase()}
                            </div>
                            <div className="header-user-details">
                                <span className="header-user-name">{user.full_name}</span>
                                <span className="header-user-role">{user.role}</span>
                            </div>
                        </div>
                    </div>
                    <div className="header-actions">
                        <NotificationBell
                            notifications={notifList}
                            unreadCount={notifUnread}
                            onMarkRead={notifMarkRead}
                            onMarkAllRead={notifMarkAllRead}
                            onDelete={notifDelete}
                            onOpen={openNotificationTarget}
                        />
                        <span className="date-display">
                            {new Date().toLocaleDateString('fr-FR', { 
                                weekday: 'long', 
                                year: 'numeric', 
                                month: 'long', 
                                day: 'numeric' 
                            })}
                        </span>
                    </div>
                </header>

                <div className="content-wrapper">
                    {activeTab === 'dashboard' && canAccessTab('dashboard') && (
                        <Dashboard refreshTrigger={refreshTrigger} onNavigate={(tab) => canAccessTab(tab) && setActiveTab(tab)} />
                    )}
                    {activeTab === 'reporting' && hasPermission('reporting', 'read') && <Reporting refreshTrigger={reportingRefresh} />}
                    {activeTab === 'saisie' && hasPermission('saisie_caisse') && <SaisieCaisse refreshTrigger={refreshTrigger} />}
                    {activeTab === 'export' && hasPermission('export_csv') && <ExportCSV />}
                    {activeTab === 'sage-bfc' && hasPermission('sage_bfc') && <SageBfcParser
                        refreshTrigger={sageBfcRefresh}
                        forecastRefresh={forecastRefresh}
                        onOpenMappingConfiguration={hasPermission('configuration', 'read') ? openMappingConfiguration : null}
                        navigationTarget={notificationTarget?.tab === 'sage-bfc' ? notificationTarget : null}
                        onNavigationConsumed={consumeNotificationTarget}
                    />}
                    {activeTab === 'configuration' && hasPermission('configuration', 'read') && <Configuration initialTab={configurationInitialTab} />}
                    {activeTab === 'rapprochement' && hasPermission('saisie_bancaire', 'read') && <SaisieBancaire navigationTarget={notificationTarget?.tab === 'rapprochement' ? notificationTarget : null} />}
                    {activeTab === 'rapprochement_bancaire' && hasPermission('rapprochement_bancaire', 'read') && <RapprochementBancaire navigationTarget={notificationTarget?.tab === 'rapprochement_bancaire' ? notificationTarget : null} />}
                    {activeTab === 'users' && has('admin.users.read') && <UserManagement />}
                    {activeTab === 'roles' && has('admin.roles.read') && <RoleManagement />}
                    {activeTab === 'audit' && has('admin.audit.read') && <AuditLogs />}
                </div>

                <footer className="main-footer">
                    <div className="footer-content">
                        <span>Système de Gestion comptable et financière - Format compatible Sage</span>
                        <span className="footer-brand">© Powered by Guizani Med Rached</span>
                    </div>
                </footer>
            </main>
        </div>
    );
}

export default App;
