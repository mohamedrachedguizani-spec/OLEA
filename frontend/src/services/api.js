// src/services/api.js
const API_BASE_URL = 'http://localhost:8000';

class ApiService {

    // ===================== Helper : fetch avec credentials (cookies) =====================
    static _loggingOut = false;

    static async _fetch(url, options = {}) {
        const defaultOptions = {
            credentials: 'include',  // Envoie les cookies httpOnly à chaque requête
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        };

        // Ne pas forcer Content-Type pour FormData
        if (options.body instanceof FormData) {
            delete defaultOptions.headers['Content-Type'];
        }

        const response = await fetch(url, { ...defaultOptions, ...options, headers: { ...defaultOptions.headers, ...options.headers } });

        // Si 401, tenter un refresh automatique (sauf si logout en cours, ou si c'est /auth/refresh ou /auth/login)
        if (response.status === 401 && !ApiService._loggingOut && !url.includes('/auth/refresh') && !url.includes('/auth/login')) {
            const refreshed = await ApiService.refreshToken();
            if (refreshed) {
                // Retry la requête originale
                return fetch(url, { ...defaultOptions, ...options, headers: { ...defaultOptions.headers, ...options.headers } });
            }
            // Le refresh a échoué → session révoquée ou expirée → forcer la déconnexion immédiate
            window.dispatchEvent(new CustomEvent('auth:session-expired'));
        }

        return response;
    }

    // ===================== AUTHENTIFICATION =====================

    static async login(username, password) {
        const response = await fetch(`${API_BASE_URL}/auth/login`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur de connexion' }));
            throw new Error(err.detail || 'Erreur de connexion');
        }
        return response.json();
    }

    static async logout() {
        ApiService._loggingOut = true;
        try {
            const response = await fetch(`${API_BASE_URL}/auth/logout`, {
                method: 'POST',
                credentials: 'include',
            });
            return response.json();
        } finally {
            ApiService._loggingOut = false;
        }
    }

