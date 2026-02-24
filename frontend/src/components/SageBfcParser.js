// src/components/SageBfcParser.js
import React, { useState, useCallback, useEffect, useMemo } from 'react';
import ApiService from '../services/api';
import SageBfcUpload from './sage-bfc/SageBfcUpload';
import SageBfcPnl from './sage-bfc/SageBfcPnl';
import SageBfcLignes from './sage-bfc/SageBfcLignes';
import SageBfcValidations from './sage-bfc/SageBfcValidations';
import SageBfcDashboard from './sage-bfc/SageBfcDashboard';
import './sage-bfc/SageBfcParser.css';

const ALL_PERIODS_KEY = '__all_periods__';

const RESUME_SUM_KEYS = [
    'ca_brut',
    'retrocessions',
    'ca_net',
    'autres_produits',
    'total_produits',
    'frais_personnel',
    'honoraires',
    'frais_commerciaux',
    'impots_taxes',
    'fonctionnement',
    'autres_charges',
    'total_charges',
    'ebitda',
    'produits_financiers',
    'charges_financieres',
    'resultat_financier',
    'dotations',
    'resultat_avant_impot',
    'impot_societes',
    'resultat_net'
];

function buildAllPeriodsResult(sortedMonths, monthlyData) {
    if (!sortedMonths.length) return null;

    const resume = RESUME_SUM_KEYS.reduce((acc, key) => {
        acc[key] = 0;
        return acc;
    }, {});

    const lignes = [];
    const validations = [];
    const alertesSet = new Set();

    sortedMonths.forEach((monthKey) => {
        const monthResult = monthlyData[monthKey]?.result;
        const monthResume = monthResult?.resume || {};

        RESUME_SUM_KEYS.forEach((key) => {
            resume[key] += Number(monthResume[key] || 0);
        });

        (monthResult?.lignes || []).forEach((l) => {
            lignes.push({ ...l, mois: monthKey });
        });

        (monthResult?.validations || []).forEach((v) => {
            validations.push({ ...v, periode: monthKey });
        });

        (monthResult?.alertes_globales || []).forEach((a) => alertesSet.add(a));
    });

    resume.ebitda_pct = resume.ca_net ? (resume.ebitda / resume.ca_net) * 100 : 0;
    resume.resultat_net_pct = resume.ca_net ? (resume.resultat_net / resume.ca_net) * 100 : 0;

    return {
        periode: ALL_PERIODS_KEY,
        resume,
        lignes,
        validations,
        alertes_globales: [...alertesSet]
    };
}

