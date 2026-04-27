// src/components/SaisieCaisse.jsx
import ApiService from '../services/api';
import LibelleAutocomplete from './LibelleAutocomplete';
import React, { useState, useEffect, useRef, useCallback } from 'react';


function SaisieCaisse({ refreshTrigger }) {
    const [formData, setFormData] = useState({
        date_ecriture: new Date().toISOString().split('T')[0],
        libelle_ecriture: '',
        debit: '',
        credit: ''
    });
    const [ecritures, setEcritures] = useState([]);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [editingId, setEditingId] = useState(null);
    const [editForm, setEditForm] = useState({});
    const debitInputRef = useRef(null);
    const creditInputRef = useRef(null);
    const lastSuggestedFieldRef = useRef(null);

    const normalizeText = (text = '') =>
        text
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();

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
            const data = await ApiService.getEcrituresCaisse({ limit: 500 });
            // Filtrer les écritures migrées et inverser l'ordre: ancien vers récent
            const ecrituresNonMigrees = data.filter(e => !e.est_migree);
            setEcritures(ecrituresNonMigrees.reverse());
        } catch (error) {
            console.error('Erreur lors du chargement:', error);
        }
    }, []);

    useEffect(() => {
        loadEcritures();
    }, [loadEcritures, refreshTrigger]);

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: (name === 'debit' || name === 'credit')
                ? (value === '' ? '' : parseFloat(value))
                : value
        }));
    };

    const handleLibelleSelect = (libelle) => {
        setFormData(prev => ({
            ...prev,
            libelle_ecriture: libelle
        }));
        autoFocusMontantField(libelle);
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
                credit: ''
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

    const handleEdit = (ecriture) => {
        setEditingId(ecriture.id);
        setEditForm({
            date_ecriture: ecriture.date_ecriture.split('T')[0],
            libelle_ecriture: ecriture.libelle_ecriture,
            debit: ecriture.debit,
            credit: ecriture.credit
        });
    };

    const handleCancelEdit = () => {
        setEditingId(null);
        setEditForm({});
    };

    const handleSaveEdit = async (id) => {
        setLoading(true);
        try {
            await ApiService.updateEcritureCaisse(id, editForm);
            setMessage('Écriture modifiée avec succès!');
            setEditingId(null);
            setEditForm({});
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
                    <span className="icon">💰</span>
                    Saisie des Écritures de Caisse
                </h2>
            </div>
            
            {message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

            <form onSubmit={handleSubmit} className="olea-form mb-4">
                <div className="form-row">
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
                <span className="badge badge-warning">{ecritures.length} en attente</span>
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
                            <tr key={ecriture.id} className={`fade-in ${editingId === ecriture.id ? 'editing' : ''}`}>
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
                                        <td>
                                            <input
                                                type="text"
                                                name="libelle_ecriture"
                                                value={editForm.libelle_ecriture}
                                                onChange={handleEditChange}
                                                className="form-control form-control-sm"
                                            />
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
                                                >
                                                    ✓
                                                </button>
                                                <button
                                                    className="btn btn-sm btn-secondary"
                                                    onClick={handleCancelEdit}
                                                >
                                                    ✕
                                                </button>
                                            </div>
                                        </td>
                                    </>
                                ) : (
                                    <>
                                        <td>{new Date(ecriture.date_ecriture).toLocaleDateString('fr-FR')}</td>
                                        <td>{ecriture.libelle_ecriture}</td>
                                        <td className="text-right">{ecriture.debit.toFixed(3)}</td>
                                        <td className="text-right">{ecriture.credit.toFixed(3)}</td>
                                        <td className="text-right font-bold">{ecriture.solde.toFixed(3)}</td>
                                        <td className="text-center">
                                            <div className="btn-group">
                                                <button
                                                    className="btn btn-sm btn-secondary"
                                                    onClick={() => handleEdit(ecriture)}
                                                    title="Modifier"
                                                >
                                                    ✏️
                                                </button>
                                                <button
                                                    className="btn btn-sm btn-danger"
                                                    onClick={() => handleDelete(ecriture.id)}
                                                    title="Supprimer"
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
        </div>
    );
}

export default SaisieCaisse;