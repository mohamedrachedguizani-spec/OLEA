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
                                onChange={(value) => setFormData(prev => ({ ...prev, libelle_ecriture: value }))}
                                onSelect={handleLibelleSelect}
                            />
                        </div>
                    </div>
                    
                    <div className="form-col">
                        <div className="form-group">
                            <label>Débit</label>
                            <input
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