function SageBfcParser({ refreshTrigger }) {
    const [activeStep, setActiveStep] = useState('upload'); // upload | results
    const [activeTab, setActiveTab] = useState('dashboard'); // dashboard | pnl | lignes | validations
    const [loading, setLoading] = useState(false);
    const [loadingData, setLoadingData] = useState(true);
    const [error, setError] = useState(null);
    const [mappingStats, setMappingStats] = useState(null);
    const [fileName, setFileName] = useState('');

    // Données mensuelles chargées depuis le backend
    const [monthlyData, setMonthlyData] = useState({});
    const [selectedMonth, setSelectedMonth] = useState(null);

    // Mois triés chronologiquement
    const sortedMonths = useMemo(() => {
        return Object.keys(monthlyData).sort();
    }, [monthlyData]);

    // Sélectionner toutes les périodes par défaut
    useEffect(() => {
        if (sortedMonths.length > 0 && !selectedMonth) {
            setSelectedMonth(ALL_PERIODS_KEY);
        }
    }, [sortedMonths, selectedMonth]);

    // Résultat du mois sélectionné
    const currentResult = useMemo(() => {
        if (!selectedMonth) return null;
        if (selectedMonth === ALL_PERIODS_KEY) {
            return buildAllPeriodsResult(sortedMonths, monthlyData);
        }
        if (!monthlyData[selectedMonth]) return null;
        return monthlyData[selectedMonth].result;
    }, [selectedMonth, monthlyData, sortedMonths]);

    // Résultat du mois précédent (pour comparaison)
    const previousResult = useMemo(() => {
        if (!selectedMonth || selectedMonth === ALL_PERIODS_KEY) return null;
        const idx = sortedMonths.indexOf(selectedMonth);
        if (idx <= 0) return null;
        return monthlyData[sortedMonths[idx - 1]]?.result || null;
    }, [selectedMonth, sortedMonths, monthlyData]);

    // Toutes les lignes accumulées de tous les mois
    const allLignes = useMemo(() => {
        return Object.entries(monthlyData).flatMap(([periode, data]) =>
            (data.result?.lignes || []).map(l => ({ ...l, mois: periode }))
        );
    }, [monthlyData]);

    // Charger les données mensuelles depuis le backend au montage
    const loadMonthlyData = useCallback(async () => {
        try {
            setLoadingData(true);
            const months = await ApiService.getSageBfcMonthlyList();
            const data = {};
            for (const month of months) {
                data[month.periode] = {
                    result: {
                        periode: month.periode,
                        resume: month.resume,
                        lignes: [],
                        validations: [],
                        alertes_globales: []
                    },
                    fileName: month.file_name,
                    lignesCount: month.lignes_count,
                    uploadDate: month.created_at
                };
            }
            setMonthlyData(data);

            // Si des mois existent et qu'on est sur l'upload, proposer les résultats
            if (months.length > 0 && !selectedMonth) {
                setSelectedMonth(months[months.length - 1].periode);
            }
        } catch (err) {
            console.error('Erreur chargement données mensuelles:', err);
        } finally {
            setLoadingData(false);
        }
    }, []);

    // Charger les données complètes d'un mois quand on le sélectionne
    const loadMonthDetail = useCallback(async (monthKey) => {
        if (!monthKey || monthKey === ALL_PERIODS_KEY) return;
        // Si les lignes sont déjà chargées, ne pas recharger
        if (monthlyData[monthKey]?.result?.lignes?.length > 0) return;

        try {
            const detail = await ApiService.getSageBfcMonthlyDetail(monthKey);
            setMonthlyData(prev => ({
                ...prev,
                [monthKey]: {
                    ...prev[monthKey],
                    result: {
                        periode: detail.periode,
                        resume: detail.resume,
                        lignes: detail.lignes,
                        validations: detail.validations,
                        alertes_globales: detail.alertes_globales
                    },
                    fileName: detail.file_name,
                    lignesCount: detail.lignes_count
                }
            }));
        } catch (err) {
            console.error(`Erreur chargement détail mois ${monthKey}:`, err);
        }
    }, [monthlyData]);

    // Charger tous les détails (pour lignes et dashboard complets)
    const loadAllMonthDetails = useCallback(async () => {
        const monthsToLoad = sortedMonths.filter(
            m => !monthlyData[m]?.result?.lignes?.length
        );
        if (monthsToLoad.length === 0) return;
        
        await Promise.all(monthsToLoad.map(async (monthKey) => {
            try {
                const detail = await ApiService.getSageBfcMonthlyDetail(monthKey);
                setMonthlyData(prev => ({
                    ...prev,
                    [monthKey]: {
                        ...prev[monthKey],
                        result: {
                            periode: detail.periode,
                            resume: detail.resume,
                            lignes: detail.lignes,
                            validations: detail.validations,
                            alertes_globales: detail.alertes_globales
                        },
                        fileName: detail.file_name,
                        lignesCount: detail.lignes_count
                    }
                }));
            } catch (err) {
                console.error(`Erreur chargement détail mois ${monthKey}:`, err);
            }
        }));
    }, [sortedMonths, monthlyData]);

    // Charger le détail quand on change de mois sélectionné
    useEffect(() => {
        if (selectedMonth) {
            loadMonthDetail(selectedMonth);
        }
    }, [selectedMonth, loadMonthDetail]);

    // Charger tous les détails quand on accède aux lignes (besoin de toutes les lignes)
    useEffect(() => {
        if (activeTab === 'lignes' && sortedMonths.length > 0) {
            loadAllMonthDetails();
        }
    }, [activeTab, sortedMonths.length, loadAllMonthDetails]);

    // Charger tous les détails quand on sélectionne la vue consolidée
    useEffect(() => {
        if (selectedMonth === ALL_PERIODS_KEY && sortedMonths.length > 0) {
            loadAllMonthDetails();
        }
    }, [selectedMonth, sortedMonths.length, loadAllMonthDetails]);

    // Charger les stats du mapping et les données mensuelles au montage
    useEffect(() => {
        const loadStats = async () => {
            try {
                const stats = await ApiService.getSageBfcMappingStats();
                setMappingStats(stats);
            } catch (err) {
                console.error('Erreur chargement stats mapping:', err);
            }
        };
        loadStats();
        loadMonthlyData();
    }, [loadMonthlyData]);

    // Rechargement temps réel déclenché par WebSocket
    useEffect(() => {
        if (refreshTrigger > 0) {
            loadMonthlyData();
        }
    }, [refreshTrigger, loadMonthlyData]);

    const handleFileParse = useCallback(async (file, periode) => {
        setLoading(true);
        setError(null);
        setFileName(file.name);

        try {
            const data = await ApiService.parseSageBfcFile(file, periode);
            const monthKey = data.periode;

            // Mettre à jour les données locales avec le résultat complet
            setMonthlyData(prev => ({
                ...prev,
                [monthKey]: {
                    result: data,
                    fileName: file.name,
                    lignesCount: data.lignes?.length || 0,
                    uploadDate: new Date().toISOString()
                }
            }));

            setSelectedMonth(monthKey);
            setActiveStep('results');
            setActiveTab('dashboard');
        } catch (err) {
            setError(err.message || 'Erreur lors du parsing du fichier');
        } finally {
            setLoading(false);
        }
    }, []);

    const handleNewUpload = useCallback(() => {
        setActiveStep('upload');
        setError(null);
        setFileName('');
    }, []);

    const handleViewResults = useCallback(() => {
        if (sortedMonths.length > 0) {
            setActiveStep('results');
            setActiveTab('dashboard');
        }
    }, [sortedMonths]);

    const handleDeleteMonth = useCallback(async (monthKey) => {
        try {
            await ApiService.deleteSageBfcMonth(monthKey);
            setMonthlyData(prev => {
                const newData = { ...prev };
                delete newData[monthKey];
                return newData;
            });
            if (selectedMonth === monthKey) {
                const remaining = sortedMonths.filter(m => m !== monthKey);
                setSelectedMonth(remaining.length > 0 ? remaining[remaining.length - 1] : null);
                if (remaining.length === 0) {
                    setActiveStep('upload');
                }
            }
        } catch (err) {
            setError('Erreur lors de la suppression: ' + err.message);
        }
    }, [selectedMonth, sortedMonths]);

    const handleClearAll = useCallback(async () => {
        if (window.confirm('Supprimer toutes les données mensuelles ?')) {
            try {
                await ApiService.deleteSageBfcAllMonths();
                setMonthlyData({});
                setSelectedMonth(null);
                setActiveStep('upload');
            } catch (err) {
                setError('Erreur lors de la suppression: ' + err.message);
            }
        }
    }, []);



    const formatMonthLabel = (periode) => {
        try {
            const d = new Date(periode);
            return d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
        } catch {
            return periode;
        }
    };

    const formatMonthShort = (periode) => {
        try {
            const d = new Date(periode);
            return d.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' });
        } catch {
            return periode;
        }
    };

    return (
        <div className="sage-bfc-container fade-in">
            {/* Header du module */}
            <div className="sage-bfc-header">
                <div>
                    <h2 className="sage-bfc-title">
                        <span className="sage-bfc-title-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                <polyline points="14,2 14,8 20,8"/>
                                <line x1="16" y1="13" x2="8" y2="13"/>
                                <line x1="16" y1="17" x2="8" y2="17"/>
                                <polyline points="10,9 9,9 8,9"/>
                            </svg>
                        </span>
                        SAGE → BFC
                    </h2>
                    <p className="sage-bfc-subtitle">
                        Transformation des balances SAGE au format Budget BFC
                    </p>
                </div>
                {sortedMonths.length > 0 && (
                    <div className="sage-bfc-stats-badge months-badge">
                        <span className="stats-badge-icon">📅</span>
                        <span>{sortedMonths.length} mois chargé{sortedMonths.length > 1 ? 's' : ''}</span>
                    </div>
                )}
            </div>

            {/* Navigation rapide */}
            <div className="sage-bfc-nav">
                <button
                    className={`sage-nav-btn ${activeStep === 'upload' ? 'active' : ''}`}
                    onClick={() => setActiveStep('upload')}
                >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                        <polyline points="17 8 12 3 7 8"/>
                        <line x1="12" y1="3" x2="12" y2="15"/>
                    </svg>
                    Import
                    {sortedMonths.length > 0 && <span className="nav-check">✓</span>}
                </button>
                <button
                    className={`sage-nav-btn ${activeStep === 'results' ? 'active' : ''}`}
                    onClick={handleViewResults}
                    disabled={sortedMonths.length === 0}
                >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="20" x2="18" y2="10"/>
                        <line x1="12" y1="20" x2="12" y2="4"/>
                        <line x1="6" y1="20" x2="6" y2="14"/>
                    </svg>
                    Analyse
                    {sortedMonths.length > 0 && <span className="nav-badge">{sortedMonths.length}</span>}
                </button>
            </div>

            {/* Erreur globale */}
            {error && (
                <div className="sage-bfc-error">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="15" y1="9" x2="9" y2="15"/>
                        <line x1="9" y1="9" x2="15" y2="15"/>
                    </svg>
                    <div>
                        <strong>Erreur</strong>
                        <p>{error}</p>
                    </div>
                    <button onClick={() => setError(null)} className="error-dismiss">✕</button>
                </div>
            )}

            {/* Étape 1: Upload */}
            {activeStep === 'upload' && (
                <div className="sage-upload-step">
                    <SageBfcUpload
                        onFileParse={handleFileParse}
                        loading={loading}
                        mappingStats={mappingStats}
                    />

                    {/* Historique des mois chargés */}
                    {sortedMonths.length > 0 && (
                        <div className="monthly-history-panel">
                            <div className="monthly-history-header">
                                <h4>📊 Mois déjà chargés</h4>
                                <button className="btn-view-results" onClick={handleViewResults}>
                                    Voir les résultats →
                                </button>
                            </div>
                            <div className="monthly-history-chips">
                                {sortedMonths.map(m => (
                                    <div key={m} className="month-chip" onClick={() => {
                                        setSelectedMonth(m);
                                        setActiveStep('results');
                                        setActiveTab('dashboard');
                                    }}>
                                        <span className="month-chip-label">{formatMonthShort(m)}</span>
                                        <span className="month-chip-lines">
                                            {monthlyData[m].result?.lignes?.length || 0} lignes
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Étape 2: Résultats */}
            {activeStep === 'results' && sortedMonths.length > 0 && (
                <div className="sage-bfc-results">
                    {/* Barre d'actions */}
                    <div className="sage-bfc-actions-bar">
                        <div className="actions-left">
                            {/* Sélecteur de mois amélioré */}
                            <div className="month-selector">
                                <svg className="month-selector-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                                    <line x1="16" y1="2" x2="16" y2="6"/>
                                    <line x1="8" y1="2" x2="8" y2="6"/>
                                    <line x1="3" y1="10" x2="21" y2="10"/>
                                </svg>
                                <select
                                    className="month-selector-select"
                                    value={selectedMonth || ''}
                                    onChange={(e) => setSelectedMonth(e.target.value)}
                                >
                                    <option value={ALL_PERIODS_KEY}> Toutes les périodes</option>
                                    {sortedMonths.map(m => (
                                        <option key={m} value={m}>{formatMonthLabel(m)}</option>
                                    ))}
                                </select>
                            </div>

                            {currentResult && selectedMonth !== ALL_PERIODS_KEY && (
                                <span className="file-name-badge">
                                    📄 {monthlyData[selectedMonth]?.fileName}
                                </span>
                            )}
                        </div>
                        <div className="actions-right">
                            {selectedMonth !== ALL_PERIODS_KEY && (
                                <button
                                    className="btn-delete-month"
                                    onClick={() => handleDeleteMonth(selectedMonth)}
                                    title="Supprimer ce mois"
                                >
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                        <polyline points="3,6 5,6 21,6"/>
                                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                                    </svg>
                                    Supprimer
                                </button>
                            )}
                        </div>
                    </div>

                    {/* Tabs de navigation */}
                    <div className="sage-bfc-tabs">
                        <button
                            className={`sage-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
                            onClick={() => setActiveTab('dashboard')}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="3" y="3" width="7" height="7"/>
                                <rect x="14" y="3" width="7" height="7"/>
                                <rect x="14" y="14" width="7" height="7"/>
                                <rect x="3" y="14" width="7" height="7"/>
                            </svg>
                            Vue d'ensemble
                        </button>
                        <button
                            className={`sage-tab ${activeTab === 'pnl' ? 'active' : ''}`}
                            onClick={() => setActiveTab('pnl')}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <line x1="18" y1="20" x2="18" y2="10"/>
                                <line x1="12" y1="20" x2="12" y2="4"/>
                                <line x1="6" y1="20" x2="6" y2="14"/>
                            </svg>
                            P&L Formaté
                        </button>
                        <button
                            className={`sage-tab ${activeTab === 'lignes' ? 'active' : ''}`}
                            onClick={() => setActiveTab('lignes')}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <line x1="8" y1="6" x2="21" y2="6"/>
                                <line x1="8" y1="12" x2="21" y2="12"/>
                                <line x1="8" y1="18" x2="21" y2="18"/>
                                <line x1="3" y1="6" x2="3.01" y2="6"/>
                                <line x1="3" y1="12" x2="3.01" y2="12"/>
                                <line x1="3" y1="18" x2="3.01" y2="18"/>
                            </svg>
                            Lignes Mappées
                            <span className="tab-count">{allLignes.length}</span>
                        </button>
                        <button
                            className={`sage-tab ${activeTab === 'validations' ? 'active' : ''}`}
                            onClick={() => setActiveTab('validations')}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                                <polyline points="22,4 12,14.01 9,11.01"/>
                            </svg>
                            Validations
                            {currentResult && currentResult.validations.length > 0 && (
                                <span className={`tab-count ${currentResult.validations.some(v => v.statut === 'ALERTE') ? 'alert' : 'ok'}`}>
                                    {currentResult.validations.length}
                                </span>
                            )}
                        </button>
                    </div>

                    {/* Contenu des tabs */}
                    <div className="sage-bfc-tab-content">
                        {activeTab === 'dashboard' && (
                            <SageBfcDashboard
                                monthlyData={monthlyData}
                                sortedMonths={sortedMonths}
                                formatMonthLabel={formatMonthLabel}
                                formatMonthShort={formatMonthShort}
                                currentResume={currentResult?.resume}
                                previousResume={previousResult?.resume}
                                selectedMonth={selectedMonth}
                            />
                        )}
                        {activeTab === 'pnl' && currentResult && (
                            <SageBfcPnl
                                resume={currentResult.resume}
                                previousResume={previousResult?.resume}
                            />
                        )}
                        {activeTab === 'lignes' && (
                            <SageBfcLignes
                                lignes={allLignes}
                                sortedMonths={sortedMonths}
                                formatMonthShort={formatMonthShort}
                            />
                        )}
                        {activeTab === 'validations' && currentResult && (
                            <SageBfcValidations
                                validations={currentResult.validations}
                                alertes={currentResult.alertes_globales}
                            />
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default SageBfcParser;
