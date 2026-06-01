// src/components/RapprochementBancaire.jsx
import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom';
import ApiService from '../services/api';

function RapprochementBancaire() {
    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [comptes, setComptes] = useState([]);
    const [batch, setBatch] = useState(null);
    const [movements, setMovements] = useState([]);
    const [showPreview, setShowPreview] = useState(false);

    const [formData, setFormData] = useState({
        periode_debut: '',
        periode_fin: '',
        compte_banque: '',
        compte_comptable: '',
        file: null,
    });

    const [ligne2ByMovement, setLigne2ByMovement] = useState({});

    useEffect(() => {
        const loadComptes = async () => {
            try {
                const data = await ApiService.getComptes();
                setComptes(Array.isArray(data) ? data : []);
            } catch (err) {
                console.error(err);
            }
        };
        loadComptes();
    }, []);

    const comptesOptions = useMemo(
        () => comptes.map((c) => `${c.code_compte} - ${c.libelle_compte}`),
        [comptes]
    );

    const handleFormChange = (e) => {
        const { name, value, files } = e.target;
        if (name === 'file') {
            setFormData((prev) => ({ ...prev, file: files?.[0] || null }));
            return;
        }
        setFormData((prev) => ({ ...prev, [name]: value }));
    };

    const resetMessages = () => {
        setMessage('');
        setError('');
    };

    const handleUpload = async (e) => {
        e.preventDefault();
        resetMessages();

        if (!formData.file) {
            setError('Veuillez sélectionner un fichier.');
            return;
        }

        if (!formData.compte_banque || !formData.compte_comptable) {
            setError('Veuillez sélectionner le compte bancaire et le compte comptable.');
            return;
        }

        const payload = new FormData();
        payload.append('file', formData.file);
        payload.append('periode_debut', formData.periode_debut || '');
        payload.append('periode_fin', formData.periode_fin || '');
        payload.append('compte_banque', formData.compte_banque.trim());
        payload.append('compte_comptable', formData.compte_comptable.trim());

        setLoading(true);
        try {
            const data = await ApiService.uploadBankReconciliation(payload);
            setBatch(data?.batch || null);
            const batchId = data?.batch?.id;
            if (batchId) {
                const items = await ApiService.getBankReconciliationMovements(batchId);
                setMovements(Array.isArray(items) ? items : []);
            } else {
                setMovements(Array.isArray(data?.preview) ? data.preview : []);
            }
            setStep(2);
            setMessage('Fichier importé avec succès.');
        } catch (err) {
            setError(err.message || 'Erreur lors de l’import.');
        } finally {
            setLoading(false);
        }
    };

    const updateLigne2 = (movementId, field, value) => {
        setLigne2ByMovement((prev) => ({
            ...prev,
            [movementId]: {
                ...(prev[movementId] || {}),
                [field]: value,
            },
        }));
    };

    const buildSavePayload = () => {
        const contreparties = {};
        const tiersByMovement = {};
        const sectionsByMovement = {};
        Object.entries(ligne2ByMovement).forEach(([id, values]) => {
            if (values?.compte) {
                contreparties[Number(id)] = values.compte;
            }
            if (values?.tiers) {
                tiersByMovement[Number(id)] = values.tiers;
            }
            if (values?.section_analytique) {
                sectionsByMovement[Number(id)] = values.section_analytique;
            }
        });

        return {
            contreparties: Object.keys(contreparties).length ? contreparties : null,
            tiers_by_movement: Object.keys(tiersByMovement).length ? tiersByMovement : null,
            sections_by_movement: Object.keys(sectionsByMovement).length ? sectionsByMovement : null,
        };
    };

    const handleSaveSageLines = async () => {
        if (!batch?.id) return;
        resetMessages();
        setLoading(true);
        try {
            const payload = buildSavePayload();
            await ApiService.saveBankReconciliationSageLines(batch.id, payload);
            setMessage('Lignes Sage sauvegardées avec succès.');
        } catch (err) {
            setError(err.message || 'Erreur lors de la sauvegarde.');
        } finally {
            setLoading(false);
        }
    };

    const renderStep1 = () => (
        <form onSubmit={handleUpload} className="olea-form mb-4">
            <div className="form-row">
                <div className="form-col">
                    <div className="form-group">
                        <label>Période début</label>
                        <input
                            type="date"
                            name="periode_debut"
                            value={formData.periode_debut}
                            onChange={handleFormChange}
                            className="form-control"
                        />
                    </div>
                </div>
                <div className="form-col">
                    <div className="form-group">
                        <label>Période fin</label>
                        <input
                            type="date"
                            name="periode_fin"
                            value={formData.periode_fin}
                            onChange={handleFormChange}
                            className="form-control"
                        />
                    </div>
                </div>
                <div className="form-col">
                    <div className="form-group">
                        <label>Compte bancaire (journal)</label>
                        <input
                            list="comptes-list"
                            name="compte_banque"
                            value={formData.compte_banque}
                            onChange={handleFormChange}
                            className="form-control"
                            placeholder="Ex: 521000"
                            required
                        />
                    </div>
                </div>
                <div className="form-col">
                    <div className="form-group">
                        <label>Compte comptable</label>
                        <input
                            list="comptes-list"
                            name="compte_comptable"
                            value={formData.compte_comptable}
                            onChange={handleFormChange}
                            className="form-control"
                            placeholder="Ex: 521000"
                            required
                        />
                    </div>
                </div>
                <div className="form-col form-col-lg">
                    <div className="form-group">
                        <label>Fichier (PDF / Excel / CSV)</label>
                        <input
                            type="file"
                            name="file"
                            accept=".pdf,.csv,.xlsx,.xls"
                            onChange={handleFormChange}
                            className="form-control"
                            required
                        />
                    </div>
                </div>
                <div className="form-col form-col-btn">
                    <button type="submit" className="btn btn-primary" disabled={loading}>
                        {loading ? 'Import…' : 'Importer'}
                    </button>
                </div>
            </div>
            <datalist id="comptes-list">
                {comptesOptions.map((option) => (
                    <option key={option} value={option.split(' - ')[0]} />
                ))}
            </datalist>
        </form>
    );

    const renderStep2 = () => (
        <>
            <div className="section-header">
                <h3>
                    <span className="icon">📋</span>
                    Mouvements importés
                </h3>
                <span className="badge badge-warning">{movements.length} mouvements</span>
            </div>

            <div className="olea-form mb-4">
                <div className="form-row">
                    <div className="form-col form-col-btn">
                        <button
                            type="button"
                            className="btn btn-primary"
                            onClick={handleSaveSageLines}
                            disabled={loading}
                        >
                            {loading ? 'Sauvegarde…' : 'Sauvegarder Sage'}
                        </button>
                    </div>
                    <div className="form-col form-col-btn">
                        <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={() => setShowPreview(true)}
                        >
                            Prévisualiser format Sage
                        </button>
                    </div>
                </div>
            </div>

            <div className="table-responsive sage-table-scroll">
                <table className="olea-table sage-table">
                    <colgroup>
                        <col style={{ width: '130px' }} />
                        <col style={{ width: '140px' }} />
                        <col style={{ width: '140px' }} />
                        <col style={{ width: '110px' }} />
                        <col style={{ width: '110px' }} />
                        <col style={{ width: '140px' }} />
                        <col style={{ width: '320px' }} />
                    </colgroup>
                    <thead>
                        <tr>
                            <th>Date écriture</th>
                            <th>Compte</th>
                            <th>Tiers</th>
                            <th className="text-right">Débit</th>
                            <th className="text-right">Crédit</th>
                            <th>Section</th>
                            <th>Libellé</th>
                        </tr>
                    </thead>
                    <tbody>
                        {movements.length === 0 ? (
                            <tr>
                                <td colSpan="7" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                                    Aucun mouvement importé.
                                </td>
                            </tr>
                        ) : (
                            movements.map((mov) => {
                                const ligne2 = ligne2ByMovement[mov.id] || {};
                                return (
                                    <React.Fragment key={mov.id}>
                                        <tr className="fade-in">
                                            <td>{mov.date_operation}</td>
                                            <td>
                                                <input
                                                    value={batch?.compte_comptable || ''}
                                                    className="form-control form-control-sm compte-input"
                                                    readOnly
                                                />
                                            </td>
                                            <td>
                                                <input
                                                    value={ligne2.tiers || ''}
                                                    onChange={(e) => updateLigne2(mov.id, 'tiers', e.target.value)}
                                                    className="form-control form-control-sm"
                                                    placeholder="Tiers"
                                                />
                                            </td>
                                            <td className="text-right">{Number(mov.debit || 0).toFixed(3)}</td>
                                            <td className="text-right">{Number(mov.credit || 0).toFixed(3)}</td>
                                            <td>
                                                <input
                                                    value={ligne2.section_analytique || ''}
                                                    onChange={(e) => updateLigne2(mov.id, 'section_analytique', e.target.value)}
                                                    className="form-control form-control-sm"
                                                    placeholder="Section"
                                                />
                                            </td>
                                            <td>{mov.libelle}</td>
                                        </tr>
                                        <tr className="fade-in sage-row-secondary">
                                            <td>{mov.date_operation}</td>
                                            <td>
                                                <input
                                                    list="comptes-list"
                                                    value={ligne2.compte || ''}
                                                    onChange={(e) => updateLigne2(mov.id, 'compte', e.target.value)}
                                                    className="form-control form-control-sm compte-input"
                                                    placeholder="Compte"
                                                />
                                            </td>
                                            <td>
                                                <input
                                                    value={ligne2.tiers || ''}
                                                    className="form-control form-control-sm"
                                                    readOnly
                                                />
                                            </td>
                                            <td className="text-right">{Number(mov.credit || 0).toFixed(3)}</td>
                                            <td className="text-right">{Number(mov.debit || 0).toFixed(3)}</td>
                                            <td>
                                                <input
                                                    value={ligne2.section_analytique || ''}
                                                    className="form-control form-control-sm"
                                                    readOnly
                                                />
                                            </td>
                                            <td>{mov.libelle}</td>
                                        </tr>
                                    </React.Fragment>
                                );
                            })
                        )}
                    </tbody>
                </table>
            </div>
        </>
    );

    const PreviewModal = () => {
        if (!showPreview) return null;

        const numeroPiece = `${batch?.compte_comptable || ''}-${new Date().toLocaleDateString('fr-FR').replace(/\//g, '')}`;
        const previewLines = movements.flatMap((mov) => {
            const ligne2 = ligne2ByMovement[mov.id] || {};
            return [
                {
                    line_no: 'L1',
                    societe: 'TN01',
                    journal: batch?.compte_banque || '-',
                    date_ecriture: mov.date_operation,
                    compte: batch?.compte_comptable || '-',
                    tiers: ligne2.tiers || '',
                    debit: Number(mov.debit || 0).toFixed(3),
                    credit: Number(mov.credit || 0).toFixed(3),
                    section: ligne2.section_analytique || '',
                    numero_piece: numeroPiece,
                    libelle: mov.libelle,
                    devise: 'TND',
                    type_piece: 'BQ',
                },
                {
                    line_no: 'L2',
                    societe: 'TN01',
                    journal: batch?.compte_banque || '-',
                    date_ecriture: mov.date_operation,
                    compte: ligne2.compte || '-',
                    tiers: ligne2.tiers || '',
                    debit: Number(mov.credit || 0).toFixed(3),
                    credit: Number(mov.debit || 0).toFixed(3),
                    section: ligne2.section_analytique || '',
                    numero_piece: numeroPiece,
                    libelle: mov.libelle,
                    devise: 'TND',
                    type_piece: 'BQ',
                },
            ];
        });

        return ReactDOM.createPortal(
            <div className="csv-preview-modal">
                <div className="csv-preview-backdrop" onClick={() => setShowPreview(false)}></div>
                <div className="csv-preview-container">
                    <div className="csv-preview-header">
                        <div className="csv-preview-title">
                            <span>📄</span>
                            <h3>Prévisualisation format Sage</h3>
                        </div>
                        <div className="csv-preview-meta">
                            <span className="csv-count">{previewLines.length} lignes</span>
                        </div>
                        <button className="csv-preview-close" onClick={() => setShowPreview(false)}>✕</button>
                    </div>
                    <div className="csv-preview-body">
                        <table className="csv-preview-table">
                            <thead>
                                <tr>
                                    <th>Ligne</th>
                                    <th>Société</th>
                                    <th>Journal</th>
                                    <th>Date écriture</th>
                                    <th>Compte</th>
                                    <th>Tiers</th>
                                    <th>Débit</th>
                                    <th>Crédit</th>
                                    <th>Section</th>
                                    <th>Numéro pièce</th>
                                    <th>Libellé</th>
                                    <th>Devise</th>
                                    <th>Type pièce</th>
                                </tr>
                            </thead>
                            <tbody>
                                {previewLines.length === 0 ? (
                                    <tr>
                                        <td colSpan="13" className="csv-preview-empty">Aucune ligne à afficher</td>
                                    </tr>
                                ) : (
                                    previewLines.map((line, idx) => (
                                        <tr key={`${line.line_no}-${idx}`}>
                                            <td>{line.line_no}</td>
                                            <td>{line.societe}</td>
                                            <td>{line.journal}</td>
                                            <td>{line.date_ecriture}</td>
                                            <td>{line.compte}</td>
                                            <td>{line.tiers}</td>
                                            <td>{line.debit}</td>
                                            <td>{line.credit}</td>
                                            <td>{line.section}</td>
                                            <td>{line.numero_piece}</td>
                                            <td>{line.libelle}</td>
                                            <td>{line.devise}</td>
                                            <td>{line.type_piece}</td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                    <div className="csv-preview-footer">
                        <button className="btn btn-secondary" onClick={() => setShowPreview(false)}>
                            ✕ Fermer
                        </button>
                    </div>
                </div>
            </div>,
            document.body
        );
    };

    return (
        <div className="olea-card fade-in">
            <div className="card-header">
                <h2 className="card-title">
                    <span className="icon">🏦</span>
                    Rapprochement Bancaire
                </h2>
            </div>

            {message && (
                <div className="alert alert-success slide-down">{message}</div>
            )}
            {error && (
                <div className="alert alert-danger slide-down">{error}</div>
            )}

            {step === 1 && renderStep1()}
            {step === 2 && renderStep2()}

            {step === 2 && (
                <div className="form-actions">
                    <button className="btn btn-secondary" onClick={() => setStep(1)}>
                        Retour à l’import
                    </button>
                </div>
            )}
            <PreviewModal />
        </div>
    );
}

export default RapprochementBancaire;
