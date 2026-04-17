// src/components/UserManagement.js
import React, { useState, useEffect, useCallback } from 'react';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const ROLES = [
    { value: 'comptable', label: 'Comptable', color: '#2f343a' },
    { value: 'financier', label: 'Financier', color: '#b7482b' },
    { value: 'dirigeant', label: 'Dirigeant', color: '#d4a528' },
    { value: 'superadmin', label: 'Super Admin', color: '#863421' },
];

const MODULES = [
    { name: 'saisie_caisse', label: 'Saisie Caisse', icon: '✏️' },
    { name: 'migration_sage', label: 'Migration Sage', icon: '📤' },
    { name: 'export_csv', label: 'Export CSV', icon: '📁' },
    { name: 'sage_bfc', label: 'SAGE → BFC', icon: '🔄' },
    { name: 'reporting', label: 'Reporting', icon: '📊' },
];

const PASSWORD_POLICY_HINT = '8+ caractères, 1 majuscule, 1 minuscule, 1 chiffre, 1 caractère spécial, sans espaces';
const PASSWORD_POLICY_REGEX = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9])\S{8,128}$/;

function UserManagement() {
    const { user: currentUser } = useAuth();
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    // Modals
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [showEditModal, setShowEditModal] = useState(false);
    const [showPermissionsModal, setShowPermissionsModal] = useState(false);
    const [showResetPasswordModal, setShowResetPasswordModal] = useState(false);
    const [selectedUser, setSelectedUser] = useState(null);

    // Create form
    const [createForm, setCreateForm] = useState({
        username: '', email: '', full_name: '', password: '', role: 'comptable',
    });

    // Edit form
    const [editForm, setEditForm] = useState({
        email: '', full_name: '', role: '', is_active: true,
    });

    // Permissions form
    const [permissionsForm, setPermissionsForm] = useState([]);

    // Reset password
    const [newPassword, setNewPassword] = useState('');

    const clearMessages = () => { setError(''); setSuccess(''); };

    const loadUsers = useCallback(async () => {
        try {
            setLoading(true);
            const data = await ApiService.getUsers();
            setUsers(data);
        } catch (err) {
            setError('Erreur lors du chargement des utilisateurs');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadUsers(); }, [loadUsers]);

    // Auto-clear messages
    useEffect(() => {
        if (success || error) {
            const timer = setTimeout(() => { setSuccess(''); setError(''); }, 4000);
            return () => clearTimeout(timer);
        }
    }, [success, error]);

    // ─── Create ───
    const handleCreate = async (e) => {
        e.preventDefault();
        clearMessages();
        if (!PASSWORD_POLICY_REGEX.test(createForm.password)) {
            setError(`Mot de passe invalide: ${PASSWORD_POLICY_HINT}`);
            return;
        }
        try {
            await ApiService.createUser(createForm);
            setSuccess('Utilisateur créé avec succès');
            setShowCreateModal(false);
            setCreateForm({ username: '', email: '', full_name: '', password: '', role: 'comptable' });
            loadUsers();
        } catch (err) {
            setError(err.message);
        }
    };

    // ─── Edit ───
    const openEditModal = (user) => {
        setSelectedUser(user);
        setEditForm({
            email: user.email,
            full_name: user.full_name,
            role: user.role,
            is_active: user.is_active,
        });
        setShowEditModal(true);
    };

    const handleEdit = async (e) => {
        e.preventDefault();
        clearMessages();
        try {
            await ApiService.updateUser(selectedUser.id, editForm);
            setSuccess('Utilisateur modifié avec succès');
            setShowEditModal(false);
            loadUsers();
        } catch (err) {
            setError(err.message);
        }
    };

    // ─── Permissions ───
    const openPermissionsModal = (user) => {
        setSelectedUser(user);
        const perms = MODULES.map(mod => {
            const existing = user.permissions?.find(p => p.module_name === mod.name);
            return {
                module_name: mod.name,
                can_read: existing?.can_read || false,
                can_write: existing?.can_write || false,
                can_delete: existing?.can_delete || false,
            };
        });
        setPermissionsForm(perms);
        setShowPermissionsModal(true);
    };

    const togglePermission = (moduleIndex, action) => {
        setPermissionsForm(prev => {
            const updated = [...prev];
            updated[moduleIndex] = { ...updated[moduleIndex], [action]: !updated[moduleIndex][action] };
            return updated;
        });
    };

    const handleSavePermissions = async () => {
        clearMessages();
        try {
            await ApiService.setUserPermissions(selectedUser.id, permissionsForm);
            setSuccess(`Permissions de ${selectedUser.full_name} mises à jour`);
            setShowPermissionsModal(false);
            loadUsers();
        } catch (err) {
            setError(err.message);
        }
    };

    // ─── Reset Password ───
    const openResetPasswordModal = (user) => {
        setSelectedUser(user);
        setNewPassword('');
        setShowResetPasswordModal(true);
    };

    const handleResetPassword = async (e) => {
        e.preventDefault();
        clearMessages();
        if (!PASSWORD_POLICY_REGEX.test(newPassword)) {
            setError(`Mot de passe invalide: ${PASSWORD_POLICY_HINT}`);
            return;
        }
        try {
            await ApiService.resetUserPassword(selectedUser.id, newPassword);
            setSuccess(`Mot de passe de ${selectedUser.full_name} réinitialisé`);
            setShowResetPasswordModal(false);
        } catch (err) {
            setError(err.message);
        }
    };

    // ─── Toggle Activer / Désactiver ───
    const handleToggleActive = async (user) => {
        if (user.is_active) {
            if (!window.confirm(`Désactiver l'utilisateur "${user.full_name}" ? Il ne pourra plus se connecter.`)) return;
            clearMessages();
            try {
                await ApiService.deleteUser(user.id);
                setSuccess(`${user.full_name} a été désactivé`);
                loadUsers();
            } catch (err) {
                setError(err.message);
            }
        } else {
            if (!window.confirm(`Réactiver l'utilisateur "${user.full_name}" ? Il pourra se reconnecter.`)) return;
            clearMessages();
            try {
                await ApiService.activateUser(user.id);
                setSuccess(`${user.full_name} a été réactivé`);
                loadUsers();
            } catch (err) {
                setError(err.message);
            }
        }
    };

    // ─── Supprimer définitivement ───
    const handlePermanentDelete = async (user) => {
        if (!window.confirm(`⚠️ ATTENTION : Supprimer définitivement l'utilisateur "${user.full_name}" ?\n\nCette action est IRRÉVERSIBLE. Toutes ses données seront perdues.`)) return;
        clearMessages();
        try {
            await ApiService.permanentDeleteUser(user.id);
            setSuccess(`${user.full_name} a été supprimé définitivement`);
            loadUsers();
        } catch (err) {
            setError(err.message);
        }
    };

    // ─── Revoke Sessions ───
    const handleRevoke = async (user) => {
        if (!window.confirm(`Révoquer toutes les sessions de "${user.full_name}" ?`)) return;
        clearMessages();
        try {
            await ApiService.revokeUserSessions(user.id);
            setSuccess(`Sessions de ${user.full_name} révoquées`);
        } catch (err) {
            setError(err.message);
        }
    };

    const getRoleBadge = (role) => {
        const r = ROLES.find(x => x.value === role);
        return (
            <span className="um-role-badge" style={{ background: `${r?.color}20`, color: r?.color, borderColor: `${r?.color}40` }}>
                {r?.label || role}
            </span>
        );
    };

    if (loading) {
        return (
            <div className="um-loading">
                <div className="um-spinner"></div>
                <p>Chargement des utilisateurs…</p>
            </div>
        );
    }

    return (
        <div className="um-container">
            {/* Header */}
            <div className="um-header">
                <div>
                    <h2 className="um-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="28" height="28">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
                            <circle cx="9" cy="7" r="4"/>
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
                        </svg>
                        Gestion des Utilisateurs
                    </h2>
                    <p className="um-subtitle">{users.length} utilisateur{users.length > 1 ? 's' : ''} enregistré{users.length > 1 ? 's' : ''}</p>
                </div>
                <button className="um-btn um-btn-primary" onClick={() => { clearMessages(); setShowCreateModal(true); }}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="18" height="18">
                        <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                    </svg>
                    Nouvel Utilisateur
                </button>
            </div>

            {/* Messages */}
            {error && <div className="um-alert um-alert-error"><span>⚠️</span> {error}</div>}
            {success && <div className="um-alert um-alert-success"><span>✅</span> {success}</div>}

            {/* Table */}
            <div className="um-table-wrapper">
                <table className="um-table">
                    <thead>
                        <tr>
                            <th>Utilisateur</th>
                            <th>Email</th>
                            <th>Rôle</th>
                            <th>Statut</th>
                            <th>Sessions</th>
                            <th>Permissions</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {users.map(u => (
                            <tr key={u.id} className={!u.is_active ? 'um-row-inactive' : ''}>
                                <td>
                                    <div className="um-user-cell">
                                        <div className="um-avatar" style={{ background: ROLES.find(r => r.value === u.role)?.color || '#666' }}>
                                            {u.full_name.charAt(0).toUpperCase()}
                                        </div>
                                        <div>
                                            <div className="um-user-name">{u.full_name}</div>
                                            <div className="um-user-username">@{u.username}</div>
                                        </div>
                                    </div>
                                </td>
                                <td><span className="um-email">{u.email}</span></td>
                                <td>{getRoleBadge(u.role)}</td>
                                <td>
                                    <span className={`um-status-badge ${u.is_active ? 'um-status-active' : 'um-status-inactive'}`}>
                                        {u.is_active ? 'Actif' : 'Inactif'}
                                    </span>
                                </td>
                                <td>
                                    {(u.active_sessions || 0) > 0 ? (
                                        <span className="um-sessions-badge">
                                            <span className="um-sessions-dot"></span>
                                            {u.active_sessions} session{u.active_sessions > 1 ? 's' : ''}
                                        </span>
                                    ) : (
                                        <span className="um-text-muted">—</span>
                                    )}
                                </td>
                                <td>
                                    {u.role === 'superadmin' ? (
                                        <span className="um-text-muted">Toutes</span>
                                    ) : (
                                        <div className="um-perm-pills">
                                            {u.permissions?.filter(p => p.can_read || p.can_write || p.can_delete).length > 0 ? (
                                                u.permissions.filter(p => p.can_read || p.can_write || p.can_delete).map(p => (
                                                    <span key={p.module_name} className="um-perm-pill" title={`R:${p.can_read ? '✓' : '✗'} W:${p.can_write ? '✓' : '✗'} D:${p.can_delete ? '✓' : '✗'}`}>
                                                        {MODULES.find(m => m.name === p.module_name)?.icon} {MODULES.find(m => m.name === p.module_name)?.label?.split(' ')[0]}
                                                    </span>
                                                ))
                                            ) : (
                                                <span className="um-text-muted">Aucune</span>
                                            )}
                                        </div>
                                    )}
                                </td>
                                <td>
                                    <div className="um-actions">
                                        {u.role !== 'superadmin' && (
                                            <button className="um-action-btn um-action-perms" onClick={() => openPermissionsModal(u)} title="Permissions">
                                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                                                </svg>
                                            </button>
                                        )}
                                        <button className="um-action-btn um-action-edit" onClick={() => openEditModal(u)} title="Modifier">
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                                <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                                            </svg>
                                        </button>
                                        <button className="um-action-btn um-action-password" onClick={() => openResetPasswordModal(u)} title="Reset mot de passe">
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                            </svg>
                                        </button>
                                        {u.id !== currentUser?.id && (
                                            <>
                                                <button className="um-action-btn um-action-revoke" onClick={() => handleRevoke(u)} title="Révoquer sessions">
                                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                                        <circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>
                                                    </svg>
                                                </button>
                                                <button
                                                    className={`um-action-btn ${u.is_active ? 'um-action-delete' : 'um-action-activate'}`}
                                                    onClick={() => handleToggleActive(u)}
                                                    title={u.is_active ? 'Désactiver' : 'Activer'}
                                                >
                                                    {u.is_active ? (
                                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><line x1="23" y1="18" x2="17" y2="12"/><line x1="17" y1="18" x2="23" y2="12"/>
                                                        </svg>
                                                    ) : (
                                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                                                        </svg>
                                                    )}
                                                </button>
                                                <button className="um-action-btn um-action-permanent-delete" onClick={() => handlePermanentDelete(u)} title="Supprimer définitivement">
                                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16">
                                                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>
                                                    </svg>
                                                </button>
                                            </>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* ═══ Modal : Créer ═══ */}
            {showCreateModal && (
                <div className="um-modal-overlay" onClick={() => setShowCreateModal(false)}>
                    <div className="um-modal" onClick={e => e.stopPropagation()}>
                        <div className="um-modal-header">
                            <h3>Nouvel Utilisateur</h3>
                            <button className="um-modal-close" onClick={() => setShowCreateModal(false)}>×</button>
                        </div>
                        <form onSubmit={handleCreate}>
                            <div className="um-modal-body">
                                <div className="um-form-group">
                                    <label>Nom complet</label>
                                    <input type="text" value={createForm.full_name} onChange={e => setCreateForm({...createForm, full_name: e.target.value})} required placeholder="Ex: Mohamed Diallo" />
                                </div>
                                <div className="um-form-row">
                                    <div className="um-form-group">
                                        <label>Nom d'utilisateur</label>
                                        <input type="text" value={createForm.username} onChange={e => setCreateForm({...createForm, username: e.target.value})} required placeholder="Ex: m.diallo" />
                                    </div>
                                    <div className="um-form-group">
                                        <label>Email</label>
                                        <input type="email" value={createForm.email} onChange={e => setCreateForm({...createForm, email: e.target.value})} required placeholder="Ex: m.diallo@olea.com" />
                                    </div>
                                </div>
                                <div className="um-form-row">
                                    <div className="um-form-group">
                                        <label>Mot de passe</label>
                                        <input
                                            type="password"
                                            value={createForm.password}
                                            onChange={e => setCreateForm({...createForm, password: e.target.value})}
                                            required
                                            minLength={8}
                                            pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9])\S{8,128}"
                                            title={PASSWORD_POLICY_HINT}
                                            placeholder={PASSWORD_POLICY_HINT}
                                        />
                                    </div>
                                    <div className="um-form-group">
                                        <label>Rôle</label>
                                        <select value={createForm.role} onChange={e => setCreateForm({...createForm, role: e.target.value})}>
                                            <option value="comptable">Comptable</option>
                                            <option value="financier">Financier</option>
                                            <option value="dirigeant">Dirigeant</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div className="um-modal-footer">
                                <button type="button" className="um-btn um-btn-secondary" onClick={() => setShowCreateModal(false)}>Annuler</button>
                                <button type="submit" className="um-btn um-btn-primary">Créer l'utilisateur</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ═══ Modal : Modifier ═══ */}
            {showEditModal && selectedUser && (
                <div className="um-modal-overlay" onClick={() => setShowEditModal(false)}>
                    <div className="um-modal" onClick={e => e.stopPropagation()}>
                        <div className="um-modal-header">
                            <h3>Modifier — {selectedUser.full_name}</h3>
                            <button className="um-modal-close" onClick={() => setShowEditModal(false)}>×</button>
                        </div>
                        <form onSubmit={handleEdit}>
                            <div className="um-modal-body">
                                <div className="um-form-group">
                                    <label>Nom complet</label>
                                    <input type="text" value={editForm.full_name} onChange={e => setEditForm({...editForm, full_name: e.target.value})} />
                                </div>
                                <div className="um-form-group">
                                    <label>Email</label>
                                    <input type="email" value={editForm.email} onChange={e => setEditForm({...editForm, email: e.target.value})} />
                                </div>
                                <div className="um-form-row">
                                    <div className="um-form-group">
                                        <label>Rôle</label>
                                        <select value={editForm.role} onChange={e => setEditForm({...editForm, role: e.target.value})}>
                                            <option value="comptable">Comptable</option>
                                            <option value="financier">Financier</option>
                                            <option value="dirigeant">Dirigeant</option>
                                            <option value="superadmin">Super Admin</option>
                                        </select>
                                    </div>
                                    <div className="um-form-group">
                                        <label>Statut</label>
                                        <select value={editForm.is_active ? 'true' : 'false'} onChange={e => setEditForm({...editForm, is_active: e.target.value === 'true'})}>
                                            <option value="true">Actif</option>
                                            <option value="false">Inactif</option>
                                        </select>
                                    </div>
                                </div>
                            </div>
                            <div className="um-modal-footer">
                                <button type="button" className="um-btn um-btn-secondary" onClick={() => setShowEditModal(false)}>Annuler</button>
                                <button type="submit" className="um-btn um-btn-primary">Enregistrer</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ═══ Modal : Permissions ═══ */}
            {showPermissionsModal && selectedUser && (
                <div className="um-modal-overlay" onClick={() => setShowPermissionsModal(false)}>
                    <div className="um-modal um-modal-wide" onClick={e => e.stopPropagation()}>
                        <div className="um-modal-header">
                            <h3>Permissions — {selectedUser.full_name}</h3>
                            <button className="um-modal-close" onClick={() => setShowPermissionsModal(false)}>×</button>
                        </div>
                        <div className="um-modal-body">
                            <p className="um-perm-hint">Cochez les droits d'accès pour chaque module de l'application.</p>
                            <table className="um-perm-table">
                                <thead>
                                    <tr>
                                        <th>Module</th>
                                        <th>Lecture</th>
                                        <th>Écriture</th>
                                        <th>Suppression</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {MODULES.map((mod, idx) => (
                                        <tr key={mod.name}>
                                            <td>
                                                <span className="um-perm-module">
                                                    {mod.icon} {mod.label}
                                                </span>
                                            </td>
                                            <td>
                                                <label className="um-checkbox">
                                                    <input type="checkbox" checked={permissionsForm[idx]?.can_read || false} onChange={() => togglePermission(idx, 'can_read')} />
                                                    <span className="um-checkmark"></span>
                                                </label>
                                            </td>
                                            <td>
                                                <label className="um-checkbox">
                                                    <input type="checkbox" checked={permissionsForm[idx]?.can_write || false} onChange={() => togglePermission(idx, 'can_write')} />
                                                    <span className="um-checkmark"></span>
                                                </label>
                                            </td>
                                            <td>
                                                <label className="um-checkbox">
                                                    <input type="checkbox" checked={permissionsForm[idx]?.can_delete || false} onChange={() => togglePermission(idx, 'can_delete')} />
                                                    <span className="um-checkmark"></span>
                                                </label>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="um-modal-footer">
                            <button className="um-btn um-btn-secondary" onClick={() => setShowPermissionsModal(false)}>Annuler</button>
                            <button className="um-btn um-btn-primary" onClick={handleSavePermissions}>Enregistrer les permissions</button>
                        </div>
                    </div>
                </div>
            )}

            {/* ═══ Modal : Reset Password ═══ */}
            {showResetPasswordModal && selectedUser && (
                <div className="um-modal-overlay" onClick={() => setShowResetPasswordModal(false)}>
                    <div className="um-modal um-modal-sm" onClick={e => e.stopPropagation()}>
                        <div className="um-modal-header">
                            <h3>Réinitialiser le mot de passe</h3>
                            <button className="um-modal-close" onClick={() => setShowResetPasswordModal(false)}>×</button>
                        </div>
                        <form onSubmit={handleResetPassword}>
                            <div className="um-modal-body">
                                <p className="um-text-muted">Pour : <strong>{selectedUser.full_name}</strong> (@{selectedUser.username})</p>
                                <div className="um-form-group">
                                    <label>Nouveau mot de passe</label>
                                    <input
                                        type="password"
                                        value={newPassword}
                                        onChange={e => setNewPassword(e.target.value)}
                                        required
                                        minLength={8}
                                        pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9])\S{8,128}"
                                        title={PASSWORD_POLICY_HINT}
                                        placeholder={PASSWORD_POLICY_HINT}
                                    />
                                </div>
                                <p className="um-perm-hint">⚠️ Toutes les sessions existantes seront révoquées.</p>
                            </div>
                            <div className="um-modal-footer">
                                <button type="button" className="um-btn um-btn-secondary" onClick={() => setShowResetPasswordModal(false)}>Annuler</button>
                                <button type="submit" className="um-btn um-btn-primary">Réinitialiser</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}

export default UserManagement;