    static async refreshToken() {
        try {
            const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
                method: 'POST',
                credentials: 'include',
            });
            if (!response.ok) return false;
            return true;
        } catch {
            return false;
        }
    }

    static async sessionCheck() {
        try {
            const response = await fetch(`${API_BASE_URL}/auth/session-check`, {
                credentials: 'include',
            });
            return response.ok;
        } catch {
            return true; // En cas d'erreur réseau, ne pas déconnecter
        }
    }

    static async getMe() {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/me`);
        if (!response.ok) return null;
        return response.json();
    }

    static async changeMyPassword(currentPassword, newPassword) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/me/password`, {
            method: 'PUT',
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || 'Erreur lors du changement de mot de passe');
        }
        return response.json();
    }

    // ===================== GESTION UTILISATEURS (superadmin) =====================

    static async getUsers() {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users`);
        if (!response.ok) throw new Error('Erreur lors du chargement des utilisateurs');
        return response.json();
    }

    static async createUser(userData) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users`, {
            method: 'POST',
            body: JSON.stringify(userData),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || 'Erreur lors de la création');
        }
        return response.json();
    }

    static async updateUser(userId, userData) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify(userData),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || 'Erreur lors de la mise à jour');
        }
        return response.json();
    }

    static async deleteUser(userId) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}`, {
            method: 'DELETE',
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || 'Erreur lors de la suppression');
        }
        return response.json();
    }

    static async activateUser(userId) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}/activate`, {
            method: 'POST',
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || "Erreur lors de l'activation");
        }
        return response.json();
    }

    static async permanentDeleteUser(userId) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}/permanent`, {
            method: 'DELETE',
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || 'Erreur lors de la suppression définitive');
        }
        return response.json();
    }

    static async revokeUserSessions(userId) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}/revoke`, {
            method: 'POST',
        });
        if (!response.ok) throw new Error('Erreur lors de la révocation');
        return response.json();
    }

    static async resetUserPassword(userId, newPassword) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}/reset-password`, {
            method: 'PUT',
            body: JSON.stringify({ new_password: newPassword }),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || 'Erreur lors du reset');
        }
        return response.json();
    }

    static async getUserPermissions(userId) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}/permissions`);
        if (!response.ok) throw new Error('Erreur lors du chargement des permissions');
        return response.json();
    }

    static async setUserPermissions(userId, permissions) {
        const response = await ApiService._fetch(`${API_BASE_URL}/auth/users/${userId}/permissions`, {
            method: 'PUT',
            body: JSON.stringify({ permissions }),
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Erreur' }));
            throw new Error(err.detail || 'Erreur lors de la mise à jour des permissions');
        }
        return response.json();
    }
    // Écritures de caisse
    static async createEcritureCaisse(ecriture) {
        const response = await ApiService._fetch(`${API_BASE_URL}/ecritures-caisse/`, {
            method: 'POST',
            body: JSON.stringify(ecriture)
        });
        return response.json();
    }

    static async getEcrituresCaisse(params = {}) {
        const queryParams = new URLSearchParams(params).toString();
        const response = await ApiService._fetch(`${API_BASE_URL}/ecritures-caisse/?${queryParams}`);
        return response.json();
    }

    static async deleteEcritureCaisse(id) {
        const response = await ApiService._fetch(`${API_BASE_URL}/ecritures-caisse/${id}`, {
            method: 'DELETE'
        });
        return response.json();
    }

    // Suggestions de libellés
    static async getLibellesSuggestions(search) {
        const response = await ApiService._fetch(`${API_BASE_URL}/libelles-suggestions/?search=${search}`);
        return response.json();
    }

    // Migration
    static async getEcrituresAMigrer() {
        const response = await ApiService._fetch(`${API_BASE_URL}/ecritures-a-migrer/`);
        return response.json();
    }

    static async migrerEcriture(migrationData) {
        const response = await ApiService._fetch(`${API_BASE_URL}/migrer-ecriture/`, {
            method: 'POST',
            body: JSON.stringify(migrationData)
        });
        return response.json();
    }

    static async migrerTout(migrations) {
        const response = await ApiService._fetch(`${API_BASE_URL}/migrer-tout/`, {
            method: 'POST',
            body: JSON.stringify(migrations)
        });
        return response.json();
    }

    static async updateEcritureCaisse(id, ecriture) {
        const response = await ApiService._fetch(`${API_BASE_URL}/ecritures-caisse/${id}`, {
            method: 'PUT',
            body: JSON.stringify(ecriture)
        });
        return response.json();
    }

    // Écritures Sage
    static async getEcrituresSage(params = {}) {
        const queryParams = new URLSearchParams(params).toString();
        const response = await ApiService._fetch(`${API_BASE_URL}/ecritures-sage/?${queryParams}`);
        return response.json();
    }

    // Export CSV
    static async exportCSV(dateDebut = null, dateFin = null) {
        const params = {};
        if (dateDebut) params.date_debut = dateDebut;
        if (dateFin) params.date_fin = dateFin;
        
        const queryParams = new URLSearchParams(params).toString();
        const response = await ApiService._fetch(`${API_BASE_URL}/export-csv/?${queryParams}`);
        return response.json();
    }

    // Export Brouillard de Caisse
    static async exportBrouillardCaisse(dateDebut = null, dateFin = null) {
        const params = {};
        if (dateDebut) params.date_debut = dateDebut;
        if (dateFin) params.date_fin = dateFin;
        
        const queryParams = new URLSearchParams(params).toString();
        const response = await ApiService._fetch(`${API_BASE_URL}/export-brouillard-caisse/?${queryParams}`);
        return response.json();
    }

    // Comptes
    static async getComptes(search = '') {
        const response = await ApiService._fetch(`${API_BASE_URL}/comptes/?search=${search}`);
        return response.json();
    }

    // Vérification balance
    static async verifierBalance() {
        const response = await ApiService._fetch(`${API_BASE_URL}/verifier-balance/`);
        return response.json();
    }

    // Dashboard global — agrège tous les modules
    static async getGlobalDashboard(dateDebut = null, dateFin = null) {
        const params = {};
        if (dateDebut) params.date_debut = dateDebut;
        if (dateFin) params.date_fin = dateFin;
        
        const queryParams = new URLSearchParams(params).toString();
        const response = await ApiService._fetch(`${API_BASE_URL}/global-dashboard/?${queryParams}`);
        return response.json();
    }

    // Nettoyage automatique après migration
    static async nettoyerHistoriqueMigre() {
        const response = await ApiService._fetch(`${API_BASE_URL}/nettoyer-historique-migre/`, {
            method: 'POST',
        });
        return response.json();
    }

    // ===================== SAGE → BFC Parser =====================

    // Récupérer les stats du mapping
    static async getSageBfcMappingStats() {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/mapping/stats`);
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        return response.json();
    }

    // Parser un fichier balance SAGE (période obligatoire)
    static async parseSageBfcFile(file, periode) {
        const formData = new FormData();
        formData.append('file', file);

        const params = new URLSearchParams();
        params.append('periode', periode);

        const url = `${API_BASE_URL}/sage-bfc/parse?${params.toString()}`;

        const response = await ApiService._fetch(url, {
            method: 'POST',
            body: formData,
            headers: {},
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Erreur inconnue' }));
            throw new Error(error.detail || `Erreur ${response.status}`);
        }
        return response.json();
    }

    // ===================== CRUD Données mensuelles =====================

    // Récupérer la liste de tous les mois (résumés sans lignes)
    static async getSageBfcMonthlyList() {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/monthly`);
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        return response.json();
    }

    // Récupérer les données complètes d'un mois
    static async getSageBfcMonthlyDetail(periode) {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/monthly/${periode}`);
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        return response.json();
    }

    // Supprimer un mois
    static async deleteSageBfcMonth(periode) {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/monthly/${periode}`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        return response.json();
    }

    // Supprimer tous les mois
    static async deleteSageBfcAllMonths() {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/monthly`, {
            method: 'DELETE'
        });
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        return response.json();
    }

    // Récupérer un tableau BFC depuis le cache
    static async getSageBfcTableau(tableauId) {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/tableau/${tableauId}`);
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        return response.json();
    }

    // Exporter un tableau BFC en Excel
    static async exportSageBfcExcel(tableauId) {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/tableau/${tableauId}/export/excel`);
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `BFC_export.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }

    // Récupérer la config des validations interco
    static async getSageBfcValidationsConfig() {
        const response = await ApiService._fetch(`${API_BASE_URL}/sage-bfc/validations/config`);
        if (!response.ok) throw new Error(`Erreur ${response.status}: ${await response.text()}`);
        return response.json();
    }
}

export default ApiService;