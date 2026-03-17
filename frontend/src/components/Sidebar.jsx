// src/components/Sidebar.jsx
import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import ApiService from '../services/api';

function Sidebar({ activeTab, setActiveTab, darkMode, setDarkMode, sidebarOpen, setSidebarOpen }) {
    const { user, logout, isSuperAdmin, hasPermission } = useAuth();
    const [showPasswordModal, setShowPasswordModal] = useState(false);
    const [showSettingsMenu, setShowSettingsMenu] = useState(false);
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPasswordVal, setNewPasswordVal] = useState('');
    const [pwdError, setPwdError] = useState('');
    const [pwdSuccess, setPwdSuccess] = useState('');
    const [pwdLoading, setPwdLoading] = useState(false);

    // Menu items filtrés selon les permissions de l'utilisateur
    const allMenuItems = [
        { id: 'dashboard', label: 'Tableau de Bord', icon: 'dashboard', alwaysVisible: true },
        { id: 'saisie', label: 'Saisie Caisse', icon: 'edit', module: 'saisie_caisse' },
        { id: 'migration', label: 'Migration Sage', icon: 'sync', module: 'migration_sage' },
        { id: 'export', label: 'Export CSV', icon: 'download', module: 'export_csv' },
        { id: 'sage-bfc', label: 'SAGE → BFC', icon: 'transform', module: 'sage_bfc' },
    ];

    // Filtrer : superadmin voit tout, les autres selon permissions
    const menuItems = allMenuItems.filter(item => {
        if (item.alwaysVisible) return true;
        if (isSuperAdmin) return true;
        return hasPermission(item.module, 'read');
    });

    const getIcon = (iconName) => {
        const icons = {
            dashboard: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="7" height="7" rx="1"/>
                    <rect x="14" y="3" width="7" height="7" rx="1"/>
                    <rect x="3" y="14" width="7" height="7" rx="1"/>
                    <rect x="14" y="14" width="7" height="7" rx="1"/>
                </svg>
            ),
            edit: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 20h9"/>
                    <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                </svg>
            ),
            sync: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M23 4v6h-6"/>
                    <path d="M1 20v-6h6"/>
                    <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                </svg>
            ),
            download: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7,10 12,15 17,10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                </svg>
            ),
            transform: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="16,3 21,3 21,8"/>
                    <line x1="4" y1="20" x2="21" y2="3"/>
                    <polyline points="21,16 21,21 16,21"/>
                    <line x1="15" y1="15" x2="21" y2="21"/>
                    <line x1="4" y1="4" x2="9" y2="9"/>
                </svg>
            ),
            users: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                    <circle cx="9" cy="7" r="4"/>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                </svg>
            ),
        };
        return icons[iconName];
    };

    return (
        <>
            <div 
                className={`sidebar-overlay ${sidebarOpen ? 'active' : ''}`}
                onClick={() => setSidebarOpen(false)}
            />
            
            <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
                {/* Logo Section */}
                <div className="sidebar-brand">
                    <div className="brand-logo">
                        <span className="logo-letter">O</span>
                    </div>
                    <div className="brand-info">
                        <span className="brand-name">OLEA</span>
                        <span className="brand-tagline">Finance Manager</span>
                    </div>
                    <button className="sidebar-close" onClick={() => setSidebarOpen(false)}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18"/>
                            <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                    </button>
                </div>

                {/* Navigation */}
                <nav className="sidebar-menu">
                    <div className="menu-section">
                        <span className="menu-title">Navigation</span>
                        <ul className="menu-list">
                            {menuItems.map(item => (
                                <li key={item.id}>
                                    <button
                                        className={`menu-item ${activeTab === item.id ? 'active' : ''}`}
                                        onClick={() => {
                                            setActiveTab(item.id);
                                            setSidebarOpen(false);
                                        }}
                                    >
                                        <span className="menu-icon">{getIcon(item.icon)}</span>
                                        <span className="menu-label">{item.label}</span>
                                        {activeTab === item.id && <span className="menu-active-dot"></span>}
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </div>

                    {/* Section Administration — superadmin uniquement */}
                    {isSuperAdmin && (
                        <div className="menu-section">
                            <span className="menu-title">Administration</span>
                            <ul className="menu-list">
                                <li>
                                    <button
                                        className={`menu-item ${activeTab === 'users' ? 'active' : ''}`}
                                        onClick={() => { setActiveTab('users'); setSidebarOpen(false); }}
                                    >
                                        <span className="menu-icon">{getIcon('users')}</span>
                                        <span className="menu-label">Utilisateurs</span>
                                        {activeTab === 'users' && <span className="menu-active-dot"></span>}
                                    </button>
                                </li>
                            </ul>
                        </div>
                    )}
                </nav>

                {/* Footer */}
                <div className="sidebar-bottom">
                    {/* Settings icon with dropdown */}
                    <div className="sidebar-settings-wrapper">
                        <button 
                            className="sidebar-settings-btn"
                            onClick={() => setShowSettingsMenu(prev => !prev)}
                            title="Paramètres"
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="20" height="20">
                                <circle cx="12" cy="12" r="3"/>
                                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                            </svg>
                            <span>Paramètres</span>
                        </button>

                        {showSettingsMenu && (
                            <div className="sidebar-settings-dropdown">
                                <button className="sidebar-dropdown-item" onClick={() => { setShowPasswordModal(true); setShowSettingsMenu(false); }}>
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                    </svg>
                                    Changer mot de passe
                                </button>
                                <div className="sidebar-dropdown-divider"></div>
                                <button className="sidebar-dropdown-item sidebar-dropdown-logout" onClick={() => { setShowSettingsMenu(false); logout(); }}>
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                                        <polyline points="16 17 21 12 16 7"/>
                                        <line x1="21" y1="12" x2="9" y2="12"/>
                                    </svg>
                                    Déconnexion
                                </button>
                            </div>
                        )}
                    </div>

                    <div className="theme-switcher">
                        <button 
                            className={`theme-btn ${!darkMode ? 'active' : ''}`}
                            onClick={() => setDarkMode(false)}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <circle cx="12" cy="12" r="5"/>
                                <line x1="12" y1="1" x2="12" y2="3"/>
                                <line x1="12" y1="21" x2="12" y2="23"/>
                                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                                <line x1="1" y1="12" x2="3" y2="12"/>
                                <line x1="21" y1="12" x2="23" y2="12"/>
                                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                            </svg>
                        </button>
                        <button 
                            className={`theme-btn ${darkMode ? 'active' : ''}`}
                            onClick={() => setDarkMode(true)}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
                            </svg>
                        </button>
                    </div>
                    <div className="sidebar-copyright">
                        <span>© 2026 OLEA Africa</span>
                    </div>
                </div>

                {/* Modal : Changer mot de passe */}
                {showPasswordModal && (
                    <div className="um-modal-overlay" onClick={() => setShowPasswordModal(false)}>
                        <div className="um-modal um-modal-sm" onClick={e => e.stopPropagation()}>
                            <div className="um-modal-header">
                                <h3>Changer mon mot de passe</h3>
                                <button className="um-modal-close" onClick={() => { setShowPasswordModal(false); setPwdError(''); setPwdSuccess(''); }}>×</button>
                            </div>
                            <form onSubmit={async (e) => {
                                e.preventDefault();
                                setPwdError(''); setPwdSuccess(''); setPwdLoading(true);
                                try {
                                    await ApiService.changeMyPassword(currentPassword, newPasswordVal);
                                    setPwdSuccess('Mot de passe modifié avec succès');
                                    setCurrentPassword(''); setNewPasswordVal('');
                                    setTimeout(() => setShowPasswordModal(false), 1500);
                                } catch (err) {
                                    setPwdError(err.message);
                                } finally { setPwdLoading(false); }
                            }}>
                                <div className="um-modal-body">
                                    {pwdError && <div className="um-alert um-alert-error"><span>⚠️</span> {pwdError}</div>}
                                    {pwdSuccess && <div className="um-alert um-alert-success"><span>✅</span> {pwdSuccess}</div>}
                                    <div className="um-form-group">
                                        <label>Mot de passe actuel</label>
                                        <input type="password" value={currentPassword} onChange={e => setCurrentPassword(e.target.value)} required />
                                    </div>
                                    <div className="um-form-group">
                                        <label>Nouveau mot de passe</label>
                                        <input type="password" value={newPasswordVal} onChange={e => setNewPasswordVal(e.target.value)} required minLength={6} placeholder="Min. 6 caractères" />
                                    </div>
                                </div>
                                <div className="um-modal-footer">
                                    <button type="button" className="um-btn um-btn-secondary" onClick={() => setShowPasswordModal(false)}>Annuler</button>
                                    <button type="submit" className="um-btn um-btn-primary" disabled={pwdLoading}>
                                        {pwdLoading ? 'En cours…' : 'Modifier'}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </aside>
        </>
    );
}

export default Sidebar;
