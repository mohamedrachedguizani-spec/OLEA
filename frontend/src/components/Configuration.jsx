import React, { useEffect, useState, useCallback } from 'react';
import ApiService from '../services/api';

function Configuration() {
    const [form, setForm] = useState({ code_compte: '', libelle_compte: '' });
    const [search, setSearch] = useState('');
    const [comptes, setComptes] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');

    const loadComptes = useCallback(async () => {
        setLoading(true);
        try {
            const data = await ApiService.getConfigurationComptes(search);
            setComptes(Array.isArray(data) ? data : []);
        } catch (error) {
            setMessage(`Erreur lors du chargement: ${error.message}`);
        } finally {
            setLoading(false);
        }
    }, [search]);

    useEffect(() => {
        loadComptes();
    }, [loadComptes]);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setMessage('');

        const code = (form.code_compte || '').trim();
        const libelle = (form.libelle_compte || '').trim();

        if (!code || !libelle) {
            setMessage('Veuillez saisir le code compte et le libellé compte');
            return;
        }

        setSaving(true);
        try {
            await ApiService.createOrUpdateConfigurationCompte({
                code_compte: code,
                libelle_compte: libelle,
            });
            setMessage('Compte enregistré avec succès');
            setForm({ code_compte: '', libelle_compte: '' });
            await loadComptes();
        } catch (error) {
            setMessage(`Erreur lors de l\'enregistrement: ${error.message}`);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="olea-card fade-in">
            <div className="card-header">
                <h2 className="card-title">
                    <span className="icon">⚙️</span>
                    Configuration des Comptes
                </h2>
            </div>

            {message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

            <form className="olea-form mb-4" onSubmit={handleSubmit}>
                <div className="form-row">
                    <div className="form-col">
                        <div className="form-group">
                            <label>Code compte</label>
                            <input
                                type="text"
                                className="form-control"
                                value={form.code_compte}
                                onChange={(e) => setForm((prev) => ({ ...prev, code_compte: e.target.value }))}
                                placeholder="Ex: 5411000T"
                                required
                            />
                        </div>
                    </div>

                    <div className="form-col form-col-lg">
                        <div className="form-group">
                            <label>Libellé compte</label>
                            <input
                                type="text"
                                className="form-control"
                                value={form.libelle_compte}
                                onChange={(e) => setForm((prev) => ({ ...prev, libelle_compte: e.target.value }))}
                                placeholder="Ex: Caisse"
                                required
                            />
                        </div>
                    </div>

                    <div className="form-col form-col-btn">
                        <button type="submit" className="btn btn-primary" disabled={saving}>
                            {saving ? 'Enregistrement...' : 'Enregistrer'}
                        </button>
                    </div>
                </div>
            </form>

            <div className="section-header" style={{ marginBottom: '1rem' }}>
                <h3>
                    <span className="icon">📋</span>
                    Liste des comptes
                </h3>
                <span className="badge badge-primary">{comptes.length}</span>
            </div>

            <div className="form-row" style={{ marginBottom: '1rem' }}>
                <div className="form-col form-col-lg">
                    <input
                        type="text"
                        className="form-control"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Rechercher par code ou libellé..."
                    />
                </div>
                <div className="form-col form-col-btn">
                    <button type="button" className="btn btn-secondary" onClick={loadComptes} disabled={loading}>
                        {loading ? 'Actualisation...' : 'Rafraîchir'}
                    </button>
                </div>
            </div>

            <div className="table-responsive">
                <table className="olea-table">
                    <thead>
                        <tr>
                            <th>Code compte</th>
                            <th>Libellé compte</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="2" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Chargement...
                                </td>
                            </tr>
                        ) : comptes.length === 0 ? (
                            <tr>
                                <td colSpan="2" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Aucun compte trouvé
                                </td>
                            </tr>
                        ) : (
                            comptes.map((compte) => (
                                <tr key={compte.code_compte}>
                                    <td>{compte.code_compte}</td>
                                    <td>{compte.libelle_compte}</td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

export default Configuration;
