// src/contexts/AuthContext.js
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import ApiService from '../services/api';

const AuthContext = createContext(null);

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

    // Vérifier si l'utilisateur a la permission sur un module
    const hasPermission = (moduleName, action = 'read') => {
        if (!user) return false;
        if (user.role === 'superadmin') return true;
        const perm = user.permissions?.find(p => p.module_name === moduleName);
        if (!perm) return false;
        if (action === 'read') return perm.can_read;
        if (action === 'write') return perm.can_write;
        if (action === 'delete') return perm.can_delete;
        return false;
    };

    const value = {
        user,
        loading,
        login,
        logout,
        updateUser,
        isSuperAdmin,
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
