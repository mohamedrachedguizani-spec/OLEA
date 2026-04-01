// src/App.jsx
import React, { useState, useCallback } from 'react';
import { useAuth } from './contexts/AuthContext';
import useLiveUpdates from './hooks/useLiveUpdates';
import Login from './components/Login';
import SaisieCaisse from './components/SaisieCaisse';
import MigrationSage from './components/MigrationSage';
import ExportCSV from './components/ExportCSV';
import SageBfcParser from './components/SageBfcParser';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import UserManagement from './components/UserManagement';
import Reporting from './components/Reporting';

function App() {
    const { user, loading, hasPermission } = useAuth();
    const [activeTab, setActiveTab] = useState('dashboard');
    const [darkMode, setDarkMode] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [refreshTrigger, setRefreshTrigger] = useState(0);
    const [migrationRefresh, setMigrationRefresh] = useState(0);
    const [sageBfcRefresh, setSageBfcRefresh] = useState(0);
    const [forecastRefresh, setForecastRefresh] = useState(0);
    const [reportingRefresh, setReportingRefresh] = useState(0);

    const handleMigrationComplete = useCallback(() => {
        setRefreshTrigger(prev => prev + 1);
    }, []);

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
    });

    // Écran de chargement initial
    if (loading) {
        return (
            <div className={`app light-mode`}>
                <div className="app-loading">
                    <div className="app-loading-logo">O</div>
                    <p>Chargement…</p>
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
            />

            <main className="main-content">
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
                    {activeTab === 'dashboard' && <Dashboard refreshTrigger={refreshTrigger} />}
                    {activeTab === 'reporting' && hasPermission('reporting', 'read') && <Reporting refreshTrigger={reportingRefresh} />}
                    {activeTab === 'saisie' && <SaisieCaisse refreshTrigger={refreshTrigger} />}
                    {activeTab === 'migration' && <MigrationSage onMigrationComplete={handleMigrationComplete} refreshTrigger={migrationRefresh} />}
                    {activeTab === 'export' && <ExportCSV />}
                    {activeTab === 'sage-bfc' && <SageBfcParser refreshTrigger={sageBfcRefresh} forecastRefresh={forecastRefresh} />}
                    {activeTab === 'users' && <UserManagement />}
                </div>

                <footer className="main-footer">
                    <div className="footer-content">
                        <span>Système de Gestion de Caisse - Format compatible Sage</span>
                        <span className="footer-brand">Powered by OLEA Africa</span>
                    </div>
                </footer>
            </main>
        </div>
    );
}

export default App;