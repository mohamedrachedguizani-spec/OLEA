// src/App.jsx
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
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
import BalanceAgee from './components/BalanceAgee';
import BalanceAgeeFournisseur from './components/BalanceAgeeFournisseur';
import NotificationBell from './components/NotificationBell';
import oleaLogo from './assets/olea-logo.svg';

const ACTIVE_TAB_STORAGE_KEY = 'olea-active-module';
const APP_TABS = [
    'dashboard', 'saisie', 'export', 'rapprochement',
    'rapprochement_bancaire', 'sage-bfc', 'reporting',
    'balance-agee', 'balance-fournisseur', 'configuration', 'users', 'roles', 'audit',
];

const TAB_PATHS = {
    dashboard: '/',
    saisie: '/saisie-caisse',
    export: '/export',
    rapprochement: '/saisie-bancaire',
    rapprochement_bancaire: '/rapprochement-bancaire',
    'sage-bfc': '/sage-bfc',
    reporting: '/reporting',
    'balance-agee': '/balance-agee',
    'balance-fournisseur': '/balance-fournisseur',
    configuration: '/configuration',
    users: '/users',
    roles: '/roles',
    audit: '/audit',
};

const PATH_TABS = Object.entries(TAB_PATHS).reduce((result, [tab, path]) => {
    result[path] = tab;
    return result;
}, {});

function tabFromPath(pathname) {
    return PATH_TABS[pathname] || 'dashboard';
}

function App() {
    const { user, loading, has, hasPermission, logout } = useAuth();
    const location = useLocation();
    const navigate = useNavigate();
    const [activeTab, setActiveTab] = useState(() => {
        if (typeof window === 'undefined') return 'dashboard';
        const routeTab = tabFromPath(window.location.pathname);
        if (window.location.pathname !== '/' || routeTab !== 'dashboard') return routeTab;
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
    const [balanceTarget, setBalanceTarget] = useState(null);
    const explicitLogout = useRef(false);

    const handleLogout = useCallback(async () => {
        explicitLogout.current = true;
        navigate('/login', { replace: true });
        await logout();
    }, [logout, navigate]);

    const navigateToTab = useCallback((tab, params = {}) => {
        const path = TAB_PATHS[tab] || TAB_PATHS.dashboard;
        const search = new URLSearchParams(params).toString();
        navigate(search ? `${path}?${search}` : path);
        setActiveTab(tab);
    }, [navigate]);

    // L'URL est la source de vérité : un accès direct ou les boutons précédent/suivant
    // mettent aussi à jour l'onglet actif utilisé par le composant Sidebar.
    useEffect(() => {
        setActiveTab(tabFromPath(location.pathname));
    }, [location.pathname]);

    // Les écrans protégés redirigent vers la connexion. Après authentification,
    // l'utilisateur revient sur la page qu'il essayait d'ouvrir.
    useEffect(() => {
        if (loading) return;
        if (!user && location.pathname !== '/login' && !explicitLogout.current) {
            const currentUrl = `${location.pathname}${location.search}${location.hash}`;
            const loginUrl = currentUrl === '/' ? '/login' : `/login?redirect=${encodeURIComponent(currentUrl)}`;
            navigate(loginUrl, { replace: true });
        } else if (user && location.pathname === '/login') {
            navigate('/', { replace: true });
        }
    }, [loading, user, location.pathname, location.search, location.hash, navigate]);

    const handleLoginSuccess = useCallback(() => {
        explicitLogout.current = false;
        const redirect = new URLSearchParams(location.search).get('redirect');
        const target = redirect && redirect.startsWith('/') ? redirect : '/';
        navigate(target, { replace: true });
    }, [location.search, navigate]);

    const openMappingConfiguration = useCallback(() => {
        setConfigurationInitialTab('mapping');
        navigateToTab('configuration');
    }, [navigateToTab]);

    const canAccessTab = useCallback((tab) => ({
        dashboard: has('dashboard.read') || has('admin.dashboard.read'),
        reporting: hasPermission('reporting'),
        saisie: hasPermission('saisie_caisse'),
        export: hasPermission('export_csv'),
        'sage-bfc': hasPermission('sage_bfc'),
        configuration: hasPermission('configuration'),
        rapprochement: hasPermission('saisie_bancaire'),
        rapprochement_bancaire: hasPermission('rapprochement_bancaire'),
        'balance-agee': hasPermission('balance_agee'),
        'balance-fournisseur': hasPermission('balance_fournisseur'),
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
        navigateToTab(targetTab, Object.fromEntries(targetUrl.searchParams.entries()));
    }, [canAccessTab, navigateToTab]);

    const consumeNotificationTarget = useCallback((targetKey) => {
        setNotificationTarget((current) => current?.key === targetKey ? null : current);
    }, []);

    const openBalanceTarget = useCallback((tab, params = {}) => {
        if (!canAccessTab(tab)) return;
        setBalanceTarget({ key: `${tab}-${Date.now()}`, tab, params });
        navigateToTab(tab, params);
    }, [canAccessTab, navigateToTab]);

    const consumeBalanceTarget = useCallback((targetKey) => {
        setBalanceTarget((current) => current?.key === targetKey ? null : current);
    }, []);

    useEffect(() => {
        if (!user || canAccessTab(activeTab)) return;
        const firstAllowed = APP_TABS.find(canAccessTab);
        if (firstAllowed) navigateToTab(firstAllowed);
    }, [activeTab, canAccessTab, navigateToTab, user]);

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
                <Login onSuccess={handleLoginSuccess} />
            </div>
        );
    }

    // Connecté → application normale
    return (
        <div className={`app ${darkMode ? 'dark-mode' : 'light-mode'}`}>
            <Sidebar 
                activeTab={activeTab}
                setActiveTab={navigateToTab}
                onLogout={handleLogout}
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
                        <Dashboard refreshTrigger={refreshTrigger} onNavigate={openBalanceTarget} />
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
                    {activeTab === 'balance-agee' && hasPermission('balance_agee') && <BalanceAgee navigationTarget={balanceTarget?.tab === 'balance-agee' ? balanceTarget : null} onNavigationConsumed={consumeBalanceTarget} />}
                    {activeTab === 'balance-fournisseur' && hasPermission('balance_fournisseur') && <BalanceAgeeFournisseur navigationTarget={balanceTarget?.tab === 'balance-fournisseur' ? balanceTarget : null} onNavigationConsumed={consumeBalanceTarget} />}
                    {activeTab === 'users' && has('admin.users.read') && <UserManagement />}
                    {activeTab === 'roles' && has('admin.roles.read') && <RoleManagement />}
                    {activeTab === 'audit' && has('admin.audit.read') && <AuditLogs />}
                </div>

                <footer className="main-footer">
                    <div className="footer-content">
                        <span>Système de Gestion comptable et financière</span>
                        <span className="footer-brand">© Olea Tunisie</span>
                    </div>
                </footer>
            </main>
        </div>
    );
}

export default App;
