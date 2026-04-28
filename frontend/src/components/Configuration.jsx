import React, { useEffect, useState, useCallback } from 'react';
import ApiService from '../services/api';

function Configuration() {
    const [form, setForm] = useState({ code_compte: '', libelle_compte: '' });
    const [search, setSearch] = useState('');
    const [comptes, setComptes] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [message, setMessage] = useState('');
    const [editingCode, setEditingCode] = useState(null);
    const [editForm, setEditForm] = useState({ code_compte: '', libelle_compte: '' });
    const [page, setPage] = useState(1);
    const [pageSize] = useState(20);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(1);

    const loadComptes = useCallback(async () => {
        setLoading(true);
        try {
            const data = await ApiService.getConfigurationComptes(search, page, pageSize);
            const items = Array.isArray(data?.items) ? data.items : [];
            setComptes(items);
            setTotal(Number(data?.total ?? items.length));
            setPages(Number(data?.pages ?? 1));
            setPage(Number(data?.page ?? page));
        } catch (error) {
            setMessage(`Erreur lors du chargement: ${error.message}`);
        } finally {
            setLoading(false);
        }
    }, [search, page, pageSize]);

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

    const handleSearchChange = (e) => {
        setSearch(e.target.value);
        setPage(1);
    };

    const handleEdit = (compte) => {
        setEditingCode(compte.code_compte);
        setEditForm({
            code_compte: compte.code_compte,
            libelle_compte: compte.libelle_compte,
        });
    };

    const handleCancelEdit = () => {
        setEditingCode(null);
        setEditForm({ code_compte: '', libelle_compte: '' });
    };

    const handleEditChange = (e) => {
        const { name, value } = e.target;
        setEditForm((prev) => ({ ...prev, [name]: value }));
    };

    const handleSaveEdit = async (originalCode) => {
        const code = (editForm.code_compte || '').trim();
        const libelle = (editForm.libelle_compte || '').trim();

        if (!code || !libelle) {
            setMessage('Veuillez saisir le code compte et le libellé compte');
            return;
        }

        setSaving(true);
        setMessage('');
        try {
            await ApiService.updateConfigurationCompte(originalCode, {
                code_compte: code,
                libelle_compte: libelle,
            });
            setMessage('Compte modifié avec succès');
            setEditingCode(null);
            setEditForm({ code_compte: '', libelle_compte: '' });
            await loadComptes();
        } catch (error) {
            setMessage(`Erreur lors de la modification: ${error.message}`);
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (codeCompte) => {
        if (!window.confirm(`Supprimer le compte "${codeCompte}" ?`)) return;
        setSaving(true);
        setMessage('');
        try {
            await ApiService.deleteConfigurationCompte(codeCompte);
            setMessage('Compte supprimé avec succès');
            if (editingCode === codeCompte) {
                setEditingCode(null);
                setEditForm({ code_compte: '', libelle_compte: '' });
            }
            await loadComptes();
        } catch (error) {
            setMessage(`Erreur lors de la suppression: ${error.message}`);
        } finally {
            setSaving(false);
        }
    };

    const canGoPrev = page > 1;
    const canGoNext = page < pages;

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
                <span className="badge badge-primary">{total}</span>
            </div>

            <div className="form-row config-search-row" style={{ marginBottom: '1rem' }}>
                <div className="form-col form-col-lg">
                    <input
                        type="text"
                        className="form-control"
                        value={search}
                        onChange={handleSearchChange}
                        placeholder="Rechercher par code ou libellé..."
                    />
                </div>
            </div>

            <div className="table-responsive">
                <table className="olea-table config-table">
                    <thead>
                        <tr>
                            <th>Code compte</th>
                            <th>Libellé compte</th>
                            <th className="text-center">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="3" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Chargement...
                                </td>
                            </tr>
                        ) : comptes.length === 0 ? (
                            <tr>
                                <td colSpan="3" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Aucun compte trouvé
                                </td>
                            </tr>
                        ) : (
                            comptes.map((compte) => (
                                <tr key={compte.code_compte}>
                                    {editingCode === compte.code_compte ? (
                                        <>
                                            <td>
                                                <input
                                                    type="text"
                                                    name="code_compte"
                                                    className="form-control form-control-sm"
                                                    value={editForm.code_compte}
                                                    onChange={handleEditChange}
                                                />
                                            </td>
                                            <td>
                                                <input
                                                    type="text"
                                                    name="libelle_compte"
                                                    className="form-control form-control-sm"
                                                    value={editForm.libelle_compte}
                                                    onChange={handleEditChange}
                                                />
                                            </td>
                                            <td className="text-center">
                                                <div className="btn-group config-actions">
                                                    <button
                                                        className="btn btn-sm btn-success"
                                                        onClick={() => handleSaveEdit(compte.code_compte)}
                                                        disabled={saving}
                                                        title="Enregistrer"
                                                    >
                                                        ✓ Enregistrer
                                                    </button>
                                                    <button
                                                        className="btn btn-sm btn-secondary"
                                                        onClick={handleCancelEdit}
                                                        title="Annuler"
                                                    >
                                                        ✕ Annuler
                                                    </button>
                                                </div>
                                            </td>
                                        </>
                                    ) : (
                                        <>
                                            <td>{compte.code_compte}</td>
                                            <td>{compte.libelle_compte}</td>
                                            <td className="text-center">
                                                <div className="btn-group config-actions">
                                                    <button
                                                        className="btn btn-sm btn-secondary"
                                                        onClick={() => handleEdit(compte)}
                                                        title="Modifier"
                                                    >
                                                        ✏️ Modifier
                                                    </button>
                                                    <button
                                                        className="btn btn-sm btn-danger"
                                                        onClick={() => handleDelete(compte.code_compte)}
                                                        title="Supprimer"
                                                        disabled={saving}
                                                    >
                                                        🗑️ Supprimer
                                                    </button>
                                                </div>
                                            </td>
                                        </>
                                    )}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            <div className="form-row config-pagination" style={{ marginTop: '1rem', alignItems: 'center' }}>
                <div className="form-col">
                    <span className="text-muted">
                        Page {page} / {pages}
                    </span>
                </div>
                <div className="form-col form-col-btn" style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={!canGoPrev || loading}
                    >
                        Précédent
                    </button>
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setPage((p) => Math.min(pages, p + 1))}
                        disabled={!canGoNext || loading}
                    >
                        Suivant
                    </button>
                </div>
            </div>
        </div>
    );
}

export default Configuration;
