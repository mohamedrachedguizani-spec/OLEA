// src/contexts/AuthContext.js
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import ApiService from '../services/api';

const AuthContext = createContext(null);

const MODULE_PERMISSION_PREFIXES = {
    dashboard: ['dashboard.', 'admin.dashboard.'],
    saisie_caisse: ['saisie_caisse.'],
    export_csv: ['export_csv.'],
    saisie_bancaire: ['saisie_bancaire.'],
    rapprochement_bancaire: ['rapprochement_bancaire.'],
    sage_bfc: ['sage_bfc.', 'forecast.'],
    reporting: ['reporting.'],
    configuration: ['configuration.'],
    users: ['admin.users.'],
    audit: ['admin.audit.'],
};

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    // Vérifier la session au chargement (via cookie httpOnly)
    const checkSession = useCallback(async () => {
        try {
            const userData = await ApiService.getMe();
            setUser(userData);
        } catch {
            setUser(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        checkSession();
    }, [checkSession]);

    // Écouter l'événement de session expirée/révoquée pour déconnexion immédiate
    useEffect(() => {
        const handleSessionExpired = () => {
            setUser(null);
        };
        window.addEventListener('auth:session-expired', handleSessionExpired);
        return () => window.removeEventListener('auth:session-expired', handleSessionExpired);
    }, []);

    // Ce heartbeat ne recharge pas les droits. Il sert uniquement au suivi
    // des sessions actives et à la détection des révocations.
    useEffect(() => {
        if (!user) return;
        const heartbeat = setInterval(async () => {
            const valid = await ApiService.sessionCheck();
            if (!valid) {
                setUser(null);
            }
        }, 15 * 1000);
        return () => clearInterval(heartbeat);
    }, [user]);

    // Refresh automatique du token toutes les 13 minutes
    useEffect(() => {
        if (!user) return;
        const interval = setInterval(async () => {
            const ok = await ApiService.refreshToken();
            if (!ok) {
                setUser(null);
            }
        }, 13 * 60 * 1000); // 13 min (token expire à 15 min)
        return () => clearInterval(interval);
    }, [user]);

    const login = async (username, password) => {
        const data = await ApiService.login(username, password);
        setUser(data.user);
        return data;
    };

    const logout = async () => {
        setUser(null); // Vider immédiatement pour forcer l'écran login
        try {
            await ApiService.logout();
        } catch {
            // Ignorer les erreurs réseau au logout
        }
    };

    const updateUser = (updatedUser) => {
        setUser(updatedUser);
    };

    // Helpers de rôle
    const isSuperAdmin = user?.role === 'superadmin';

    const has = useCallback(
        (permissionCode) => Boolean(user?.permission_codes?.includes(permissionCode)),
        [user],
    );
    const hasAny = useCallback((...permissionCodes) => permissionCodes.some(has), [has]);

    // Compatibilité avec les composants encore filtrés par nom de module.
    const hasPermission = useCallback((moduleName, action = 'read') => {
        if (!user) return false;
        const prefixes = MODULE_PERMISSION_PREFIXES[moduleName] || [`${moduleName}.`];
        const codes = user.permission_codes || [];
        return codes.some((code) => prefixes.some((prefix) => code.startsWith(prefix)));
    }, [user]);

    const value = {
        user,
        loading,
        login,
        logout,
        updateUser,
        isSuperAdmin,
        has,
        hasAny,
        hasPermission,
        checkSession,
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth doit être utilisé dans un AuthProvider');
    }
    return context;
}

export default AuthContext;
