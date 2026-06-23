import React, { useEffect, useState, useCallback } from 'react';
import ApiService from '../services/api';

function Configuration() {
    const [activeTab, setActiveTab] = useState('comptes');
    
    // Comptes
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

    // Tiers
    const [tiersForm, setTiersForm] = useState({ code: '', libelle: '' });
    const [tiersSearch, setTiersSearch] = useState('');
    const [tiersList, setTiersList] = useState([]);
    const [tiersLoading, setTiersLoading] = useState(false);
    const [tiersSaving, setTiersSaving] = useState(false);
    const [tiersMessage, setTiersMessage] = useState('');
    const [tiersEditingCode, setTiersEditingCode] = useState(null);
    const [tiersEditForm, setTiersEditForm] = useState({ code: '', libelle: '' });
    const [tiersPage, setTiersPage] = useState(1);
    const [tiersPageSize, setTiersPageSize] = useState(20);
    const [tiersTotal, setTiersTotal] = useState(0);
    const [tiersPages, setTiersPages] = useState(1);

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

    const loadTiers = useCallback(async () => {
        setTiersLoading(true);
        try {
            const data = await ApiService.getConfigurationTiers(tiersSearch, tiersPage, tiersPageSize);
            const items = Array.isArray(data?.items) ? data.items : [];
            setTiersList(items);
            setTiersTotal(Number(data?.total ?? items.length));
            setTiersPages(Number(data?.pages ?? 1));
            setTiersPage(Number(data?.page ?? tiersPage));
        } catch (error) {
            setTiersMessage(`Erreur lors du chargement: ${error.message}`);
        } finally {
            setTiersLoading(false);
        }
    }, [tiersSearch, tiersPage, tiersPageSize]);

    useEffect(() => {
        if (activeTab === 'tiers') {
            loadTiers();
        }
    }, [activeTab, loadTiers]);

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

    useEffect(() => {
        if (message) {
            const timer = setTimeout(() => setMessage(''), 2000);
            return () => clearTimeout(timer);
        }
    }, [message]);

    useEffect(() => {
        if (tiersMessage) {
            const timer = setTimeout(() => setTiersMessage(''), 2000);
            return () => clearTimeout(timer);
        }
    }, [tiersMessage]);

    useEffect(() => {
        if (mappingMessage) {
            const timer = setTimeout(() => setMappingMessage(''), 2000);
            return () => clearTimeout(timer);
        }
    }, [mappingMessage]);

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

    const handleTiersSubmit = async (e) => {
        e.preventDefault();
        setTiersMessage('');

        const code = (tiersForm.code || '').trim();
        const libelle = (tiersForm.libelle || '').trim();

        if (!code || !libelle) {
            setTiersMessage('Veuillez saisir le code tiers et le libellé tiers');
            return;
        }

        setTiersSaving(true);
        try {
            await ApiService.createOrUpdateConfigurationTiers({
                code: code,
                libelle: libelle,
            });
            setTiersMessage('Tiers enregistré avec succès');
            setTiersForm({ code: '', libelle: '' });
            await loadTiers();
        } catch (error) {
            setTiersMessage(`Erreur lors de l'enregistrement: ${error.message}`);
        } finally {
            setTiersSaving(false);
        }
    };

    const handleTiersSearchChange = (e) => {
        setTiersSearch(e.target.value);
        setTiersPage(1);
    };

    const handleTiersEdit = (t) => {
        setTiersEditingCode(t.code);
        setTiersEditForm({
            code: t.code,
            libelle: t.libelle,
        });
    };

    const handleTiersCancelEdit = () => {
        setTiersEditingCode(null);
        setTiersEditForm({ code: '', libelle: '' });
    };

    const handleTiersEditChange = (e) => {
        const { name, value } = e.target;
        setTiersEditForm((prev) => ({ ...prev, [name]: value }));
    };

    const handleTiersSaveEdit = async (originalCode) => {
        const code = (tiersEditForm.code || '').trim();
        const libelle = (tiersEditForm.libelle || '').trim();

        if (!code || !libelle) {
            setTiersMessage('Veuillez saisir le code tiers et le libellé tiers');
            return;
        }

        setTiersSaving(true);
        setTiersMessage('');
        try {
            await ApiService.updateConfigurationTiers(originalCode, {
                code: code,
                libelle: libelle,
            });
            setTiersMessage('Tiers modifié avec succès');
            setTiersEditingCode(null);
            setTiersEditForm({ code: '', libelle: '' });
            await loadTiers();
        } catch (error) {
            setTiersMessage(`Erreur lors de la modification: ${error.message}`);
        } finally {
            setTiersSaving(false);
        }
    };

    const handleTiersDelete = async (code) => {
        if (!window.confirm(`Supprimer le tiers "${code}" ?`)) return;
        setTiersSaving(true);
        setTiersMessage('');
        try {
            await ApiService.deleteConfigurationTiers(code);
            setTiersMessage('Tiers supprimé avec succès');
            if (tiersEditingCode === code) {
                setTiersEditingCode(null);
                setTiersEditForm({ code: '', libelle: '' });
            }
            await loadTiers();
        } catch (error) {
            setTiersMessage(`Erreur lors de la suppression: ${error.message}`);
        } finally {
            setTiersSaving(false);
        }
    };

    const canGoPrev = page > 1;
    const canGoNext = page < pages;

    const canGoTiersPrev = tiersPage > 1;
    const canGoTiersNext = tiersPage < tiersPages;

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
                        {/* <span className="icon">⚙️</span> */}
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
                            className={`config-tab ${activeTab === 'tiers' ? 'active' : ''}`}
                            onClick={() => setActiveTab('tiers')}
                            role="tab"
                            aria-selected={activeTab === 'tiers'}
                        >
                            Plan Tiers
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

            {activeTab === 'tiers' && tiersMessage && (
                <div className={`alert ${tiersMessage.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {tiersMessage}
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
                                                        <div className="btn-group">
                                                            <button
                                                                className="btn btn-sm btn-success"
                                                                onClick={() => handleSaveEdit(compte.code_compte)}
                                                                disabled={saving}
                                                                title="Enregistrer"
                                                            >
                                                                ✓ 
                                                            </button>
                                                            <button
                                                                className="btn btn-sm btn-secondary"
                                                                onClick={handleCancelEdit}
                                                                title="Annuler"
                                                            >
                                                                ✕ 
                                                            </button>
                                                        </div>
                                                    </td>
                                                </>
                                            ) : (
                                                <>
                                                    <td>{compte.code_compte}</td>
                                                    <td>{compte.libelle_compte}</td>
                                                    <td className="text-center">
                                                        <div className="btn-group">
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

                    {pages > 1 && (
                        <div className="lignes-pagination">
                            <button
                                className="pagination-btn"
                                disabled={page === 1 || loading}
                                onClick={() => setPage(1)}
                                title="Première page"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="11 17 6 12 11 7" />
                                    <polyline points="18 17 13 12 18 7" />
                                </svg>
                            </button>
                            <button
                                className="pagination-btn"
                                disabled={!canGoPrev || loading}
                                onClick={() => setPage((p) => p - 1)}
                                title="Page précédente"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="15 18 9 12 15 6" />
                                </svg>
                            </button>

                            <div className="pagination-pages">
                                {Array.from({ length: Math.min(5, pages) }, (_, i) => {
                                    let pageNumber;
                                    if (pages <= 5) {
                                        pageNumber = i + 1;
                                    } else if (page <= 3) {
                                        pageNumber = i + 1;
                                    } else if (page >= pages - 2) {
                                        pageNumber = pages - 4 + i;
                                    } else {
                                        pageNumber = page - 2 + i;
                                    }
                                    return (
                                        <button
                                            key={pageNumber}
                                            className={`pagination-page ${page === pageNumber ? 'active' : ''}`}
                                            onClick={() => setPage(pageNumber)}
                                            disabled={loading}
                                        >
                                            {pageNumber}
                                        </button>
                                    );
                                })}
                            </div>

                            <button
                                className="pagination-btn"
                                disabled={!canGoNext || loading}
                                onClick={() => setPage((p) => p + 1)}
                                title="Page suivante"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="9 18 15 12 9 6" />
                                </svg>
                            </button>
                            <button
                                className="pagination-btn"
                                disabled={page === pages || loading}
                                onClick={() => setPage(pages)}
                                title="Dernière page"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="13 17 18 12 13 7" />
                                    <polyline points="6 17 11 12 6 7" />
                                </svg>
                            </button>
                        </div>
                    )}
                </>
            )}

            {activeTab === 'tiers' && (
                <>
                    <div className="section-header" style={{ marginBottom: '1rem' }}>
                        <h3>
                            <span className="icon">🏷️</span>
                            Plan Tiers
                        </h3>
                        <span className="badge badge-primary">{tiersTotal}</span>
                    </div>

                    <form className="olea-form mb-4" onSubmit={handleTiersSubmit}>
                        <div className="form-row">
                            <div className="form-col">
                                <div className="form-group">
                                    <label>Code tiers</label>
                                    <input
                                        type="text"
                                        className="form-control"
                                        value={tiersForm.code}
                                        onChange={(e) => setTiersForm((prev) => ({ ...prev, code: e.target.value }))}
                                        placeholder="Ex: T01"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="form-col form-col-lg">
                                <div className="form-group">
                                    <label>Libellé tiers</label>
                                    <input
                                        type="text"
                                        className="form-control"
                                        value={tiersForm.libelle}
                                        onChange={(e) => setTiersForm((prev) => ({ ...prev, libelle: e.target.value }))}
                                        placeholder="Ex: Client Olea"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="form-col form-col-btn">
                                <button type="submit" className="btn btn-primary" disabled={tiersSaving}>
                                    {tiersSaving ? 'Enregistrement...' : 'Enregistrer'}
                                </button>
                            </div>
                        </div>
                    </form>

                    <div className="form-row config-search-row" style={{ marginBottom: '1rem' }}>
                        <div className="form-col form-col-lg">
                            <input
                                type="text"
                                className="form-control"
                                value={tiersSearch}
                                onChange={handleTiersSearchChange}
                                placeholder="Rechercher par code ou libellé..."
                            />
                        </div>
                    </div>

                    <div className="table-responsive">
                        <table className="olea-table config-table">
                            <thead>
                                <tr>
                                    <th>Code tiers</th>
                                    <th>Libellé tiers</th>
                                    <th className="text-center">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {tiersLoading ? (
                                    <tr>
                                        <td colSpan="3" style={{ textAlign: 'center', padding: '1rem' }}>
                                            Chargement...
                                        </td>
                                    </tr>
                                ) : tiersList.length === 0 ? (
                                    <tr>
                                        <td colSpan="3" style={{ textAlign: 'center', padding: '1rem' }}>
                                            Aucun tiers trouvé
                                        </td>
                                    </tr>
                                ) : (
                                    tiersList.map((t) => (
                                        <tr key={t.code}>
                                            {tiersEditingCode === t.code ? (
                                                <>
                                                    <td>
                                                        <input
                                                            type="text"
                                                            name="code"
                                                            className="form-control form-control-sm"
                                                            value={tiersEditForm.code}
                                                            onChange={handleTiersEditChange}
                                                        />
                                                    </td>
                                                    <td>
                                                        <input
                                                            type="text"
                                                            name="libelle"
                                                            className="form-control form-control-sm"
                                                            value={tiersEditForm.libelle}
                                                            onChange={handleTiersEditChange}
                                                        />
                                                    </td>
                                                    <td className="text-center">
                                                        <div className="btn-group">
                                                            <button
                                                                className="btn btn-sm btn-success"
                                                                onClick={() => handleTiersSaveEdit(t.code)}
                                                                disabled={tiersSaving}
                                                                title="Enregistrer"
                                                            >
                                                                ✓ 
                                                            </button>
                                                            <button
                                                                className="btn btn-sm btn-secondary"
                                                                onClick={handleTiersCancelEdit}
                                                                title="Annuler"
                                                            >
                                                                ✕ 
                                                            </button>
                                                        </div>
                                                    </td>
                                                </>
                                            ) : (
                                                <>
                                                    <td>{t.code}</td>
                                                    <td>{t.libelle}</td>
                                                    <td className="text-center">
                                                        <div className="btn-group">
                                                            <button
                                                                className="btn btn-sm btn-secondary"
                                                                onClick={() => handleTiersEdit(t)}
                                                                title="Modifier"
                                                            >
                                                                ✏️ 
                                                            </button>
                                                            <button
                                                                className="btn btn-sm btn-danger"
                                                                onClick={() => handleTiersDelete(t.code)}
                                                                title="Supprimer"
                                                                disabled={tiersSaving}
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

                    {tiersPages > 1 && (
                        <div className="lignes-pagination">
                            <button
                                className="pagination-btn"
                                disabled={tiersPage === 1 || tiersLoading}
                                onClick={() => setTiersPage(1)}
                                title="Première page"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="11 17 6 12 11 7" />
                                    <polyline points="18 17 13 12 18 7" />
                                </svg>
                            </button>
                            <button
                                className="pagination-btn"
                                disabled={!canGoTiersPrev || tiersLoading}
                                onClick={() => setTiersPage((p) => p - 1)}
                                title="Page précédente"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="15 18 9 12 15 6" />
                                </svg>
                            </button>

                            <div className="pagination-pages">
                                {Array.from({ length: Math.min(5, tiersPages) }, (_, i) => {
                                    let pageNumber;
                                    if (tiersPages <= 5) {
                                        pageNumber = i + 1;
                                    } else if (tiersPage <= 3) {
                                        pageNumber = i + 1;
                                    } else if (tiersPage >= tiersPages - 2) {
                                        pageNumber = tiersPages - 4 + i;
                                    } else {
                                        pageNumber = tiersPage - 2 + i;
                                    }
                                    return (
                                        <button
                                            key={pageNumber}
                                            className={`pagination-page ${tiersPage === pageNumber ? 'active' : ''}`}
                                            onClick={() => setTiersPage(pageNumber)}
                                            disabled={tiersLoading}
                                        >
                                            {pageNumber}
                                        </button>
                                    );
                                })}
                            </div>

                            <button
                                className="pagination-btn"
                                disabled={!canGoTiersNext || tiersLoading}
                                onClick={() => setTiersPage((p) => p + 1)}
                                title="Page suivante"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="9 18 15 12 9 6" />
                                </svg>
                            </button>
                            <button
                                className="pagination-btn"
                                disabled={tiersPage === tiersPages || tiersLoading}
                                onClick={() => setTiersPage(tiersPages)}
                                title="Dernière page"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="13 17 18 12 13 7" />
                                    <polyline points="6 17 11 12 6 7" />
                                </svg>
                            </button>
                        </div>
                    )}
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
                                                            <div className="btn-group">
                                                                <button
                                                                    className="btn btn-sm btn-success"
                                                                    onClick={() => handleMappingSaveEdit(entry.code_compte)}
                                                                    disabled={mappingSaving}
                                                                    title="Enregistrer"
                                                                >
                                                                    ✓ 
                                                                </button>
                                                                <button
                                                                    className="btn btn-sm btn-secondary"
                                                                    onClick={handleMappingCancelEdit}
                                                                    title="Annuler"
                                                                >
                                                                    ✕ 
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
                                                            <div className="btn-group">
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

                    {mappingPages > 1 && (
                        <div className="lignes-pagination">
                            <button
                                className="pagination-btn"
                                disabled={mappingPage === 1 || mappingLoading}
                                onClick={() => setMappingPage(1)}
                                title="Première page"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="11 17 6 12 11 7" />
                                    <polyline points="18 17 13 12 18 7" />
                                </svg>
                            </button>
                            <button
                                className="pagination-btn"
                                disabled={mappingPage <= 1 || mappingLoading}
                                onClick={() => setMappingPage((p) => p - 1)}
                                title="Page précédente"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="15 18 9 12 15 6" />
                                </svg>
                            </button>

                            <div className="pagination-pages">
                                {Array.from({ length: Math.min(5, mappingPages) }, (_, i) => {
                                    let pageNumber;
                                    if (mappingPages <= 5) {
                                        pageNumber = i + 1;
                                    } else if (mappingPage <= 3) {
                                        pageNumber = i + 1;
                                    } else if (mappingPage >= mappingPages - 2) {
                                        pageNumber = mappingPages - 4 + i;
                                    } else {
                                        pageNumber = mappingPage - 2 + i;
                                    }
                                    return (
                                        <button
                                            key={pageNumber}
                                            className={`pagination-page ${mappingPage === pageNumber ? 'active' : ''}`}
                                            onClick={() => setMappingPage(pageNumber)}
                                            disabled={mappingLoading}
                                        >
                                            {pageNumber}
                                        </button>
                                    );
                                })}
                            </div>

                            <button
                                className="pagination-btn"
                                disabled={mappingPage >= mappingPages || mappingLoading}
                                onClick={() => setMappingPage((p) => p + 1)}
                                title="Page suivante"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="9 18 15 12 9 6" />
                                </svg>
                            </button>
                            <button
                                className="pagination-btn"
                                disabled={mappingPage === mappingPages || mappingLoading}
                                onClick={() => setMappingPage(mappingPages)}
                                title="Dernière page"
                            >
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                                    <polyline points="13 17 18 12 13 7" />
                                    <polyline points="6 17 11 12 6 7" />
                                </svg>
                            </button>
                        </div>
                    )}

                </>
            )}
        </div>
    );
}

export default Configuration;
