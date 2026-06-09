// src/components/MigrationSage.jsx
import React, { useState, useEffect } from 'react';
import ApiService from '../services/api';

function MigrationSage({ onMigrationComplete, refreshTrigger }) {
    const [ecrituresAMigrer, setEcrituresAMigrer] = useState([]);
    const [migrationForm, setMigrationForm] = useState({});
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [comptes, setComptes] = useState([]);
    const [customCompte1, setCustomCompte1] = useState({});
    const [customCompte2, setCustomCompte2] = useState({});
    const [useCustomCompte1, setUseCustomCompte1] = useState({});
    const [useCustomCompte2, setUseCustomCompte2] = useState({});
    const [activeCompteInput, setActiveCompteInput] = useState(null);

    const [page, setPage] = useState(1);
    const [pageSize] = useState(20);
    const [totalPages, setTotalPages] = useState(1);
    const [totalEcritures, setTotalEcritures] = useState(0);

    useEffect(() => {
        loadEcrituresAMigrer();
        loadComptes();
    }, [refreshTrigger, page, pageSize]);

    const loadEcrituresAMigrer = async () => {
        try {
            const data = await ApiService.getEcrituresAMigrer({ page, page_size: pageSize });
            setEcrituresAMigrer(Array.isArray(data?.items) ? data.items : []);
            setTotalEcritures(Number(data?.total ?? 0));
            setTotalPages(Number(data?.pages ?? 1));
        } catch (error) {
            // Pas de log console
        }
    };

    const loadComptes = async () => {
        try {
            const data = await ApiService.getComptes();
            setComptes(data);
        } catch (error) {
            // Pas de log console
        }
    };

    const canGoPrev = page > 1;
    const canGoNext = page < totalPages;

    const handleMigrationChange = (ecritureId, ligne, field, value) => {
        setMigrationForm(prev => ({
            ...prev,
            [ecritureId]: {
                ...prev[ecritureId],
                [ligne]: {
                    ...(prev[ecritureId]?.[ligne] || {}),
                    [field]: value
                }
            }
        }));
    };

    const getCompte1 = () => {
        // Compte caisse toujours fixe
        return '5411000T';
    };

    const getCompte2 = (ecritureId) => {
        if (useCustomCompte2[ecritureId]) {
            return customCompte2[ecritureId] || '';
        }
        return migrationForm[ecritureId]?.ligne2?.compte || '';
    };

    const handleMigrer = async (ecriture) => {
        const compte1 = getCompte1(ecriture.id);
        const compte2 = getCompte2(ecriture.id);
        const formData = migrationForm[ecriture.id];
        
        if (!compte1) {
            setMessage('Veuillez sélectionner ou saisir un compte pour la ligne 1');
            return;
        }
        
        if (!compte2) {
            setMessage('Veuillez sélectionner ou saisir un compte pour la ligne 2');
            return;
        }

        setLoading(true);
        setMessage('');

        try {
            const migrationRequest = {
                ecriture_caisse_id: ecriture.id,
                ligne1: {
                    date_compta: ecriture.date_ecriture,
                    compte: compte1,
                    tiers: formData?.ligne1?.tiers || '',
                    section_analytique: formData?.ligne1?.section_analytique || '',
                    libelle_ecriture: ecriture.libelle_ecriture,
                    numero_piece: `MGCAI${new Date(ecriture.date_ecriture).getMonth() + 1}${new Date(ecriture.date_ecriture).getFullYear()}`
                },
                ligne2: {
                    date_compta: ecriture.date_ecriture,
                    compte: compte2,
                    tiers: formData?.ligne2?.tiers || '',
                    section_analytique: formData?.ligne2?.section_analytique || '',
                    libelle_ecriture: ecriture.libelle_ecriture,
                    numero_piece: `MGCAI${new Date(ecriture.date_ecriture).getMonth() + 1}${new Date(ecriture.date_ecriture).getFullYear()}`
                }
            };

            await ApiService.migrerEcriture(migrationRequest);
            setMessage('Écriture migrée avec succès!');
            loadEcrituresAMigrer();
            if (onMigrationComplete) {
                onMigrationComplete();
            }
        } catch (error) {
            setMessage('Erreur lors de la migration: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    const handleMigrerTout = async () => {
        const migrations = [];
        
        for (const ecriture of ecrituresAMigrer) {
            const compte1 = getCompte1(ecriture.id);
            const compte2 = getCompte2(ecriture.id);
            const formData = migrationForm[ecriture.id];
            
            if (!compte1 || !compte2) {
                setMessage(`Veuillez remplir les comptes pour toutes les écritures`);
                return;
            }
            
            migrations.push({
                ecriture_caisse_id: ecriture.id,
                ligne1: {
                    date_compta: ecriture.date_ecriture,
                    compte: compte1,
                    tiers: formData?.ligne1?.tiers || '',
                    section_analytique: formData?.ligne1?.section_analytique || '',
                    libelle_ecriture: ecriture.libelle_ecriture,
                    numero_piece: `MGCAI${new Date(ecriture.date_ecriture).getMonth() + 1}${new Date(ecriture.date_ecriture).getFullYear()}`
                },
                ligne2: {
                    date_compta: ecriture.date_ecriture,
                    compte: compte2,
                    tiers: formData?.ligne2?.tiers || '',
                    section_analytique: formData?.ligne2?.section_analytique || '',
                    libelle_ecriture: ecriture.libelle_ecriture,
                    numero_piece: `MGCAI${new Date(ecriture.date_ecriture).getMonth() + 1}${new Date(ecriture.date_ecriture).getFullYear()}`
                }
            });
        }
        
        if (migrations.length === 0) {
            setMessage('Aucune écriture à migrer');
            return;
        }

        setLoading(true);
        setMessage('');

        try {
            const result = await ApiService.migrerTout(migrations);
            setMessage(result.message);
            
            // Nettoyage automatique après migration réussie
            if (result.resultats && result.resultats.length > 0) {
                try {
                    const cleanupResult = await ApiService.nettoyerHistoriqueMigre();
                    setMessage(prev => `${prev} | ${cleanupResult.message}`);
                } catch (cleanupError) {
                    // Pas de log console
                }
            }
            
            loadEcrituresAMigrer();
            if (onMigrationComplete) {
                onMigrationComplete();
            }
        } catch (error) {
            setMessage('Erreur lors de la migration: ' + error.message);
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

    return (
        <div className="olea-card fade-in">
            <div className="card-header">
                <h2 className="card-title">
                    <span className="icon">📤</span>
                    Migration vers Sage
                </h2>
                {ecrituresAMigrer.length > 0 && (
                    <div className="header-actions">
                        <span className="badge badge-primary">{totalEcritures} écriture(s)</span>
                        <button
                            className="btn btn-primary"
                            onClick={handleMigrerTout}
                            disabled={loading}
                        >
                            {/* <span className="icon">🚀</span> */}
                            {loading ? 'Migration...' : 'Migrer tout'}
                        </button>
                    </div>
                )}
            </div>
            
            {message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

            {ecrituresAMigrer.length === 0 ? (
                <div className="empty-state">
                    <div className="empty-icon">✅</div>
                    <h3>Aucune écriture à migrer</h3>
                    <p>Toutes les écritures ont été migrées vers Sage.</p>
                </div>
            ) : (
                <div className="migration-list">
                    {ecrituresAMigrer.map(ecriture => (
                        <div key={ecriture.id} className="migration-card fade-in">
                            {/* En-tête de la carte */}
                            <div className="migration-card-header">
                                <div className="migration-info">
                                    <div className="migration-date">
                                        <span className="icon">📅</span>
                                        {new Date(ecriture.date_ecriture).toLocaleDateString('fr-FR')}
                                    </div>
                                    <div className="migration-libelle">{ecriture.libelle_ecriture}</div>
                                </div>
                                <div className="migration-amounts">
                                    {ecriture.debit > 0 && (
                                        <span className="amount debit">
                                            <span className="label">Débit</span>
                                            <span className="value">{ecriture.debit.toFixed(3)} TND</span>
                                        </span>
                                    )}
                                    {ecriture.credit > 0 && (
                                        <span className="amount credit">
                                            <span className="label">Crédit</span>
                                            <span className="value">{ecriture.credit.toFixed(3)} TND</span>
                                        </span>
                                    )}
                                </div>
                            </div>
                            
                            {/* Corps avec les deux lignes */}
                            <div className="migration-card-body">
                                {/* Ligne 1 - Caisse (compte fixe) */}
                                <div className="ligne-config">
                                    <div className="ligne-header">
                                        <span className="ligne-badge caisse">Ligne 1</span>
                                        <span className="ligne-title">Compte Caisse</span>
                                    </div>
                                    
                                    {/* Affichage du montant attendu pour ligne 1 */}
                                    {/* <div className="ligne-montant-preview">
                                        <div className={`montant-box ${ecriture.debit > 0 ? 'debit' : 'credit'}`}>
                                            <span className="montant-type">{ecriture.debit > 0 ? 'DÉBIT' : 'CRÉDIT'}</span>
                                            <span className="montant-value">
                                                {ecriture.debit > 0 
                                                    ? ecriture.debit.toFixed(3) 
                                                    : ecriture.credit.toFixed(3)} TND
                                            </span>
                                        </div>
                                    </div> */}
                                    
                                    <div className="ligne-fields">
                                        <div className="field-group">
                                            <label>Compte</label>
                                            <div className="compte-fixe">
                                                <span className="compte-code">5411000T</span>
                                                <span className="compte-libelle">Caisse</span>
                                            </div>
                                        </div>
                                        <div className="field-group">
                                            <label>Tiers</label>
                                            <input
                                                type="text"
                                                className="form-control"
                                                placeholder="Tiers (optionnel)"
                                                value={migrationForm[ecriture.id]?.ligne1?.tiers || ''}
                                                onChange={(e) => handleMigrationChange(ecriture.id, 'ligne1', 'tiers', e.target.value)}
                                            />
                                        </div>
                                        <div className="field-group">
                                            <label>Section analytique</label>
                                            <input
                                                type="text"
                                                className="form-control"
                                                placeholder="Section (optionnel)"
                                                value={migrationForm[ecriture.id]?.ligne1?.section_analytique || ''}
                                                onChange={(e) => handleMigrationChange(ecriture.id, 'ligne1', 'section_analytique', e.target.value)}
                                            />
                                        </div>
                                    </div>
                                </div>
                                
                                {/* Séparateur avec flèche */}
                                <div className="ligne-separator">
                                    <span className="arrow">⟷</span>
                                </div>
                                
                                {/* Ligne 2 - Contrepartie */}
                                <div className="ligne-config">
                                    <div className="ligne-header">
                                        <span className="ligne-badge contrepartie">Ligne 2</span>
                                        <span className="ligne-title">Contre partie</span>
                                        <label className="toggle-manual">
                                            <input
                                                type="checkbox"
                                                checked={useCustomCompte2[ecriture.id] || false}
                                                onChange={(e) => setUseCustomCompte2(prev => ({
                                                    ...prev,
                                                    [ecriture.id]: e.target.checked
                                                }))}
                                            />
                                            <span className="toggle-slider"></span>
                                            <span className="toggle-label">Manuel</span>
                                        </label>
                                    </div>
                                    
                                    {/* Affichage du montant attendu pour ligne 2 (inversé) */}
                                    {/* <div className="ligne-montant-preview">
                                        <div className={`montant-box ${ecriture.credit > 0 ? 'debit' : 'credit'}`}>
                                            <span className="montant-type">{ecriture.credit > 0 ? 'DÉBIT' : 'CRÉDIT'}</span>
                                            <span className="montant-value">
                                                {ecriture.credit > 0 
                                                    ? ecriture.credit.toFixed(3) 
                                                    : ecriture.debit.toFixed(3)} TND
                                            </span>
                                        </div>
                                    </div> */}
                                    
                                    <div className="ligne-fields">
                                        <div className="field-group">
                                            <label>Compte <span className="required">*</span></label>
                                            {useCustomCompte2[ecriture.id] ? (
                                                <input
                                                    type="text"
                                                    className="form-control"
                                                    placeholder="Saisir le compte"
                                                    value={customCompte2[ecriture.id] || ''}
                                                    onChange={(e) => setCustomCompte2(prev => ({
                                                        ...prev,
                                                        [ecriture.id]: e.target.value
                                                    }))}
                                                />
                                            ) : (
                                                <div className="compte-suggest">
                                                    <input
                                                        type="text"
                                                        className="form-control"
                                                        value={migrationForm[ecriture.id]?.ligne2?.compte || ''}
                                                        onChange={(e) => handleMigrationChange(ecriture.id, 'ligne2', 'compte', e.target.value)}
                                                        onFocus={() => setActiveCompteInput(ecriture.id)}
                                                        onBlur={() => {
                                                            setTimeout(() => {
                                                                setActiveCompteInput((prev) => (prev === ecriture.id ? null : prev));
                                                            }, 150);
                                                        }}
                                                        placeholder="Saisir code ou libellé"
                                                        required
                                                    />
                                                    {activeCompteInput === ecriture.id && (
                                                        <div className="compte-suggest-list">
                                                            {filterComptes(migrationForm[ecriture.id]?.ligne2?.compte || '')
                                                                .map((compte) => (
                                                                    <button
                                                                        key={compte.code_compte}
                                                                        type="button"
                                                                        className="compte-suggest-item"
                                                                        onMouseDown={(e) => {
                                                                            e.preventDefault();
                                                                            handleMigrationChange(ecriture.id, 'ligne2', 'compte', compte.code_compte);
                                                                            setActiveCompteInput(null);
                                                                        }}
                                                                    >
                                                                        <strong>{compte.code_compte}</strong> — {compte.libelle_compte}
                                                                    </button>
                                                                ))}
                                                            {filterComptes(migrationForm[ecriture.id]?.ligne2?.compte || '').length === 0 && (
                                                                <div className="compte-suggest-empty">Aucun compte trouvé</div>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                        <div className="field-group">
                                            <label>Tiers</label>
                                            <input
                                                type="text"
                                                className="form-control"
                                                placeholder="Tiers (optionnel)"
                                                value={migrationForm[ecriture.id]?.ligne2?.tiers || ''}
                                                onChange={(e) => handleMigrationChange(ecriture.id, 'ligne2', 'tiers', e.target.value)}
                                            />
                                        </div>
                                        <div className="field-group">
                                            <label>Section analytique</label>
                                            <input
                                                type="text"
                                                className="form-control"
                                                placeholder="Section (optionnel)"
                                                value={migrationForm[ecriture.id]?.ligne2?.section_analytique || ''}
                                                onChange={(e) => handleMigrationChange(ecriture.id, 'ligne2', 'section_analytique', e.target.value)}
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            {/* Footer avec action */}
                            <div className="migration-card-footer">
                                <div className="num-piece">
                                    <span className="label">N° Pièce:</span>
                                    <span className="value">MGCAI{new Date(ecriture.date_ecriture).getMonth() + 1}{new Date(ecriture.date_ecriture).getFullYear()}</span>
                                </div>
                                <button
                                    className="btn btn-success"
                                    onClick={() => handleMigrer(ecriture)}
                                    disabled={loading || (!getCompte1(ecriture.id) || !getCompte2(ecriture.id))}
                                >
                                    <span className="icon">✓</span>
                                    Migrer cette écriture
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {ecrituresAMigrer.length > 0 && totalPages > 1 && (
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

export default MigrationSage;