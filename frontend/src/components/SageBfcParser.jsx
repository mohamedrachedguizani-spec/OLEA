// src/components/SageBfcParser.js
import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import ReactDOM from 'react-dom';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import SageBfcUpload from './sage-bfc/SageBfcUpload';
import SageBfcPnl from './sage-bfc/SageBfcPnl';
import SageBfcLignes from './sage-bfc/SageBfcLignes';
import SageBfcDashboard from './sage-bfc/SageBfcDashboard';
import SageBfcForecast from './sage-bfc/SageBfcForecast';
import SageBfcMappingAlert from './sage-bfc/SageBfcMappingAlert';
import SageBfcSuccessModal from './sage-bfc/SageBfcSuccessModal';
import './sage-bfc/SageBfcParser.css';

const ALL_PERIODS_KEY = '__all_periods__';

export const getPeriodYear = (periode) => {
    const match = String(periode || '').match(/^(\d{4})/);
    return match ? match[1] : '';
};

export const getPeriodMonth = (periode) => {
    const match = String(periode || '').match(/^\d{4}-(\d{2})/);
    return match ? match[1] : '';
};

export const getPeriodsForYear = (periods, year) => (
    periods.filter((periode) => getPeriodYear(periode) === String(year))
);

export const choosePeriodForYear = (periods, year, preferredPeriod = null) => {
    const yearPeriods = getPeriodsForYear(periods, year);
    if (!yearPeriods.length) return null;
    if (preferredPeriod === ALL_PERIODS_KEY) return ALL_PERIODS_KEY;
    const preferredMonth = getPeriodMonth(preferredPeriod);
    if (preferredMonth) {
        const sameMonth = yearPeriods.find((periode) => getPeriodMonth(periode) === preferredMonth);
        if (sameMonth) return sameMonth;
    }
    return yearPeriods[yearPeriods.length - 1];
};

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
    'brand_fees',
    'management_fees',
    'interco_charges',
    'total_charges',
    'ebitda',
    'produits_financiers',
    'charges_financieres',
    'resultat_financier',
    'produits_exceptionnels',
    'charges_exceptionnelles',
    'resultat_exceptionnel',
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

    sortedMonths.forEach((monthKey) => {
        const monthResult = monthlyData[monthKey]?.result;
        const monthResume = monthResult?.resume || {};

        RESUME_SUM_KEYS.forEach((key) => {
            resume[key] += Number(monthResume[key] || 0);
        });

        (monthResult?.lignes || []).forEach((l) => {
            lignes.push({ ...l, mois: monthKey });
        });
    });

    resume.ebitda_pct = resume.ca_net ? (resume.ebitda / resume.ca_net) * 100 : 0;
    resume.resultat_net_pct = resume.ca_net ? (resume.resultat_net / resume.ca_net) * 100 : 0;

    return {
        periode: ALL_PERIODS_KEY,
        resume,
        lignes
    };
}

