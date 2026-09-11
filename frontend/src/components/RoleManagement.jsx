import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';

function RoleManagement() {
    const { has } = useAuth();
    const [roles, setRoles] = useState([]);
    const [permissions, setPermissions] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [checked, setChecked] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const [roleData, permissionData] = await Promise.all([
                ApiService.getAccessRoles(),
                ApiService.getAccessPermissions(),
            ]);
            setRoles(roleData);
            setPermissions(permissionData);
            setSelectedId((current) => current || roleData[0]?.id || null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadData(); }, [loadData]);

    const selectedRole = roles.find((role) => role.id === selectedId);
    useEffect(() => {
        setChecked(selectedRole?.permission_codes || []);
        setMessage('');
        setError('');
    }, [selectedRole?.id, selectedRole?.permission_codes]);

    const groups = useMemo(() => permissions.reduce((acc, permission) => {
        if (!acc[permission.module]) acc[permission.module] = [];
        acc[permission.module].push(permission);
        return acc;
    }, {}), [permissions]);

    const togglePermission = (code) => {
        setChecked((current) => current.includes(code)
            ? current.filter((item) => item !== code)
            : [...current, code]);
    };

    const handleSave = async () => {
        if (!selectedRole) return;
        setSaving(true);
        setMessage('');
        setError('');
        try {
            const updated = await ApiService.updateAccessRolePermissions(selectedRole.id, checked);
            setRoles((current) => current.map((role) => role.id === updated.id ? updated : role));
            setMessage('Les permissions du profil ont été enregistrées.');
        } catch (err) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    };

    if (loading) return <div className="loading-container"><div className="spinner" /></div>;

    const protectedRole = selectedRole?.code === 'SUPER_ADMIN';
    const canManage = has('admin.roles.manage') && !protectedRole;

    return (
        <div className="access-page fade-in">
            <div className="um-header">
                <div>
                    <h2 className="um-title">Profils et permissions</h2>
                    <p className="um-subtitle">Configurez le périmètre fonctionnel attribué aux acteurs de l'application.</p>
                </div>
                {canManage && (
                    <button className="um-btn um-btn-primary" onClick={handleSave} disabled={saving}>
                        {saving ? 'Enregistrement...' : 'Enregistrer les permissions'}
                    </button>
                )}
            </div>

            {error && <div className="um-alert um-alert-error">{error}</div>}
            {message && <div className="um-alert um-alert-success">{message}</div>}

            <div className="access-layout">
                <aside className="access-role-list">
                    <div className="access-panel-title">Profils disponibles</div>
                    {roles.map((role) => (
                        <button
                            key={role.id}
                            className={`access-role-item ${role.id === selectedId ? 'active' : ''}`}
                            onClick={() => setSelectedId(role.id)}
                        >
                            <span className="access-role-shield">◇</span>
                            <span>
                                <strong>{role.name}</strong>
                                <small>{role.permission_codes.length} permission(s)</small>
                            </span>
                        </button>
                    ))}
                </aside>

                <section className="access-permission-panel">
                    {selectedRole && (
                        <>
                            <div className="access-profile-heading">
                                <div>
                                    <span className="access-eyebrow">Périmètre du profil</span>
                                    <h3>{selectedRole.name}</h3>
                                    <p>{selectedRole.description}</p>
                                </div>
                                {protectedRole && <span className="access-locked">Profil protégé</span>}
                            </div>
                            <div className="access-groups">
                                {Object.entries(groups).map(([module, items]) => (
                                    <div className="access-group" key={module}>
                                        <h4>{module}</h4>
                                        {items.map((permission) => {
                                            const active = checked.includes(permission.code);
                                            return (
                                                <label className={`access-permission-row ${active ? 'active' : ''}`} key={permission.code}>
                                                    <input
                                                        type="checkbox"
                                                        checked={active}
                                                        disabled={!canManage}
                                                        onChange={() => togglePermission(permission.code)}
                                                    />
                                                    <span className="access-check">{active ? '✓' : ''}</span>
                                                    <span>
                                                        <strong>{permission.name}</strong>
                                                        <code>{permission.code}</code>
                                                    </span>
                                                </label>
                                            );
                                        })}
                                    </div>
                                ))}
                            </div>
                        </>
                    )}
                </section>
            </div>
        </div>
    );
}

export default RoleManagement;
