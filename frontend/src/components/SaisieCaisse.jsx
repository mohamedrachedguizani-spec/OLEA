// src/components/SaisieCaisse.jsx
import ApiService from '../services/api';
import LibelleAutocomplete from './LibelleAutocomplete';
import React, { useState, useEffect, useRef, useCallback } from 'react';


function SaisieCaisse({ refreshTrigger }) {
    const [formData, setFormData] = useState({
        date_ecriture: new Date().toISOString().split('T')[0],
        libelle_ecriture: '',
        debit: '',
        credit: '',
        compte_contrepartie: '',
        tiers: '',
        section_analytique: ''
    });
    const [ecritures, setEcritures] = useState([]);
    const [comptes, setComptes] = useState([]);
    const [tiersList, setTiersList] = useState([]);
    const [activeCompteInput, setActiveCompteInput] = useState(false);
    const [activeEditCompteInput, setActiveEditCompteInput] = useState(null);
    const [activeTiersInput, setActiveTiersInput] = useState(false);
    const [activeEditTiersInput, setActiveEditTiersInput] = useState(null);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const debitInputRef = useRef(null);
    const creditInputRef = useRef(null);
    const lastSuggestedFieldRef = useRef(null);

    const [page, setPage] = useState(1);
    const [pageSize] = useState(20);
    const [totalPages, setTotalPages] = useState(1);
    const [totalEcritures, setTotalEcritures] = useState(0);

    const loadComptes = useCallback(async () => {
        try {
            const data = await ApiService.getComptes();
            setComptes(data);
        } catch (error) {
            // Pas de log console
        }
    }, []);

    const loadTiers = useCallback(async () => {
        try {
            const data = await ApiService.getTiers();
            setTiersList(Array.isArray(data) ? data : []);
        } catch (error) {
            // Pas de log console
        }
    }, []);

    useEffect(() => {
        loadComptes();
        loadTiers();
    }, [loadComptes, loadTiers]);

    const filterComptes = (query = '') => {
        const value = query.toLowerCase().trim();
        if (!value) return comptes;
        return comptes.filter((compte) =>
            compte.code_compte.toLowerCase().includes(value) ||
            compte.libelle_compte.toLowerCase().includes(value)
        );
    };

    const filterTiers = (query = '') => {
        const value = query.toLowerCase().trim();
        if (!value) return tiersList;
        return tiersList.filter((t) =>
            t.code.toLowerCase().includes(value) ||
            t.libelle.toLowerCase().includes(value)
        );
    };

    const normalizeText = (text = '') =>
        text
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();

    const canGoPrev = page > 1;
    const canGoNext = page < totalPages;

    const splitWords = (text = '') =>
        normalizeText(text)
            .replace(/[^a-z0-9\s]/g, ' ')
            .split(/\s+/)
            .filter(Boolean);

    const detectTargetFieldFromLibelle = (libelle = '') => {
        const value = normalizeText(libelle);
        if (!value) return null;

        const words = splitWords(libelle);
        const hasWord = (word) => words.includes(word);
        const hasAllWords = (neededWords) => neededWords.every((w) => hasWord(w));
        const hasPhrase = (phrase) => value.includes(normalizeText(phrase));

        const debitPhrases = [
            'alimentation caisse',
            'approvisionnement caisse',
            'reapprovisionnement caisse',
            'versement caisse',
            'depot caisse',
            'encaissement',
            'fonds de caisse',
            'ajout caisse',
            'ALIM',
            'fc',
            'fct',
            'enc',
            'gain',
            'recette',
        ];

        const debitWords = [
            'alimentation',
            'alimenter',
            'approvisionnement',
            'reapprovisionnement',
            'versement',
            'depot',
            'encaissement',
            'ajout',
            'fonds',
            'recette',
        ];

        const creditPhrases = [
            'paiement par caisse',
            'reglement charge',
            'paiement charge',
            'paiement facture',
            'avance societe',
            'avance salaire',
            'avance fournisseur',
            'sortie caisse',
            'retrait caisse',
            'depense caisse',
            'achat ',
            'charge ',
            'salaire ',
            'loyer ',
            'impot ',
            'frais ',
            'reparation ',
            'indemnite ',
            'amende ',
            'taxe ',
            'amenagement ',
            'essence ',
            'carburant ',
            'cnss ',
        ];

        const creditWords = [
            'paiement',
            'reglement',
            'depense',
            'achat',
            'facture',
            'frais',
            'avance',
            'charge',
            'fournisseur',
            'loyer',
            'impot',
            'salaire',
            'reparation',
            'INDEMNITE',
            'amende',
            'cnss',
        ];

        const matchedDebitByPhrase = debitPhrases.some(hasPhrase);
        const matchedDebitByWord = debitWords.some(hasWord);

        const matchedCreditByPhrase = creditPhrases.some(hasPhrase);
        const matchedCreditByWord = creditWords.some(hasWord);
        const matchedCreditSpecialCases =
            hasAllWords(['avance', 'societe']) ||
            hasAllWords(['avance', 'salaire']) ||
            hasAllWords(['paiement', 'charge']) ||
            hasAllWords(['reglement', 'facture']);

        const isAlimentation = matchedDebitByPhrase || matchedDebitByWord;
        const isPaiementCharge = matchedCreditByPhrase || matchedCreditByWord || matchedCreditSpecialCases;

        if (isPaiementCharge) return 'credit';
        if (isAlimentation) return 'debit';
        return null;
    };

    const autoFocusMontantField = (libelle = '') => {
        const targetField = detectTargetFieldFromLibelle(libelle);
        if (!targetField) return;

        const targetInput = targetField === 'debit' ? debitInputRef.current : creditInputRef.current;
        const alreadyFocused = document.activeElement === targetInput;
        if (lastSuggestedFieldRef.current === targetField && alreadyFocused) return;

        if (targetField === 'debit') {
            debitInputRef.current?.focus();
        } else if (targetField === 'credit') {
            creditInputRef.current?.focus();
        }

        lastSuggestedFieldRef.current = targetField;
    };

    const loadEcritures = useCallback(async () => {
        try {
            const data = await ApiService.getEcrituresCaisse({
                page,
                page_size: pageSize,
                migree: false,
                order: 'desc',
            });
            const items = Array.isArray(data?.items) ? data.items : [];
            setEcritures(items);
            setTotalEcritures(Number(data?.total ?? 0));
            setTotalPages(Number(data?.pages ?? 1));
        } catch (error) {
            // Pas de log console
        }
    }, [page, pageSize]);

    useEffect(() => {
        loadEcritures();
    }, [loadEcritures, refreshTrigger]);

    useEffect(() => {
        if (message) {
            const timer = setTimeout(() => {
                setMessage('');
            }, 2000);
            return () => clearTimeout(timer);
        }
    }, [message]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: (name === 'debit' || name === 'credit')
                ? (value === '' ? '' : parseFloat(value))
                : value
        }));
    };

    const handleLibelleSelect = (suggestion) => {
        setFormData(prev => ({
            ...prev,
            libelle_ecriture: suggestion.libelle,
            compte_contrepartie: suggestion.compte_suggestion || prev.compte_contrepartie || '',
            tiers: suggestion.tiers_suggestion || prev.tiers || '',
            section_analytique: suggestion.section_analytique_suggestion || prev.section_analytique || ''
        }));
        autoFocusMontantField(suggestion.libelle);
    };

    const handleLibelleChange = (value) => {
        setFormData(prev => ({ ...prev, libelle_ecriture: value }));
    };

    const handleLibelleEditingComplete = (value) => {
        autoFocusMontantField(value);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setMessage('');

        try {
            await ApiService.createEcritureCaisse({
                ...formData,
                debit: Number(formData.debit) || 0,
                credit: Number(formData.credit) || 0,
            });
            setMessage('Écriture ajoutée avec succès!');
            setFormData({
                date_ecriture: new Date().toISOString().split('T')[0],
                libelle_ecriture: '',
                debit: '',
                credit: '',
                compte_contrepartie: '',
                tiers: '',
                section_analytique: ''
            });
            lastSuggestedFieldRef.current = null;
            loadEcritures();
        } catch (error) {
            setMessage('Erreur lors de l\'ajout: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    const handleDelete = async (id) => {
        if (window.confirm('Voulez-vous vraiment supprimer cette écriture?')) {
            try {
                await ApiService.deleteEcritureCaisse(id);
                setMessage('Écriture supprimée avec succès!');
                loadEcritures();
            } catch (error) {
                setMessage('Erreur lors de la suppression: ' + error.message);
            }
        }
    };

    const handleMigrateDirect = async (ecriture) => {
        if (!ecriture.compte_contrepartie) {
            setMessage("Erreur : le Compte de Contre partie est obligatoire pour la migration vers Sage. Veuillez modifier l'écriture pour le renseigner.");
            return;
        }

        setLoading(true);
        setMessage('');

        try {
            await ApiService.migrerEcriture({
                ecriture_caisse_id: ecriture.id
            });
            setMessage('Écriture migrée vers Sage avec succès !');
            loadEcritures();
        } catch (error) {
            setMessage('Erreur lors de la migration: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    const handleEdit = (ecriture) => {
        setEditingId(ecriture.id);
        setEditForm({
            date_ecriture: ecriture.date_ecriture.split('T')[0],
            libelle_ecriture: ecriture.libelle_ecriture,
            debit: ecriture.debit,
            credit: ecriture.credit,
            compte_contrepartie: ecriture.compte_contrepartie || '',
            tiers: ecriture.tiers || '',
            section_analytique: ecriture.section_analytique || ''
        });
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setEditForm({});
        setActiveEditCompteInput(null);
        setActiveEditTiersInput(null);
    };

    const handleSaveEdit = async (id) => {
        setLoading(true);
        try {
            await ApiService.updateEcritureCaisse(id, editForm);
            setMessage('Écriture modifiée avec succès!');
            setEditingId(null);
            setEditForm({});
            setActiveEditCompteInput(null);
            setActiveEditTiersInput(null);
            loadEcritures();
        } catch (error) {
            setMessage('Erreur lors de la modification: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    const handleEditChange = (e) => {
        const { name, value } = e.target;
        setEditForm(prev => ({
            ...prev,
            [name]: name === 'debit' || name === 'credit' ? parseFloat(value) || 0 : value
        }));
    };

    return (
        <div className="olea-card fade-in">
            <div className="card-header">
                <h2 className="card-title">
                    Saisie des Écritures de Caisse
                </h2>
            </div>

            {message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

            <form onSubmit={handleSubmit} className="olea-form mb-4">
                {/* Première ligne du formulaire : Informations de caisse */}
                <div className="form-row" style={{ marginBottom: '1rem' }}>
                    <div className="form-col">
                        <div className="form-group">
                            <label>Date écriture</label>
                            <input
                                type="date"
                                name="date_ecriture"
                                value={formData.date_ecriture}
                                onChange={handleChange}
                                className="form-control"
                                required
                            />
                        </div>
                    </div>
                    
                    <div className="form-col form-col-lg">
                        <div className="form-group">
                            <label>Libellé écriture</label>
                            <LibelleAutocomplete
                                value={formData.libelle_ecriture}
                                onChange={handleLibelleChange}
                                onSelect={handleLibelleSelect}
                                onEditingComplete={handleLibelleEditingComplete}
                            />
                        </div>
                    </div>
                    
                    <div className="form-col">
                        <div className="form-group">
                            <label>Débit</label>
                            <input
                                ref={debitInputRef}
                                type="number"
                                name="debit"
                                value={formData.debit}
                                onChange={handleChange}
                                className="form-control"
                                step="0.001"
                                min="0"
                            />
                        </div>
                    </div>
                    
                    <div className="form-col">
                        <div className="form-group">
                            <label>Crédit</label>
                            <input
                                ref={creditInputRef}
                                type="number"
                                name="credit"
                                value={formData.credit}
                                onChange={handleChange}
                                className="form-control"
                                step="0.001"
                                min="0"
                            />
                        </div>
                    </div>
                </div>

                {/* Deuxième ligne du formulaire : Informations Sage */}
                <div className="form-row">
                    <div className="form-col">
                        <div className="form-group">
                            <label>Compte Contrepartie <span className="required" style={{ color: 'red' }}>*</span></label>
                            <div className="compte-suggest">
                                <input
                                    type="text"
                                    name="compte_contrepartie"
                                    value={formData.compte_contrepartie}
                                    onChange={handleChange}
                                    onFocus={() => setActiveCompteInput(true)}
                                    onBlur={() => {
                                        setTimeout(() => {
                                            setActiveCompteInput(false);
                                        }, 150);
                                    }}
                                    className="form-control"
                                    placeholder="Saisir code ou libellé"
                                    required
                                    autoComplete="off"
                                />
                                {activeCompteInput && (
                                    <div className="compte-suggest-list">
                                        {filterComptes(formData.compte_contrepartie || '')
                                            .map((compte) => (
                                                <button
                                                    key={compte.code_compte}
                                                    type="button"
                                                    className="compte-suggest-item"
                                                    onMouseDown={(e) => {
                                                        e.preventDefault();
                                                        setFormData(prev => ({ ...prev, compte_contrepartie: compte.code_compte }));
                                                        setActiveCompteInput(false);
                                                    }}
                                                >
                                                    <strong>{compte.code_compte}</strong> — {compte.libelle_compte}
                                                </button>
                                            ))}
                                        {filterComptes(formData.compte_contrepartie || '').length === 0 && (
                                            <div className="compte-suggest-empty">Aucun compte trouvé</div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="form-col">
                        <div className="form-group">
                            <label>Tiers (optionnel)</label>
                            <div className="compte-suggest">
                                <input
                                    type="text"
                                    name="tiers"
                                    value={formData.tiers}
                                    onChange={handleChange}
                                    onFocus={() => setActiveTiersInput(true)}
                                    onBlur={() => {
                                        setTimeout(() => {
                                            setActiveTiersInput(false);
                                        }, 150);
                                    }}
                                    className="form-control"
                                    placeholder="Code Tiers"
                                    autoComplete="off"
                                />
                                {activeTiersInput && (
                                    <div className="compte-suggest-list">
                                        {filterTiers(formData.tiers || '')
                                            .map((t) => (
                                                <button
                                                    key={t.code}
                                                    type="button"
                                                    className="compte-suggest-item"
                                                    onMouseDown={(e) => {
                                                        e.preventDefault();
                                                        setFormData(prev => ({ ...prev, tiers: t.code }));
                                                        setActiveTiersInput(false);
                                                    }}
                                                >
                                                    <strong>{t.code}</strong> — {t.libelle}
                                                </button>
                                            ))}
                                        {filterTiers(formData.tiers || '').length === 0 && (
                                            <div className="compte-suggest-empty">Aucun tiers trouvé</div>
                                        )}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="form-col">
                        <div className="form-group">
                            <label>Section analytique (optionnel)</label>
                            <input
                                type="text"
                                name="section_analytique"
                                value={formData.section_analytique}
                                onChange={handleChange}
                                className="form-control"
                                placeholder="Section analytique"
                                autoComplete="off"
                            />
                        </div>
                    </div>

                    <div className="form-col form-col-btn">
                        <button type="submit" className="btn btn-primary" disabled={loading}>
                            {loading ? 'Ajout...' : 'Ajouter'}
                        </button>
                    </div>
                </div>
            </form>

            <div className="section-header">
                <h3>
                    <span className="icon">📋</span>
                    Écritures en Attente de Migration
                </h3>
                <span className="badge badge-warning">{totalEcritures} en attente</span>
            </div>
            
            <div className="table-responsive">
                <table className="olea-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Libellé</th>
                            <th className="text-right">Débit</th>
                            <th className="text-right">Crédit</th>
                            <th className="text-right">Solde</th>
                            <th className="text-center">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {ecritures.length === 0 ? (
                            <tr>
                                <td colSpan="6" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                                    <div className="empty-state-inline">
                                        <span>✅</span>
                                        <p>Toutes les écritures ont été migrées</p>
                                    </div>
                                </td>
                            </tr>
                        ) : (
                        ecritures.map(ecriture => (
                            <tr 
                                key={ecriture.id} 
                                className={`fade-in ${editingId === ecriture.id ? 'editing' : ''}`}
                                style={editingId === ecriture.id ? { position: 'relative', zIndex: (activeEditCompteInput === ecriture.id || activeEditTiersInput === ecriture.id) ? 100 : 1 } : {}}
                            >
                                {editingId === ecriture.id ? (
                                    <>
                                        <td>
                                            <input
                                                type="date"
                                                name="date_ecriture"
                                                value={editForm.date_ecriture}
                                                onChange={handleEditChange}
                                                className="form-control form-control-sm"
                                            />
                                        </td>
                                        <td 
                                            className="compte-suggest-cell" 
                                            style={{ overflow: 'visible', position: 'relative', zIndex: (activeEditCompteInput === ecriture.id || activeEditTiersInput === ecriture.id) ? 101 : 1 }}
                                        >
                                            <input
                                                type="text"
                                                name="libelle_ecriture"
                                                value={editForm.libelle_ecriture}
                                                onChange={handleEditChange}
                                                className="form-control form-control-sm"
                                                required
                                            />
                                            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                                                {/* Suggestion Compte Contrepartie en Mode Édition */}
                                                <div className="compte-suggest" style={{ flex: 1 }}>
                                                    <input
                                                        type="text"
                                                        name="compte_contrepartie"
                                                        value={editForm.compte_contrepartie || ''}
                                                        onChange={handleEditChange}
                                                        onFocus={() => setActiveEditCompteInput(ecriture.id)}
                                                        onBlur={() => {
                                                            setTimeout(() => {
                                                                setActiveEditCompteInput(null);
                                                            }, 150);
                                                        }}
                                                        className="form-control form-control-sm"
                                                        placeholder="Compte C.P."
                                                        required
                                                        autoComplete="off"
                                                    />
                                                    {activeEditCompteInput === ecriture.id && (
                                                        <div className="compte-suggest-list" style={{ width: '250px' }}>
                                                            {filterComptes(editForm.compte_contrepartie || '')
                                                                .map((compte) => (
                                                                    <button
                                                                        key={compte.code_compte}
                                                                        type="button"
                                                                        className="compte-suggest-item"
                                                                        onMouseDown={(e) => {
                                                                            e.preventDefault();
                                                                            setEditForm(prev => ({ ...prev, compte_contrepartie: compte.code_compte }));
                                                                            setActiveEditCompteInput(null);
                                                                        }}
                                                                    >
                                                                        <strong>{compte.code_compte}</strong> — {compte.libelle_compte}
                                                                    </button>
                                                                ))}
                                                            {filterComptes(editForm.compte_contrepartie || '').length === 0 && (
                                                                <div className="compte-suggest-empty">Aucun compte</div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                                
                                                {/* Suggestion Tiers en Mode Édition */}
                                                <div className="compte-suggest" style={{ flex: 1 }}>
                                                    <input
                                                        type="text"
                                                        name="tiers"
                                                        value={editForm.tiers || ''}
                                                        onChange={handleEditChange}
                                                        onFocus={() => setActiveEditTiersInput(ecriture.id)}
                                                        onBlur={() => {
                                                            setTimeout(() => {
                                                                setActiveEditTiersInput(null);
                                                            }, 150);
                                                        }}
                                                        className="form-control form-control-sm"
                                                        placeholder="Tiers"
                                                        autoComplete="off"
                                                    />
                                                    {activeEditTiersInput === ecriture.id && (
                                                        <div className="compte-suggest-list" style={{ width: '250px' }}>
                                                            {filterTiers(editForm.tiers || '')
                                                                .map((t) => (
                                                                    <button
                                                                        key={t.code}
                                                                        type="button"
                                                                        className="compte-suggest-item"
                                                                        onMouseDown={(e) => {
                                                                            e.preventDefault();
                                                                            setEditForm(prev => ({ ...prev, tiers: t.code }));
                                                                            setActiveEditTiersInput(null);
                                                                        }}
                                                                    >
                                                                        <strong>{t.code}</strong> — {t.libelle}
                                                                    </button>
                                                                ))}
                                                            {filterTiers(editForm.tiers || '').length === 0 && (
                                                                <div className="compte-suggest-empty">Aucun tiers</div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>

                                                <input
                                                    type="text"
                                                    name="section_analytique"
                                                    value={editForm.section_analytique || ''}
                                                    onChange={handleEditChange}
                                                    className="form-control form-control-sm"
                                                    placeholder="Section"
                                                    autoComplete="off"
                                                    style={{ flex: 1 }}
                                                />
                                            </div>
                                        </td>
                                        <td>
                                            <input
                                                type="number"
                                                name="debit"
                                                value={editForm.debit}
                                                onChange={handleEditChange}
                                                className="form-control form-control-sm"
                                                step="0.001"
                                            />
                                        </td>
                                        <td>
                                            <input
                                                type="number"
                                                name="credit"
                                                value={editForm.credit}
                                                onChange={handleEditChange}
                                                className="form-control form-control-sm"
                                                step="0.001"
                                            />
                                        </td>
                                        <td className="text-right">{ecriture.solde.toFixed(3)}</td>
                                        <td className="text-center">
                                            <div className="btn-group">
                                                <button
                                                    className="btn btn-sm btn-success"
                                                    onClick={() => handleSaveEdit(ecriture.id)}
                                                    disabled={loading}
                                                    style={{ fontSize: '0.7rem', padding: '0.25rem 0.45rem', lineHeight: 1 }}
                                                >
                                                    ✓
                                                </button>
                                                <button
                                                    className="btn btn-sm btn-secondary"
                                                    onClick={handleCancelEdit}
                                                    style={{ fontSize: '0.7rem', padding: '0.25rem 0.45rem', lineHeight: 1 }}
                                                >
                                                    ✕
                                                </button>
                                            </div>
                                        </td>
                                    </>
                                ) : (
                                    <>
                                        <td>{new Date(ecriture.date_ecriture).toLocaleDateString('fr-FR')}</td>
                                        <td>
                                            <div style={{ fontWeight: 600 }}>{ecriture.libelle_ecriture}</div>
                                            {(ecriture.compte_contrepartie || ecriture.tiers || ecriture.section_analytique) && (
                                                <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.25rem', fontSize: '0.8rem' }}>
                                                    {ecriture.compte_contrepartie && (
                                                        <span className="badge" style={{ background: '#e0f2fe', color: '#0369a1', padding: '0.15rem 0.4rem', borderRadius: '4px', border: '1px solid #bae6fd' }}>
                                                             C.P: {ecriture.compte_contrepartie}
                                                        </span>
                                                    )}
                                                    {ecriture.tiers && (
                                                        <span className="badge" style={{ background: '#f3f4f6', color: '#374151', padding: '0.15rem 0.4rem', borderRadius: '4px', border: '1px solid #e5e7eb' }}>
                                                            Tiers: {ecriture.tiers}
                                                        </span>
                                                    )}
                                                    {ecriture.section_analytique && (
                                                        <span className="badge" style={{ background: '#fef3c7', color: '#b45309', padding: '0.15rem 0.4rem', borderRadius: '4px', border: '1px solid #fde68a' }}>
                                                             Analytique: {ecriture.section_analytique}
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                        </td>
                                        <td className="text-right">{ecriture.debit.toFixed(3)}</td>
                                        <td className="text-right">{ecriture.credit.toFixed(3)}</td>
                                        <td className="text-right font-bold">{ecriture.solde.toFixed(3)}</td>
                                        <td className="text-center">
                                            <div className="btn-group">
                                                <button
                                                    className="btn btn-sm btn-primary"
                                                    onClick={() => handleMigrateDirect(ecriture)}
                                                    title="Migrer vers Sage"
                                                    disabled={loading}
                                                    style={{ fontSize: '0.7rem', padding: '0.25rem 0.45rem', lineHeight: 1, marginRight: '0.2rem' }}
                                                >
                                                    ✓
                                                </button>
                                                <button
                                                    className="btn btn-sm btn-secondary"
                                                    onClick={() => handleEdit(ecriture)}
                                                    title="Modifier"
                                                    style={{ fontSize: '0.7rem', padding: '0.25rem 0.45rem', lineHeight: 1 }}
                                                >
                                                    ✏️
                                                </button>
                                                <button
                                                    className="btn btn-sm btn-danger"
                                                    onClick={() => handleDelete(ecriture.id)}
                                                    title="Supprimer"
                                                    style={{ fontSize: '0.7rem', padding: '0.25rem 0.45rem', lineHeight: 1, marginLeft: '0.2rem' }}
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

            {totalPages > 1 && (
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
                        {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                            let pageNumber;
                            if (totalPages <= 5) {
                                pageNumber = i + 1;
                            } else if (page <= 3) {
                                pageNumber = i + 1;
                            } else if (page >= totalPages - 2) {
                                pageNumber = totalPages - 4 + i;
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
                        disabled={page === totalPages || loading}
                        onClick={() => setPage(totalPages)}
                        title="Dernière page"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                            <polyline points="13 17 18 12 13 7" />
                            <polyline points="6 17 11 12 6 7" />
                        </svg>
                    </button>
                </div>
            )}
        </div>
    );
}

export default SaisieCaisse;