function SageBfcParser({
    refreshTrigger,
    forecastRefresh = 0,
    onOpenMappingConfiguration,
    navigationTarget,
    onNavigationConsumed,
}) {
    const { has } = useAuth();
    const currentYear = new Date().getFullYear();
    const [activeStep, setActiveStep] = useState('upload'); // upload | results
    const [activeTab, setActiveTab] = useState('dashboard'); // dashboard | pnl | lignes | forecast
    const [loading, setLoading] = useState(false);
    const [loadingData, setLoadingData] = useState(true);
    const [error, setError] = useState(null);
    const [mappingAlert, setMappingAlert] = useState(null);
    const [importSuccess, setImportSuccess] = useState(null);
    const [successMessage, setSuccessMessage] = useState(null);
    const [mappingStats, setMappingStats] = useState(null);
    const [fileName, setFileName] = useState('');
    const [closingYear, setClosingYear] = useState(false);
    const [closedYears, setClosedYears] = useState([]);

    // Données mensuelles chargées depuis le backend
    const [monthlyData, setMonthlyData] = useState({});
    const [availableYears, setAvailableYears] = useState([]);
    const [yearMonthCounts, setYearMonthCounts] = useState({});
    const [yearsLoaded, setYearsLoaded] = useState(false);
    const [selectedMonth, setSelectedMonth] = useState(null);
    const [selectedYearFilter, setSelectedYearFilter] = useState('');
    const handledNavigationRef = useRef(null);
    const monthlyRequestRef = useRef(0);
    const initialNavigationTargetRef = useRef(navigationTarget);

    // Mois triés chronologiquement
    const sortedMonths = useMemo(() => {
        return Object.keys(monthlyData).sort();
    }, [monthlyData]);

    const filteredMonths = useMemo(() => {
        if (!selectedYearFilter) return [];
        return getPeriodsForYear(sortedMonths, selectedYearFilter);
    }, [sortedMonths, selectedYearFilter]);

    const loadMonthlyYears = useCallback(async () => {
        try {
            const response = await ApiService.getSageBfcMonthlyYears();
            const years = Array.isArray(response?.years)
                ? response.years.map(Number).filter(Number.isFinite)
                : [];
            setAvailableYears(years);
            setYearMonthCounts(Object.fromEntries(
                (response?.items || []).map((item) => [Number(item.year), Number(item.months_count || 0)])
            ));
            return years;
        } finally {
            setYearsLoaded(true);
        }
    }, []);

    const loadMonthlyData = useCallback(async (
        { year = null, periode = null } = {},
        { commit = true } = {},
    ) => {
        const requestId = commit ? ++monthlyRequestRef.current : null;
        try {
            if (commit) setLoadingData(true);
            const months = await ApiService.getSageBfcMonthlyList({ year, periode });
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
            if (commit && requestId === monthlyRequestRef.current) setMonthlyData(data);
            return data;
        } catch (err) {
            if (commit && requestId === monthlyRequestRef.current) {
                setError(err.message || 'Erreur lors du chargement des balances');
            }
            return {};
        } finally {
            if (commit && requestId === monthlyRequestRef.current) setLoadingData(false);
        }
    }, []);

    useEffect(() => {
        if (!navigationTarget || handledNavigationRef.current === navigationTarget.key) return;
        const { periode, year, section, view } = navigationTarget.params || {};
        if ((periode || year) && !yearsLoaded) return;

        let cancelled = false;
        const applyTarget = async () => {
            const targetYear = getPeriodYear(periode) || String(year || '');
            let targetData = {};
            if (targetYear && availableYears.includes(Number(targetYear))) {
                if (periode) {
                    const exactMatch = await loadMonthlyData({ periode }, { commit: false });
                    if (!Object.prototype.hasOwnProperty.call(exactMatch, periode)) {
                        setError(`La période ${periode} n'est plus disponible.`);
                        handledNavigationRef.current = navigationTarget.key;
                        onNavigationConsumed?.(navigationTarget.key);
                        return;
                    }
                }
                targetData = await loadMonthlyData({ year: targetYear });
                if (cancelled) return;
                setSelectedYearFilter(targetYear);
            }
            if (periode && Object.prototype.hasOwnProperty.call(targetData, periode)) {
                setSelectedMonth(periode);
            }
            if (section === 'upload') {
                setActiveStep('upload');
            } else {
                setActiveStep('results');
                setActiveTab(view === 'forecast' ? 'forecast' : (section || 'dashboard'));
            }
            handledNavigationRef.current = navigationTarget.key;
            onNavigationConsumed?.(navigationTarget.key);
        };
        applyTarget();
        return () => { cancelled = true; };
    }, [navigationTarget, yearsLoaded, availableYears, loadMonthlyData, onNavigationConsumed]);

    // Garantir que l'année sélectionnée existe encore dans les données.
    useEffect(() => {
        if (!availableYears.length) {
            if (selectedYearFilter) setSelectedYearFilter('');
            if (selectedMonth) setSelectedMonth(null);
            return;
        }

        if (!selectedYearFilter || !availableYears.includes(Number(selectedYearFilter))) {
            setSelectedYearFilter(String(availableYears[0]));
        }
    }, [availableYears, selectedYearFilter, selectedMonth]);

    useEffect(() => {
        if (!filteredMonths.length) {
            setSelectedMonth(null);
            return;
        }
        if (!selectedMonth || (selectedMonth !== ALL_PERIODS_KEY && !filteredMonths.includes(selectedMonth))) {
            setSelectedMonth(filteredMonths[filteredMonths.length - 1]);
        }
    }, [filteredMonths, selectedMonth]);

    const handleYearFilterChange = useCallback(async (nextYear) => {
        const preferredPeriod = selectedMonth;
        setSelectedYearFilter(nextYear);
        const data = await loadMonthlyData({ year: nextYear });
        const periods = Object.keys(data).sort();
        setSelectedMonth(choosePeriodForYear(periods, nextYear, preferredPeriod));
    }, [loadMonthlyData, selectedMonth]);

    // Résultat du mois sélectionné
    const currentResult = useMemo(() => {
        if (!selectedMonth) return null;
        if (selectedMonth === ALL_PERIODS_KEY) {
            return buildAllPeriodsResult(filteredMonths, monthlyData);
        }
        if (!monthlyData[selectedMonth]) return null;
        return monthlyData[selectedMonth].result;
    }, [selectedMonth, monthlyData, filteredMonths]);

    // Résultat du mois précédent (pour comparaison)
    const previousResult = useMemo(() => {
        if (!selectedMonth || selectedMonth === ALL_PERIODS_KEY) return null;
        const idx = filteredMonths.indexOf(selectedMonth);
        if (idx <= 0) return null;
        return monthlyData[filteredMonths[idx - 1]]?.result || null;
    }, [selectedMonth, filteredMonths, monthlyData]);

    // Toutes les lignes accumulées de tous les mois
    const allLignes = useMemo(() => {
        return filteredMonths.flatMap((periode) =>
            (monthlyData[periode]?.result?.lignes || []).map((l) => ({ ...l, mois: periode }))
        );
    }, [filteredMonths, monthlyData]);

    const loadClosedYears = useCallback(async () => {
        try {
            const res = await ApiService.getSageBfcClosedYears();
            setClosedYears(Array.isArray(res?.years) ? res.years.map((y) => Number(y)).filter((y) => Number.isFinite(y)) : []);
        } catch (err) {
            // Pas de log console
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
            // Pas de log console
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
                // Pas de log console
            }
        }));
    }, [sortedMonths, monthlyData]);

    // Charger le détail quand on change de mois sélectionné
    useEffect(() => {
        if (selectedMonth) {
            loadMonthDetail(selectedMonth);
        }
    }, [selectedMonth, loadMonthDetail]);

    // Charger tous les détails quand on accède aux lignes ou au P&L (besoin des lignes pour le détail)
    useEffect(() => {
        if ((activeTab === 'lignes' || activeTab === 'pnl') && sortedMonths.length > 0) {
            if (activeTab === 'lignes') {
                loadAllMonthDetails();
            } else if (activeTab === 'pnl' && selectedMonth && selectedMonth !== ALL_PERIODS_KEY) {
                loadMonthDetail(selectedMonth);
            } else if (activeTab === 'pnl' && selectedMonth === ALL_PERIODS_KEY) {
                loadAllMonthDetails();
            }
        }
    }, [activeTab, sortedMonths.length, selectedMonth, loadAllMonthDetails, loadMonthDetail]);

    // Charger tous les détails quand on sélectionne la vue consolidée
    useEffect(() => {
        if (selectedMonth === ALL_PERIODS_KEY && sortedMonths.length > 0) {
            loadAllMonthDetails();
        }
    }, [selectedMonth, sortedMonths.length, loadAllMonthDetails]);

    // Charger les stats, les années et uniquement la dernière année au montage.
    useEffect(() => {
        const loadStats = async () => {
            try {
                const stats = await ApiService.getSageBfcMappingStats();
                setMappingStats(stats);
            } catch (err) {
                // Pas de log console
            }
        };
        loadStats();
        loadClosedYears();
        const initializeMonthlyData = async () => {
            try {
                const years = await loadMonthlyYears();
                const initialTarget = initialNavigationTargetRef.current;
                const requestedYear = getPeriodYear(initialTarget?.params?.periode)
                    || String(initialTarget?.params?.year || '');
                const initialYear = years.includes(Number(requestedYear))
                    ? Number(requestedYear)
                    : years[0];
                if (initialYear) {
                    setSelectedYearFilter(String(initialYear));
                    await loadMonthlyData({ year: initialYear });
                } else {
                    setMonthlyData({});
                    setLoadingData(false);
                }
            } catch (err) {
                setError(err.message || 'Erreur lors du chargement des années disponibles');
                setLoadingData(false);
            }
        };
        initializeMonthlyData();
    }, [loadMonthlyData, loadMonthlyYears, loadClosedYears]);

    // Rechargement temps réel déclenché par WebSocket
    const handledRefreshRef = useRef(0);
    useEffect(() => {
        if (refreshTrigger <= 0 || handledRefreshRef.current === refreshTrigger) return;
        handledRefreshRef.current = refreshTrigger;
        const refresh = async () => {
            const years = await loadMonthlyYears();
            const activeYear = years.includes(Number(selectedYearFilter))
                ? selectedYearFilter
                : String(years[0] || '');
            if (activeYear) {
                setSelectedYearFilter(activeYear);
                await loadMonthlyData({ year: activeYear });
            } else {
                setMonthlyData({});
            }
            await loadClosedYears();
        };
        refresh().catch((err) => setError(err.message || 'Erreur lors de l\'actualisation des balances'));
    }, [refreshTrigger, selectedYearFilter, loadMonthlyData, loadMonthlyYears, loadClosedYears]);

    const handleFileParse = useCallback(async (file, periode) => {
        setLoading(true);
        setError(null);
        setMappingAlert(null);
        setImportSuccess(null);
        setSuccessMessage(null);
        setFileName(file.name);

        try {
            const data = await ApiService.parseSageBfcFile(file, periode);
            const monthKey = data.periode;
            const importedYear = getPeriodYear(monthKey);

            // Recharger uniquement l'exercice importé, puis conserver le résultat complet reçu.
            const yearData = await loadMonthlyData({ year: importedYear });

            setMonthlyData({
                ...yearData,
                [monthKey]: {
                    result: data,
                    fileName: file.name,
                    lignesCount: data.lignes?.length || 0,
                    uploadDate: new Date().toISOString()
                }
            });

            if (importedYear) setSelectedYearFilter(importedYear);
            setSelectedMonth(monthKey);
            await loadMonthlyYears();
            setActiveStep('results');
            setActiveTab('dashboard');
            const lignes = Array.isArray(data.lignes) ? data.lignes : [];
            setImportSuccess({
                periode: data.periode,
                fileName: file.name,
                linesCount: lignes.length,
                mappedAccounts: new Set(lignes.map((line) => line.code_sage).filter(Boolean)).size,
            });
        } catch (err) {
            if (err.code === 'SAGE_BFC_MAPPING_MISSING' && err.mappingDetails) {
                setMappingAlert(err.mappingDetails);
            } else {
                setError(err.message || 'Erreur lors du parsing du fichier');
            }
        } finally {
            setLoading(false);
        }
    }, []);

    const handleNewUpload = useCallback(() => {
        setActiveStep('upload');
        setError(null);
        setMappingAlert(null);
        setImportSuccess(null);
        setSuccessMessage(null);
        setFileName('');
    }, [loadMonthlyData, loadMonthlyYears]);

    const dismissImportSuccess = useCallback(() => {
        setImportSuccess(null);
    }, []);

    const handleSuccessViewResults = useCallback(() => {
        const importedPeriod = importSuccess?.periode;
        const importedYear = getPeriodYear(importedPeriod);
        if (importedYear) setSelectedYearFilter(importedYear);
        if (importedPeriod) setSelectedMonth(importedPeriod);
        setImportSuccess(null);
        setActiveStep('results');
        setActiveTab('dashboard');
    }, [importSuccess]);

    const handleSuccessNewUpload = useCallback(() => {
        setImportSuccess(null);
        handleNewUpload();
    }, [handleNewUpload]);

    const handleViewResults = useCallback(async () => {
        if (selectedYearFilter && sortedMonths.length === 0) {
            await loadMonthlyData({ year: selectedYearFilter });
        }
        setActiveStep('results');
        setActiveTab('dashboard');
    }, [selectedYearFilter, sortedMonths.length, loadMonthlyData]);

    const handleDeleteMonth = useCallback(async (monthKey) => {
        try {
            await ApiService.deleteSageBfcMonth(monthKey);
            const remaining = sortedMonths.filter(m => m !== monthKey);
            setMonthlyData((prev) => {
                const nextData = { ...prev };
                delete nextData[monthKey];
                return nextData;
            });
            const years = await loadMonthlyYears();
            if (selectedMonth === monthKey) {
                const sameYearPeriods = getPeriodsForYear(remaining, selectedYearFilter);
                if (sameYearPeriods.length > 0) {
                    setSelectedMonth(sameYearPeriods[sameYearPeriods.length - 1]);
                } else if (years.length > 0) {
                    const nextYear = String(years[0]);
                    const nextData = await loadMonthlyData({ year: nextYear });
                    const nextPeriods = Object.keys(nextData).sort();
                    setSelectedYearFilter(nextYear);
                    setSelectedMonth(choosePeriodForYear(nextPeriods, nextYear));
                } else {
                    setSelectedYearFilter('');
                    setSelectedMonth(null);
                    setMonthlyData({});
                }
                if (years.length === 0) {
                    setActiveStep('upload');
                }
            }
        } catch (err) {
            setError('Erreur lors de la suppression: ' + err.message);
        }
    }, [selectedMonth, selectedYearFilter, sortedMonths, loadMonthlyData, loadMonthlyYears]);

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

    const showTopFilters = activeTab !== 'lignes' && activeTab !== 'forecast';

    const monthsByYear = useMemo(() => {
        const acc = {};
        sortedMonths.forEach((m) => {
            const y = Number(getPeriodYear(m));
            const mo = Number(getPeriodMonth(m));
            if (!Number.isFinite(y) || !Number.isFinite(mo)) return;
            if (!acc[y]) acc[y] = new Set();
            acc[y].add(mo);
        });
        return acc;
    }, [sortedMonths]);

    const closableYear = useMemo(() => {
        if (!selectedMonth || selectedMonth === ALL_PERIODS_KEY) return null;
        const year = Number(getPeriodYear(selectedMonth));
        const month = Number(getPeriodMonth(selectedMonth));
        if (!Number.isFinite(year) || !Number.isFinite(month)) return null;
        if (month !== 12) return null;
        const count = monthsByYear[year] ? monthsByYear[year].size : 0;
        return count === 12 ? year : null;
    }, [selectedMonth, monthsByYear]);

    const latestClosableYear = useMemo(() => {
        const years = Object.keys(yearMonthCounts)
            .map(Number)
            .filter((y) => Number.isFinite(y) && yearMonthCounts[y] === 12)
            .filter((y) => !closedYears.includes(y))
            .sort((a, b) => b - a);
        return years.length ? years[0] : null;
    }, [yearMonthCounts, closedYears]);

    const handleCloseYear = useCallback(async (yearToClose = null) => {
        const targetYear = yearToClose ?? closableYear;
        if (!targetYear) return;
        const ok = window.confirm(
            `Clôturer l'année ${targetYear} ?\n\nCela va archiver l'année, synchroniser l'historique et générer le budget initial ${targetYear + 1}.`
        );
        if (!ok) return;

        try {
            setClosingYear(true);
            setError(null);
            setSuccessMessage(null);
            const res = await ApiService.closeSageBfcYear(targetYear);

            // Réinitialisation complète du module côté UI
            setMonthlyData({});
            setSelectedMonth(null);
            setSelectedYearFilter(String(res?.next_year || new Date().getFullYear()));
            setFileName('');
            setActiveTab('dashboard');
            setActiveStep('upload');

            const years = await loadMonthlyYears();
            const nextYear = years.includes(Number(res?.next_year))
                ? String(res.next_year)
                : String(years[0] || '');
            if (nextYear) {
                setSelectedYearFilter(nextYear);
                await loadMonthlyData({ year: nextYear });
            } else {
                setMonthlyData({});
            }
            await loadClosedYears();
            setSuccessMessage(`Année ${res.closed_year} clôturée avec succès. Le module a été réinitialisé pour ${res.next_year}.`);
        } catch (err) {
            setError(err.message || 'Erreur lors de la clôture annuelle');
        } finally {
            setClosingYear(false);
        }
    }, [closableYear, loadMonthlyData, loadMonthlyYears, loadClosedYears]);

    return (
        <div className="sage-bfc-container fade-in">
            {importSuccess && (
                <SageBfcSuccessModal
                    details={importSuccess}
                    onDismiss={dismissImportSuccess}
                    onViewResults={handleSuccessViewResults}
                    onNewUpload={handleSuccessNewUpload}
                />
            )}
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

                {/* Navigation rapide (placée en haut à droite) */}
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
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="20" x2="18" y2="10"/>
                            <line x1="12" y1="20" x2="12" y2="4"/>
                            <line x1="6" y1="20" x2="6" y2="14"/>
                        </svg>
                        Analyse
                        {sortedMonths.length > 0 && <span className="nav-badge">{sortedMonths.length}</span>}
                    </button>
                    {!!latestClosableYear && has('sage_bfc.year.close') && (
                        <button
                            className="sage-nav-btn"
                            onClick={() => handleCloseYear(latestClosableYear)}
                            disabled={closingYear}
                            title={`Clôturer ${latestClosableYear}`}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M20 6L9 17l-5-5"/>
                            </svg>
                            {closingYear ? 'Clôture...' : `Clôturer ${latestClosableYear}`}
                        </button>
                    )}
                </div>
            </div>

            {closingYear && ReactDOM.createPortal(
                <div className="sage-close-overlay" role="status" aria-live="polite" aria-label="Clôture annuelle en cours">
                    <div className="sage-close-overlay-card">
                        <div className="sage-close-spinner" />
                        <h4>Clôture annuelle en cours...</h4>
                        <p>Archivage, synchronisation historique et génération du budget initial.</p>
                    </div>
                </div>,
                document.body
            )}

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

            {successMessage && (
                <div className="sage-bfc-success">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M20 6L9 17l-5-5"/>
                    </svg>
                    <div>
                        <strong>Succès</strong>
                        <p>{successMessage}</p>
                    </div>
                    <button onClick={() => setSuccessMessage(null)} className="success-dismiss">✕</button>
                </div>
            )}

            {!!latestClosableYear && has('sage_bfc.year.close') && (
                <div className="sage-close-ready-notice" role="status" aria-live="polite">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M20 6L9 17l-5-5"/>
                    </svg>
                    <span>
                        La balance de décembre est disponible. Vous pouvez maintenant clôturer l’année <strong>{latestClosableYear}</strong> via le bouton <strong>Clôturer {latestClosableYear}</strong>.
                    </span>
                </div>
            )}

            {/* Étape 1: Upload */}
            {activeStep === 'upload' && (
                <div className="sage-upload-step">
                    {mappingAlert && (
                        <SageBfcMappingAlert
                            details={mappingAlert}
                            onDismiss={() => setMappingAlert(null)}
                            onOpenConfiguration={onOpenMappingConfiguration}
                        />
                    )}
                    {has('sage_bfc.import') ? (
                        <SageBfcUpload
                            onFileParse={handleFileParse}
                            loading={loading}
                            mappingStats={mappingStats}
                        />
                    ) : (
                        <div className="sage-bfc-error"><div><strong>Consultation uniquement</strong><p>Vous n'avez pas l'autorisation d'importer une balance.</p></div></div>
                    )}
                </div>
            )}

            {/* Étape 2: Résultats */}
            {activeStep === 'results' && (
                <div className="sage-bfc-results">
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
                        {/* <button
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
                        </button> */}
                        <button
                            className={`sage-tab ${activeTab === 'forecast' ? 'active' : ''}`}
                            onClick={() => setActiveTab('forecast')}
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <line x1="4" y1="19" x2="20" y2="19"/>
                                <line x1="4" y1="15" x2="8" y2="11"/>
                                <line x1="8" y1="11" x2="13" y2="14"/>
                                <line x1="13" y1="14" x2="20" y2="6"/>
                            </svg>
                            Prévision Budget
                        </button>
                    </div>

                    {/* Barre d'actions (Vue d'ensemble / P&L) */}
                    {showTopFilters && (
                        <div className="sage-bfc-actions-bar">
                            <div className="actions-left">
                                <div className="filter-block">
                                    <span className="filter-block-label">Année</span>
                                    <div className="month-selector">
                                        <svg className="month-selector-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M3 5h18"/>
                                            <path d="M3 12h18"/>
                                            <path d="M3 19h18"/>
                                        </svg>
                                        <select
                                            className="month-selector-select"
                                            value={selectedYearFilter}
                                            onChange={(e) => handleYearFilterChange(e.target.value)}
                                        >
                                            {availableYears.map((y) => (
                                                <option key={y} value={String(y)}>{y}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                <div className="filter-block">
                                    <span className="filter-block-label">Période</span>
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
                                            {!filteredMonths.length && <option value="">Aucune période chargée</option>}
                                            <option value={ALL_PERIODS_KEY}> Toutes les périodes</option>
                                            {filteredMonths.map(m => (
                                                <option key={m} value={m}>{formatMonthLabel(m)}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                {currentResult && selectedMonth !== ALL_PERIODS_KEY && (
                                    <span className="file-name-badge">
                                        📄 {monthlyData[selectedMonth]?.fileName}
                                    </span>
                                )}
                            </div>
                            <div className="actions-right">
                                {!!selectedMonth && selectedMonth !== ALL_PERIODS_KEY && has('sage_bfc.month.delete') && (
                                    <button
                                        className="btn-delete-month danger-soft"
                                        onClick={() => handleDeleteMonth(selectedMonth)}
                                        title="Supprimer la période sélectionnée"
                                    >
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <polyline points="3,6 5,6 21,6"/>
                                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                                        </svg>
                                        Supprimer la période
                                    </button>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Contenu des tabs */}
                    <div className="sage-bfc-tab-content">
                        {sortedMonths.length === 0 && (
                            <div className="sage-bfc-error">
                                <div>
                                    <strong>Aucun upload détecté</strong>
                                </div>
                            </div>
                        )}
                        {activeTab === 'dashboard' && (
                            <SageBfcDashboard
                                monthlyData={monthlyData}
                                sortedMonths={filteredMonths}
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
                                lignes={currentResult.lignes || []}
                            />
                        )}
                        {activeTab === 'lignes' && (
                            <SageBfcLignes
                                lignes={allLignes}
                                sortedMonths={sortedMonths}
                                formatMonthShort={formatMonthShort}
                            />
                        )}
                        {activeTab === 'forecast' && (
                            <SageBfcForecast
                                selectedMonth={selectedMonth}
                                refreshTrigger={forecastRefresh + refreshTrigger}
                                navigationTarget={navigationTarget?.params?.view === 'forecast' ? navigationTarget : null}
                            />
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

export default SageBfcParser;
