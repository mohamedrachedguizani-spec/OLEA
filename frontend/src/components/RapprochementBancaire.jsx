// src/components/RapprochementBancaire.jsx
import React, { useEffect, useMemo, useState, useRef } from 'react';
import ReactDOM from 'react-dom';
import ApiService from '../services/api';

function RapprochementBancaire() {
    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [exportLoading, setExportLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [error, setError] = useState('');
    const [comptes, setComptes] = useState([]);
    const [batch, setBatch] = useState(null);
    const [movements, setMovements] = useState([]);
    const [showPreview, setShowPreview] = useState(false);
    const [activeCompteInput, setActiveCompteInput] = useState(null);
    const [dragActive, setDragActive] = useState(false);
    const fileInputRef = useRef(null);

    const [formData, setFormData] = useState({
        periode_debut: '',
        periode_fin: '',
        compte_banque: '',
        compte_comptable: '',
        file: null,
    });

    const [ligne2ByMovement, setLigne2ByMovement] = useState({});

    const journalOptions = ['BI1', 'BI2', 'BI3', 'TN-ATB1', 'UB1', 'UB2', 'UB3'];
    const journalToCompte = {
        BI1: '5320000T',
        BI2: '5320003T',
        BI3: '5320002T',
        'TN-ATB1': '5320001T',
        UB1: '5320007T',
        UB2: '5320009T',
        UB3: '5320008T',
    };

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

    useEffect(() => {
        if (message) {
            const timer = setTimeout(() => {
                setMessage('');
            }, 5000);
            return () => clearTimeout(timer);
        }
    }, [message]);

    useEffect(() => {
        if (error) {
            const timer = setTimeout(() => {
                setError('');
            }, 5000);
            return () => clearTimeout(timer);
        }
    }, [error]);

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
        if (name === 'compte_banque') {
            setFormData((prev) => ({
                ...prev,
                compte_banque: value,
                compte_comptable: journalToCompte[value] || prev.compte_comptable,
            }));
            return;
        }
        setFormData((prev) => ({ ...prev, [name]: value }));
    };

    // Drag and Drop support
    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFormData((prev) => ({ ...prev, file: e.dataTransfer.files[0] }));
        }
    };

    const handleRemoveFile = () => {
        setFormData((prev) => ({ ...prev, file: null }));
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const formatFileSize = (bytes) => {
        if (!bytes) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
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

    // Calcul des statistiques de débit, crédit et équilibre en temps réel
    const stats = useMemo(() => {
        let totalDebit = 0;
        let totalCredit = 0;

        movements.forEach((mov) => {
            const ligne2 = ligne2ByMovement[mov.id] || {};
            
            // Ligne 1 (Banque)
            totalDebit += Number(mov.debit || 0);
            totalCredit += Number(mov.credit || 0);

            // Ligne 2 (Contrepartie)
            totalDebit += Number(mov.credit || 0); // le débit de la ligne 2 est le crédit du mouvement
            totalCredit += Number(mov.debit || 0); // le crédit de la ligne 2 est le débit du mouvement
        });

        const solde = totalDebit - totalCredit;
        const isBalanced = Math.abs(solde) < 0.001; // Équilibre parfait à 3 décimales près

        return {
            totalDebit,
            totalCredit,
            solde,
            isBalanced
        };
    }, [movements, ligne2ByMovement]);

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

    const filterComptes = (query = '') => {
        const value = query.toLowerCase().trim();
        if (!value) return comptes;
        return comptes.filter((compte) =>
            compte.code_compte.toLowerCase().includes(value) ||
            compte.libelle_compte.toLowerCase().includes(value)
        );
    };

    const downloadCsv = (filename, content) => {
        const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    };

    const handleExportSageCsv = async () => {
        if (!batch?.id) return;
        resetMessages();
        setExportLoading(true);
        try {
            const payload = buildSavePayload();
            const result = await ApiService.exportBankReconciliationSageCsv(batch.id, payload);
            downloadCsv(result.filename, result.content);
            setMessage('Export CSV généré avec succès.');
        } catch (err) {
            setError(err.message || 'Erreur lors de l\'export CSV.');
        } finally {
            setExportLoading(false);
        }
    };

    const renderStep1 = () => (
        <form onSubmit={handleUpload} className="sage-upload-section mb-4" style={{ padding: '2rem 1.5rem', background: 'var(--bg-card)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-lg)' }}>
            <div className="form-row mb-4">
                <div className="form-col">
                    <div className="form-group">
                        <label>
                            <span className="icon">📅</span> Période début
                        </label>
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
                        <label>
                            <span className="icon">📅</span> Période fin
                        </label>
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
                        <label>
                            <span className="icon"></span> Compte bancaire (journal)
                        </label>
                        <select
                            name="compte_banque"
                            value={formData.compte_banque}
                            onChange={handleFormChange}
                            className="form-control"
                            required
                        >
                            <option value="">Sélectionner</option>
                            {journalOptions.map((journal) => (
                                <option key={journal} value={journal}>{journal}</option>
                            ))}
                        </select>
                    </div>
                </div>
                <div className="form-col">
                    <div className="form-group">
                        <label>
                            <span className="icon"></span> Compte comptable
                        </label>
                        <input
                            list="comptes-list"
                            name="compte_comptable"
                            value={formData.compte_comptable}
                            onChange={handleFormChange}
                            className="form-control"
                            placeholder="Ex: 5320000T"
                            required
                        />
                    </div>
                </div>
            </div>

            {/* Magnifique zone de Drag & Drop inspirée de SAGE → BFC */}
            <div className="form-group mb-4">
               {/*  <label className="periode-label" style={{ fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '0.5rem' }}>
                    <span className="icon">📁</span> Fichier de rapprochement
                </label> */}
                <div
                    className={`sage-dropzone ${dragActive ? 'drag-active' : ''} ${formData.file ? 'has-file' : ''}`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                    onClick={() => !formData.file && fileInputRef.current?.click()}
                    style={{
                        position: 'relative',
                        border: '2px dashed var(--primary-300)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '3rem 2rem',
                        textAlign: 'center',
                        cursor: formData.file ? 'default' : 'pointer',
                        background: 'linear-gradient(135deg, rgba(183, 72, 43, 0.03) 0%, rgba(47, 52, 58, 0.02) 100%)',
                        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
                    }}
                >
                    <input
                        ref={fileInputRef}
                        type="file"
                        name="file"
                        accept=".pdf,.csv,.xlsx,.xls"
                        onChange={handleFormChange}
                        className="sage-file-input"
                        style={{ display: 'none' }}
                    />

                    {!formData.file ? (
                        <div className="dropzone-content">
                        <div className={`dropzone-icon ${dragActive ? 'bounce' : ''}`}>
                            <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="8" y="8" width="48" height="48" rx="8" strokeDasharray="6 3" />
                                <path d="M32 22v20M22 32h20" strokeWidth="3" strokeLinecap="round" />
                            </svg>
                        </div>
                            <h3 className="dropzone-title" style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                                Glissez-déposez votre relevé bancaire ici
                            </h3>
                            <p className="dropzone-hint" style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: 0 }}>
                                ou <span className="dropzone-link" style={{ color: 'var(--primary-500)', fontWeight: 600, textDecoration: 'underline' }}>parcourez vos fichiers</span>
                            </p>
                            <div className="dropzone-formats" style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                                <span className="format-tag" style={{ padding: '0.2rem 0.6rem', background: 'var(--bg-muted)', borderRadius: 'var(--radius-full)', fontSize: '0.75rem', fontWeight: 600 }}>.pdf</span>
                                <span className="format-tag" style={{ padding: '0.2rem 0.6rem', background: 'var(--bg-muted)', borderRadius: 'var(--radius-full)', fontSize: '0.75rem', fontWeight: 600 }}>.xlsx</span>
                                <span className="format-tag" style={{ padding: '0.2rem 0.6rem', background: 'var(--bg-muted)', borderRadius: 'var(--radius-full)', fontSize: '0.75rem', fontWeight: 600 }}>.csv</span>
                            </div>
                        </div>
                    ) : (
                        <div className="dropzone-file-preview" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1.5rem', width: '100%' }}>
                            <div className="file-preview-icon" style={{ fontSize: '2.5rem' }}>
                                {formData.file.name.endsWith('.pdf') ? '📕' : formData.file.name.endsWith('.csv') ? '📊' : '📗'}
                            </div>
                            <div className="file-preview-info" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                                <span className="file-preview-name" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{formData.file.name}</span>
                                <span className="file-preview-size" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{formatFileSize(formData.file.size)}</span>
                            </div>
                            <button
                            className="file-preview-remove"
                            onClick={(e) => { e.stopPropagation(); handleRemoveFile(); }}
                            title="Retirer le fichier"
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <line x1="18" y1="6" x2="6" y2="18"/>
                                <line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                        </button>
                        </div>
                    )}
                </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                <button type="submit" className="btn btn-primary" style={{ padding: '0.75rem 2.5rem', fontSize: '1rem' }} disabled={loading}>
                    {loading ? (
                        <>
                            <span className="spinner" style={{ marginRight: '0.5rem' }} />
                            Analyse en cours...
                        </>
                    ) : (
                        <>
                            ⚡ Lancer l'analyse du relevé
                        </>
                    )}
                </button>
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <span className="badge badge-info">{movements.length} mouvements</span>
                    <span className={`badge ${stats.isBalanced ? 'badge-success' : 'badge-danger'}`}>
                        {stats.isBalanced ? '⚖️ Équilibré' : '⚠️ Déséquilibré'}
                    </span>
                </div>
            </div>

            {/* Section de statistiques et indicateur d'équilibre dans le style SaisieCaisse/BFC */}
            <div className="brouillard-stats" style={{ display: 'flex', gap: '16px', padding: '16px 24px', background: 'var(--bg-muted)', borderBottom: '1px solid var(--border-light)', flexWrap: 'wrap' }}>
                <div className="stat-item debit" style={{ flex: '1', minWidth: '150px', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '12px 16px', background: 'var(--bg-card)', borderRadius: '10px', border: '1px solid var(--border-light)', borderLeft: '3px solid var(--success)' }}>
                    <span className="stat-label" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '4px' }}>Total Débit</span>
                    <span className="stat-value" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--success)' }}>{stats.totalDebit.toFixed(3)} TND</span>
                </div>
                <div className="stat-item credit" style={{ flex: '1', minWidth: '150px', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '12px 16px', background: 'var(--bg-card)', borderRadius: '10px', border: '1px solid var(--border-light)', borderLeft: '3px solid var(--olea-terracotta)' }}>
                    <span className="stat-label" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '4px' }}>Total Crédit</span>
                    <span className="stat-value" style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--olea-terracotta)' }}>{stats.totalCredit.toFixed(3)} TND</span>
                </div>
                <div className="stat-item solde" style={{ flex: '1', minWidth: '150px', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '12px 16px', background: stats.isBalanced ? 'rgba(31, 157, 85, 0.12)' : 'rgba(183, 72, 43, 0.12)', borderRadius: '10px', border: '1px solid var(--border-light)', borderLeft: `3px solid ${stats.isBalanced ? 'var(--success)' : 'var(--olea-terracotta)'}` }}>
                    <span className="stat-label" style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '4px' }}>Écart / Solde</span>
                    <span className="stat-value" style={{ fontSize: '1.1rem', fontWeight: 700, color: stats.isBalanced ? 'var(--success)' : 'var(--olea-terracotta)' }}>{stats.solde.toFixed(3)} TND</span>
                </div>
            </div>

            <div className="olea-form mb-4">
                <div className="form-row">
                    <div className="form-col form-col-btn">
                        <button
                            type="button"
                            className="btn btn-primary"
                            onClick={handleSaveSageLines}
                            disabled={loading || !stats.isBalanced}
                            title={!stats.isBalanced ? "Le fichier est déséquilibré et ne peut pas être importé dans Sage." : "Sauvegarder les lignes dans la base de données."}
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
                {!stats.isBalanced && (
                    <div className="alert alert-danger slide-down" style={{ marginTop: '1rem', padding: '0.75rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.9rem' }}>
                        <span>⚠️</span>
                        <span>
                            <strong>Rejet Global Sage :</strong> Le rapprochement est déséquilibré de <strong>{Math.abs(stats.solde).toFixed(3)} TND</strong>. Toute pièce déséquilibrée entraîne le rejet global du fichier d’import par Sage. Veuillez vérifier vos écritures.
                        </span>
                    </div>
                )}
            </div>

            <div className="table-responsive sage-table-scroll">
                <table className="olea-table sage-table">
                    <colgroup>
                        <col style={{ width: '80px' }} />
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
                            <th>Ligne</th>
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
                                <td colSpan="8" style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>
                                    Aucun mouvement importé.
                                </td>
                            </tr>
                        ) : (
                            movements.map((mov) => {
                                const ligne2 = ligne2ByMovement[mov.id] || {};
                                return (
                                    <React.Fragment key={mov.id}>
                                        <tr className="fade-in">
                                            <td className="font-bold">L1</td>
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
                                        <tr className={`fade-in sage-row-secondary ${activeCompteInput === mov.id ? 'active-suggest-row' : ''}`}>
                                            <td className="font-bold">L2</td>
                                            <td>{mov.date_operation}</td>
                                            <td className="compte-suggest-cell" style={{ zIndex: activeCompteInput === mov.id ? 100 : 1 }}>
                                                <div className="compte-suggest">
                                                    <input
                                                        type="text"
                                                        className="form-control form-control-sm compte-input"
                                                        value={ligne2.compte || ''}
                                                        onChange={(e) => updateLigne2(mov.id, 'compte', e.target.value)}
                                                        onFocus={() => setActiveCompteInput(mov.id)}
                                                        onBlur={() => {
                                                            setTimeout(() => {
                                                                setActiveCompteInput((prev) => (prev === mov.id ? null : prev));
                                                            }, 150);
                                                        }}
                                                        placeholder="Saisir code ou libellé"
                                                    />
                                                    {activeCompteInput === mov.id && (
                                                        <div className="compte-suggest-list">
                                                            {filterComptes(ligne2.compte || '')
                                                                .map((compte) => (
                                                                    <button
                                                                        key={compte.code_compte}
                                                                        type="button"
                                                                        className="compte-suggest-item"
                                                                        onMouseDown={(e) => {
                                                                            e.preventDefault();
                                                                            updateLigne2(mov.id, 'compte', compte.code_compte);
                                                                            setActiveCompteInput(null);
                                                                        }}
                                                                    >
                                                                        <strong>{compte.code_compte}</strong> — {compte.libelle_compte}
                                                                    </button>
                                                                ))}
                                                            {filterComptes(ligne2.compte || '').length === 0 && (
                                                                <div className="compte-suggest-empty">Aucun compte trouvé</div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
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
                        <button
                            className="btn btn-primary"
                            onClick={handleExportSageCsv}
                            disabled={exportLoading}
                        >
                            {exportLoading ? 'Export…' : 'Exporter CSV'}
                        </button>
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
