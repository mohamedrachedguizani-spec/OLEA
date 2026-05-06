import React, { useEffect, useState, useCallback } from 'react';
import ApiService from '../services/api';

function Configuration() {
    const [activeTab, setActiveTab] = useState('comptes');
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

    const [mappingForm, setMappingForm] = useState({
        mapping_section: '',
        code_compte: '',
        libelle_sage: '',
        categorie: '',
        categorie_custom: '',
        type: 'Produit',
        agregat_bfc: '',
        agregat_bfc_custom: '',
        sens: '+',
    });
    const [mappingEntries, setMappingEntries] = useState([]);
    const [mappingSections, setMappingSections] = useState([]);
    const [mappingCategories, setMappingCategories] = useState([]);
    const [mappingAgregats, setMappingAgregats] = useState([]);
    const [mappingSearch, setMappingSearch] = useState('');
    const [mappingLoading, setMappingLoading] = useState(false);
    const [mappingSaving, setMappingSaving] = useState(false);
    const [mappingMessage, setMappingMessage] = useState('');
    const [mappingPage, setMappingPage] = useState(1);
    const [mappingPageSize] = useState(20);
    const [mappingTotal, setMappingTotal] = useState(0);
    const [mappingPages, setMappingPages] = useState(1);
    const [mappingEditingKey, setMappingEditingKey] = useState(null);
    const [mappingEditForm, setMappingEditForm] = useState({
        mapping_section: '',
        code_compte: '',
        libelle_sage: '',
        categorie: '',
        type: 'Produit',
        agregat_bfc: '',
        sens: '+',
    });


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

    const loadMappingData = useCallback(async () => {
        setMappingLoading(true);
        try {
            const [metaData, entriesData] = await Promise.all([
                ApiService.getSageBfcMappingMeta(),
                ApiService.getSageBfcMappingEntries(mappingSearch, mappingPage, mappingPageSize),
            ]);
            setMappingSections(Array.isArray(metaData?.sections) ? metaData.sections : []);
            setMappingCategories(Array.isArray(metaData?.categories) ? metaData.categories : []);
            setMappingAgregats(Array.isArray(metaData?.agregats) ? metaData.agregats : []);
            const items = Array.isArray(entriesData?.items) ? entriesData.items : [];
            setMappingEntries(items);
            setMappingTotal(Number(entriesData?.total ?? items.length));
            setMappingPages(Number(entriesData?.pages ?? 1));
            setMappingPage(Number(entriesData?.page ?? mappingPage));
        } catch (error) {
            setMappingMessage(`Erreur lors du chargement: ${error.message}`);
        } finally {
            setMappingLoading(false);
        }
    }, [mappingSearch, mappingPage, mappingPageSize]);

    useEffect(() => {
        if (activeTab === 'mapping') {
            loadMappingData();
        }
    }, [activeTab, loadMappingData]);

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

    const filteredMappingEntries = mappingEntries;

    const getCategoryOptions = (currentValue) => {
        const options = new Set(mappingCategories);
        if (currentValue) options.add(currentValue);
        return Array.from(options).sort();
    };

    const getAgregatOptions = (currentValue) => {
        const options = new Set(mappingAgregats);
        if (currentValue) options.add(currentValue);
        return Array.from(options).sort();
    };

    const handleMappingSubmit = async (e) => {
        e.preventDefault();
        setMappingMessage('');

        const categorieValue =
            mappingForm.categorie === '__custom__'
                ? (mappingForm.categorie_custom || '').trim()
                : (mappingForm.categorie || '').trim();
        const agregatValue =
            mappingForm.agregat_bfc === '__custom__'
                ? (mappingForm.agregat_bfc_custom || '').trim()
                : (mappingForm.agregat_bfc || '').trim();

        const payload = {
            mapping_section: mappingForm.mapping_section,
            code_compte: mappingForm.code_compte?.trim(),
            libelle_sage: mappingForm.libelle_sage?.trim(),
            categorie: categorieValue,
            type: mappingForm.type,
            agregat_bfc: agregatValue,
            sens: mappingForm.sens,
        };

        if (!payload.mapping_section || !payload.code_compte || !payload.libelle_sage || !payload.categorie || !payload.agregat_bfc) {
            setMappingMessage('Veuillez remplir tous les champs obligatoires.');
            return;
        }

        setMappingSaving(true);
        try {
            await ApiService.createSageBfcMappingEntry(payload);
            setMappingMessage('Mapping ajouté avec succès');
            setMappingForm({
                mapping_section: mappingForm.mapping_section,
                code_compte: '',
                libelle_sage: '',
                categorie: mappingForm.categorie === '__custom__' ? '__custom__' : payload.categorie,
                categorie_custom: mappingForm.categorie === '__custom__' ? payload.categorie : '',
                type: payload.type,
                agregat_bfc: mappingForm.agregat_bfc === '__custom__' ? '__custom__' : payload.agregat_bfc,
                agregat_bfc_custom: mappingForm.agregat_bfc === '__custom__' ? payload.agregat_bfc : '',
                sens: payload.sens,
            });
            await loadMappingData();
        } catch (error) {
            setMappingMessage(`Erreur lors de l'ajout: ${error.message}`);
        } finally {
            setMappingSaving(false);
        }
    };

    const handleMappingEdit = (entry) => {
        const entryType = entry.type || entry.type_ligne || 'Produit';
        const key = `${entry.code_compte}|${entry.mapping_section}`;
        setMappingEditingKey(key);
        setMappingEditForm({
            mapping_section: entry.mapping_section,
            code_compte: entry.code_compte,
            libelle_sage: entry.libelle_sage,
            categorie: entry.categorie,
            type: entryType,
            agregat_bfc: entry.agregat_bfc,
            sens: entry.sens,
        });
    };

    const handleMappingCancelEdit = () => {
        setMappingEditingKey(null);
        setMappingEditForm({
            mapping_section: '',
            code_compte: '',
            libelle_sage: '',
            categorie: '',
            type: 'Produit',
            agregat_bfc: '',
            sens: '+',
        });
    };

    const handleMappingSaveEdit = async (originalCode) => {
        const payload = {
            mapping_section: mappingEditForm.mapping_section,
            code_compte: mappingEditForm.code_compte?.trim(),
            libelle_sage: mappingEditForm.libelle_sage?.trim(),
            categorie: mappingEditForm.categorie?.trim(),
            type: mappingEditForm.type,
            agregat_bfc: mappingEditForm.agregat_bfc?.trim(),
            sens: mappingEditForm.sens,
        };

        if (!payload.mapping_section || !payload.code_compte || !payload.libelle_sage || !payload.categorie || !payload.agregat_bfc) {
            setMappingMessage('Veuillez remplir tous les champs obligatoires.');
            return;
        }

        setMappingSaving(true);
        setMappingMessage('');
        try {
            await ApiService.updateSageBfcMappingEntry(originalCode, payload);
            setMappingMessage('Mapping modifié avec succès');
            handleMappingCancelEdit();
            await loadMappingData();
        } catch (error) {
            setMappingMessage(`Erreur lors de la modification: ${error.message}`);
        } finally {
            setMappingSaving(false);
        }
    };

    const handleMappingDelete = async (codeCompte, mappingSection) => {
        if (!window.confirm(`Supprimer le mapping "${codeCompte}" ?`)) return;
        setMappingSaving(true);
        setMappingMessage('');
        try {
            await ApiService.deleteSageBfcMappingEntry(codeCompte, mappingSection);
            setMappingMessage('Mapping supprimé avec succès');
            if (mappingEditingKey === `${codeCompte}|${mappingSection}`) {
                handleMappingCancelEdit();
            }
            await loadMappingData();
        } catch (error) {
            setMappingMessage(`Erreur lors de la suppression: ${error.message}`);
        } finally {
            setMappingSaving(false);
        }
    };


    return (
        <div className="olea-card fade-in">
            <div className="card-header">
                <div className="config-header">
                    <h2 className="card-title">
                        <span className="icon">⚙️</span>
                        Configuration
                    </h2>
                    <div className="config-tabs" role="tablist" aria-label="Configuration tabs">
                        <button
                            type="button"
                            className={`config-tab ${activeTab === 'comptes' ? 'active' : ''}`}
                            onClick={() => setActiveTab('comptes')}
                            role="tab"
                            aria-selected={activeTab === 'comptes'}
                        >
                            Comptes
                        </button>
                        <button
                            type="button"
                            className={`config-tab ${activeTab === 'mapping' ? 'active' : ''}`}
                            onClick={() => setActiveTab('mapping')}
                            role="tab"
                            aria-selected={activeTab === 'mapping'}
                        >
                            Mapping SAGE → BFC
                        </button>
                    </div>
                </div>
            </div>

            {activeTab === 'comptes' && message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

            {activeTab === 'mapping' && mappingMessage && (
                <div className={`alert ${mappingMessage.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {mappingMessage}
                </div>
            )}
            {activeTab === 'comptes' && (
                <>
                    <div className="section-header" style={{ marginBottom: '1rem' }}>
                        <h3>
                            <span className="icon">🏷️</span>
                            Comptes comptables
                        </h3>
                        <span className="badge badge-primary">{total}</span>
                    </div>

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
                                                                ✏️ 
                                                            </button>
                                                            <button
                                                                className="btn btn-sm btn-danger"
                                                                onClick={() => handleDelete(compte.code_compte)}
                                                                title="Supprimer"
                                                                disabled={saving}
                                                            >
                                                                🗑️ 
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
                </>
            )}

            {activeTab === 'mapping' && (
                <>
                    <div className="section-header" style={{ marginBottom: '1rem' }}>
                        <h3>
                            <span className="icon">🧩</span>
                            Mapping SAGE → BFC
                        </h3>
                        <span className="badge badge-primary">{mappingTotal}</span>
                    </div>

                    <form className="olea-form mb-4" onSubmit={handleMappingSubmit}>
                        <div className="form-row">
                            <div className="form-col">
                                <div className="form-group">
                                    <label>Section mapping</label>
                                    <select
                                        className="form-control"
                                        value={mappingForm.mapping_section}
                                        onChange={(e) => setMappingForm((prev) => ({ ...prev, mapping_section: e.target.value }))}
                                        required
                                    >
                                        <option value="">Sélectionner...</option>
                                        {mappingSections.map((section) => (
                                            <option key={section} value={section}>{section}</option>
                                        ))}
                                    </select>
                                </div>
                            </div>
                            <div className="form-col">
                                <div className="form-group">
                                    <label>Code compte</label>
                                    <input
                                        type="text"
                                        className="form-control"
                                        value={mappingForm.code_compte}
                                        onChange={(e) => setMappingForm((prev) => ({ ...prev, code_compte: e.target.value }))}
                                        placeholder="Ex: 7051000T"
                                        required
                                    />
                                </div>
                            </div>
                            <div className="form-col form-col-lg">
                                <div className="form-group">
                                    <label>Libellé SAGE</label>
                                    <input
                                        type="text"
                                        className="form-control"
                                        value={mappingForm.libelle_sage}
                                        onChange={(e) => setMappingForm((prev) => ({ ...prev, libelle_sage: e.target.value }))}
                                        placeholder="Ex: COMMISSION GRAND COMPTE"
                                        required
                                    />
                                </div>
                            </div>
                        </div>
                        <div className="form-row">
                            <div className="form-col">
                                <div className="form-group">
                                    <label>Catégorie</label>
                                    <select
                                        className="form-control"
                                        value={mappingForm.categorie}
                                        onChange={(e) => {
                                            const value = e.target.value;
                                            setMappingForm((prev) => ({
                                                ...prev,
                                                categorie: value,
                                                categorie_custom: value === '__custom__' ? prev.categorie_custom : '',
                                            }));
                                        }}
                                        required
                                    >
                                        <option value="">Sélectionner...</option>
                                        {mappingCategories.map((cat) => (
                                            <option key={cat} value={cat}>{cat}</option>
                                        ))}
                                        <option value="__custom__">Autre (saisir)</option>
                                    </select>
                                </div>
                                {mappingForm.categorie === '__custom__' && (
                                    <div className="form-group" style={{ marginTop: '0.5rem' }}>
                                        <input
                                            type="text"
                                            className="form-control"
                                            value={mappingForm.categorie_custom}
                                            onChange={(e) => setMappingForm((prev) => ({ ...prev, categorie_custom: e.target.value }))}
                                            placeholder="Saisir une catégorie"
                                            required
                                        />
                                    </div>
                                )}
                            </div>
                            <div className="form-col">
                                <div className="form-group">
                                    <label>Agrégat BFC</label>
                                    <select
                                        className="form-control"
                                        value={mappingForm.agregat_bfc}
                                        onChange={(e) => {
                                            const value = e.target.value;
                                            setMappingForm((prev) => ({
                                                ...prev,
                                                agregat_bfc: value,
                                                agregat_bfc_custom: value === '__custom__' ? prev.agregat_bfc_custom : '',
                                            }));
                                        }}
                                        required
                                    >
                                        <option value="">Sélectionner...</option>
                                        {mappingAgregats.map((ag) => (
                                            <option key={ag} value={ag}>{ag}</option>
                                        ))}
                                        <option value="__custom__">Autre (saisir)</option>
                                    </select>
                                </div>
                                {mappingForm.agregat_bfc === '__custom__' && (
                                    <div className="form-group" style={{ marginTop: '0.5rem' }}>
                                        <input
                                            type="text"
                                            className="form-control"
                                            value={mappingForm.agregat_bfc_custom}
                                            onChange={(e) => setMappingForm((prev) => ({ ...prev, agregat_bfc_custom: e.target.value }))}
                                            placeholder="Saisir un agrégat"
                                            required
                                        />
                                    </div>
                                )}
                            </div>
                            <div className="form-col">
                                <div className="form-group">
                                    <label>Type</label>
                                    <select
                                        className="form-control"
                                        value={mappingForm.type}
                                        onChange={(e) => setMappingForm((prev) => ({ ...prev, type: e.target.value }))}
                                        required
                                    >
                                        <option value="Produit">Produit</option>
                                        <option value="Charge">Charge</option>
                                        <option value="Actif">Actif</option>
                                    </select>
                                </div>
                            </div>
                            <div className="form-col">
                                <div className="form-group">
                                    <label>Sens</label>
                                    <select
                                        className="form-control"
                                        value={mappingForm.sens}
                                        onChange={(e) => setMappingForm((prev) => ({ ...prev, sens: e.target.value }))}
                                        required
                                    >
                                        <option value="+">+</option>
                                        <option value="-">-</option>
                                    </select>
                                </div>
                            </div>
                            <div className="form-col form-col-btn">
                                <button type="submit" className="btn btn-primary" disabled={mappingSaving}>
                                    {mappingSaving ? 'Enregistrement...' : 'Ajouter'}
                                </button>
                            </div>
                        </div>
                    </form>

                    <div className="form-row config-search-row" style={{ marginBottom: '1rem' }}>
                        <div className="form-col form-col-lg">
                            <input
                                type="text"
                                className="form-control"
                                value={mappingSearch}
                                onChange={(e) => {
                                    setMappingSearch(e.target.value);
                                    setMappingPage(1);
                                }}
                                placeholder="Rechercher par code, libellé, catégorie, agrégat..."
                            />
                        </div>
                    </div>

                    <div className="table-responsive">
                        <table className="olea-table mapping-table">
                            <thead>
                                <tr>
                                    <th>Section</th>
                                    <th>Code compte</th>
                                    <th>Libellé SAGE</th>
                                    <th>Catégorie</th>
                                    <th>Agrégat BFC</th>
                                    <th>Type</th>
                                    <th>Sens</th>
                                    <th className="text-center">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {mappingLoading ? (
                                    <tr>
                                        <td colSpan="8" style={{ textAlign: 'center', padding: '1rem' }}>
                                            Chargement...
                                        </td>
                                    </tr>
                                ) : filteredMappingEntries.length === 0 ? (
                                    <tr>
                                        <td colSpan="8" style={{ textAlign: 'center', padding: '1rem' }}>
                                            Aucun mapping trouvé
                                        </td>
                                    </tr>
                                ) : (
                                    filteredMappingEntries.map((entry) => {
                                        const key = `${entry.code_compte}|${entry.mapping_section}`;
                                        return (
                                            <tr key={key}>
                                                {mappingEditingKey === key ? (
                                                    <>
                                                        <td>
                                                            <select
                                                                className="form-control form-control-sm"
                                                                value={mappingEditForm.mapping_section}
                                                                onChange={(e) => setMappingEditForm((prev) => ({ ...prev, mapping_section: e.target.value }))}
                                                            >
                                                                {mappingSections.map((section) => (
                                                                    <option key={section} value={section}>{section}</option>
                                                                ))}
                                                            </select>
                                                        </td>
                                                        <td>
                                                            <input
                                                                type="text"
                                                                className="form-control form-control-sm"
                                                                value={mappingEditForm.code_compte}
                                                                onChange={(e) => setMappingEditForm((prev) => ({ ...prev, code_compte: e.target.value }))}
                                                            />
                                                        </td>
                                                        <td>
                                                            <input
                                                                type="text"
                                                                className="form-control form-control-sm"
                                                                value={mappingEditForm.libelle_sage}
                                                                onChange={(e) => setMappingEditForm((prev) => ({ ...prev, libelle_sage: e.target.value }))}
                                                            />
                                                        </td>
                                                        <td>
                                                            <select
                                                                className="form-control form-control-sm"
                                                                value={mappingEditForm.categorie}
                                                                onChange={(e) => setMappingEditForm((prev) => ({ ...prev, categorie: e.target.value }))}
                                                            >
                                                                {getCategoryOptions(mappingEditForm.categorie).map((cat) => (
                                                                    <option key={cat} value={cat}>{cat}</option>
                                                                ))}
                                                            </select>
                                                        </td>
                                                        <td>
                                                            <select
                                                                className="form-control form-control-sm"
                                                                value={mappingEditForm.agregat_bfc}
                                                                onChange={(e) => setMappingEditForm((prev) => ({ ...prev, agregat_bfc: e.target.value }))}
                                                            >
                                                                {getAgregatOptions(mappingEditForm.agregat_bfc).map((ag) => (
                                                                    <option key={ag} value={ag}>{ag}</option>
                                                                ))}
                                                            </select>
                                                        </td>
                                                        <td>
                                                            <select
                                                                className="form-control form-control-sm"
                                                                value={mappingEditForm.type}
                                                                onChange={(e) => setMappingEditForm((prev) => ({ ...prev, type: e.target.value }))}
                                                            >
                                                                <option value="Produit">Produit</option>
                                                                <option value="Charge">Charge</option>
                                                                <option value="Actif">Actif</option>
                                                            </select>
                                                        </td>
                                                        <td>
                                                            <select
                                                                className="form-control form-control-sm"
                                                                value={mappingEditForm.sens}
                                                                onChange={(e) => setMappingEditForm((prev) => ({ ...prev, sens: e.target.value }))}
                                                            >
                                                                <option value="+">+</option>
                                                                <option value="-">-</option>
                                                            </select>
                                                        </td>
                                                        <td className="text-center">
                                                            <div className="btn-group config-actions">
                                                                <button
                                                                    className="btn btn-sm btn-success"
                                                                    onClick={() => handleMappingSaveEdit(entry.code_compte)}
                                                                    disabled={mappingSaving}
                                                                    title="Enregistrer"
                                                                >
                                                                    ✓ Enregistrer
                                                                </button>
                                                                <button
                                                                    className="btn btn-sm btn-secondary"
                                                                    onClick={handleMappingCancelEdit}
                                                                    title="Annuler"
                                                                >
                                                                    ✕ Annuler
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </>
                                                ) : (
                                                    <>
                                                        <td>{entry.mapping_section || '-'}</td>
                                                        <td>{entry.code_compte || '-'}</td>
                                                        <td>{entry.libelle_sage || '-'}</td>
                                                        <td>{entry.categorie || '-'}</td>
                                                        <td>{entry.agregat_bfc || '-'}</td>
                                                        <td>{entry.type || entry.type_ligne || '-'}</td>
                                                        <td>{entry.sens || '-'}</td>
                                                        <td className="text-center">
                                                            <div className="btn-group config-actions">
                                                                <button
                                                                    className="btn btn-sm btn-secondary"
                                                                    onClick={() => handleMappingEdit(entry)}
                                                                    title="Modifier"
                                                                >
                                                                    ✏️ 
                                                                </button>
                                                                <button
                                                                    className="btn btn-sm btn-danger"
                                                                    onClick={() => handleMappingDelete(entry.code_compte, entry.mapping_section)}
                                                                    title="Supprimer"
                                                                    disabled={mappingSaving}
                                                                >
                                                                    🗑️ 
                                                                </button>
                                                            </div>
                                                        </td>
                                                    </>
                                                )}
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>

                    <div className="form-row config-pagination" style={{ marginTop: '1rem', alignItems: 'center' }}>
                        <div className="form-col">
                            <span className="text-muted">
                                Page {mappingPage} / {mappingPages}
                            </span>
                        </div>
                        <div className="form-col form-col-btn" style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                                type="button"
                                className="btn btn-secondary"
                                onClick={() => setMappingPage((p) => Math.max(1, p - 1))}
                                disabled={mappingPage <= 1 || mappingLoading}
                            >
                                Précédent
                            </button>
                            <button
                                type="button"
                                className="btn btn-secondary"
                                onClick={() => setMappingPage((p) => Math.min(mappingPages, p + 1))}
                                disabled={mappingPage >= mappingPages || mappingLoading}
                            >
                                Suivant
                            </button>
                        </div>
                    </div>

                </>
            )}
        </div>
    );
}

export default Configuration;
