import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ApiService from '../services/api';
import '../styles/Reporting.css';

const CYCLE_OPTIONS = ['INITIAL', 'M03', 'M06', 'M08'];

function Reporting({ refreshTrigger = 0 }) {
    const now = new Date();
    const [targetYear, setTargetYear] = useState(now.getFullYear());
    const [budgetCycleCode, setBudgetCycleCode] = useState('INITIAL');

    const [loading, setLoading] = useState(false);
    const [exportLoading, setExportLoading] = useState(false);
    const [error, setError] = useState('');
    const [preview, setPreview] = useState(null);

    const [exportConfig, setExportConfig] = useState({
        includePnlSelected: true,
        includePnlGlobal: false,
        pnlMonths: [],
        monthlyDetailMonths: [],
        includeExecutiveSummary: true,
        includePnlFormatted: true,
        includeBudgetForecast: true,
        includeGlobalState: true,
        includeMonthlyForecast: false,
        includeCycles: true,
        includeAlerts: false,
        includeSubaggregates: true,
    });

    const fmt = (v, digits = 3) => {
        if (v == null || Number.isNaN(Number(v))) return '—';
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(Number(v));
    };

    const loadPreview = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const data = await ApiService.getReportingPreview(targetYear, 'INITIAL', null);
            setPreview(data);
        } catch (e) {
            setError(e.message || 'Erreur chargement preview reporting');
        } finally {
            setLoading(false);
        }
    }, [targetYear]);

    useEffect(() => {
        loadPreview();
    }, [loadPreview]);

    useEffect(() => {
        if (!refreshTrigger) return;
        loadPreview();
    }, [refreshTrigger, loadPreview]);

    const handleExport = async () => {
        setExportLoading(true);
        setError('');
        try {
            await ApiService.exportReportingExcel(targetYear, 'INITIAL', null, {
                ...exportConfig,
                budgetCycleCode,
            });
        } catch (e) {
            setError(e.message || 'Erreur export reporting');
        } finally {
            setExportLoading(false);
        }
    };

    const availableMonths = useMemo(() => preview?.available_months || [], [preview]);

    useEffect(() => {
        if (!availableMonths.length) return;
        setExportConfig((prev) => {
            const patch = {};
            if (!prev.monthlyDetailMonths.length) {
                patch.monthlyDetailMonths = [availableMonths[availableMonths.length - 1]];
            }
            if (!prev.pnlMonths.length) {
                patch.pnlMonths = [availableMonths[availableMonths.length - 1]];
            }
            return Object.keys(patch).length ? { ...prev, ...patch } : prev;
        });
    }, [availableMonths]);

    const toggleConfigBool = (key) => {
        setExportConfig((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    const toggleMonthlyDetailMonth = (m) => {
        setExportConfig((prev) => {
            const exists = prev.monthlyDetailMonths.includes(m);
            const next = exists ? prev.monthlyDetailMonths.filter((x) => x !== m) : [...prev.monthlyDetailMonths, m].sort((a, b) => a - b);
            return { ...prev, monthlyDetailMonths: next };
        });
    };

    const togglePnlMonth = (m) => {
        setExportConfig((prev) => {
            const exists = prev.pnlMonths.includes(m);
            const next = exists ? prev.pnlMonths.filter((x) => x !== m) : [...prev.pnlMonths, m].sort((a, b) => a - b);
            return { ...prev, pnlMonths: next };
        });
    };

    const hasAnySection = useMemo(() => (
        exportConfig.includeExecutiveSummary ||
        exportConfig.includePnlFormatted ||
        exportConfig.includeBudgetForecast ||
        exportConfig.includeGlobalState ||
        exportConfig.includeCycles
    ), [exportConfig]);

    const selectedMonthlyDetailText = useMemo(() => {
        if (!exportConfig.monthlyDetailMonths.length) return 'Aucun mois';
        return exportConfig.monthlyDetailMonths.map((m) => `M${String(m).padStart(2, '0')}`).join(', ');
    }, [exportConfig]);

    const hasValidMonthlyDetailSelection = useMemo(() => {
        if (loading || !availableMonths.length) return true;
        if (!exportConfig.includeBudgetForecast || !exportConfig.includeMonthlyForecast) return true;
        return exportConfig.monthlyDetailMonths.length > 0;
    }, [exportConfig, loading, availableMonths]);

    const hasValidPnlSelection = useMemo(() => {
        if (loading || !availableMonths.length) return true;
        if (!exportConfig.includePnlFormatted) return true;
        if (!exportConfig.includePnlSelected && !exportConfig.includePnlGlobal) return false;
        if (!exportConfig.includePnlSelected) return true;
        return exportConfig.pnlMonths.length > 0;
    }, [exportConfig, loading, availableMonths]);

    const pnlMonthsText = useMemo(() => {
        const parts = [];
        if (exportConfig.includePnlSelected) {
            const selected = exportConfig.pnlMonths.length
                ? exportConfig.pnlMonths.map((m) => `M${String(m).padStart(2, '0')}`).join(', ')
                : 'Aucun mois';
            parts.push(`Sélection: ${selected}`);
        }
        if (exportConfig.includePnlGlobal) {
            parts.push('Global: Tous les mois réalisés');
        }
        return parts.length ? parts.join(' · ') : 'Aucun mode';
    }, [exportConfig]);

    return (
        <div className="reporting-container fade-in">
            <div className="reporting-header">
                <div className="reporting-title-wrap">
                    <div className="reporting-title-icon">📊</div>
                    <div>
                        <h2 className="reporting-title">Reporting Décisionnel</h2>
                        <p className="reporting-subtitle">Configuration d'export claire et rapide</p>
                    </div>
                </div>
            </div>

            <div className="reporting-toolbar">
                <label>
                    <span>Année</span>
                    <input type="number" min="2000" max="2100" value={targetYear} onChange={(e) => setTargetYear(Number(e.target.value || now.getFullYear()))} />
                </label>
                <div className="reporting-actions">
                    <button className="btn-reporting" onClick={loadPreview} disabled={loading}>{loading ? 'Chargement...' : 'Actualiser'}</button>
                    <button className="btn-reporting primary" onClick={handleExport} disabled={exportLoading || !hasAnySection || !hasValidMonthlyDetailSelection || !hasValidPnlSelection}>{exportLoading ? 'Export...' : '⬇ Export Excel'}</button>
                </div>
            </div>

            <div className="reporting-config-panel">
                <h3>Panneau de configuration d'export</h3>

                <div className="reporting-config-grid">
                    <div className="reporting-config-card">
                        <h4>Contenu du reporting</h4>
                        <label><input type="checkbox" checked={exportConfig.includeExecutiveSummary} onChange={() => toggleConfigBool('includeExecutiveSummary')} /> Executive summary KPI</label>
                        <label><input type="checkbox" checked={exportConfig.includePnlFormatted} onChange={() => toggleConfigBool('includePnlFormatted')} /> P&L formaté</label>
                        <label><input type="checkbox" checked={exportConfig.includeBudgetForecast} onChange={() => toggleConfigBool('includeBudgetForecast')} /> Prévision budget (tableaux)</label>
                        <label><input type="checkbox" checked={exportConfig.includeGlobalState} onChange={() => toggleConfigBool('includeGlobalState')} /> Etat globale </label>
                        <label><input type="checkbox" checked={exportConfig.includeCycles} onChange={() => toggleConfigBool('includeCycles')} /> Statut des cycles</label>
                    </div>

                    <div className="reporting-config-card">
                        <h4>P&L formaté</h4>
                        <label><input type="checkbox" checked={exportConfig.includePnlSelected} onChange={() => toggleConfigBool('includePnlSelected')} /> Mois sélectionnés</label>
                        <label><input type="checkbox" checked={exportConfig.includePnlGlobal} onChange={() => toggleConfigBool('includePnlGlobal')} /> Tous les mois (global)</label>
                        <div className="reporting-month-picker">
                            {(availableMonths || []).map((m) => (
                                <button
                                    type="button"
                                    key={`pnl-${m}`}
                                    className={`reporting-month-chip ${exportConfig.pnlMonths.includes(m) ? 'active' : ''}`}
                                    onClick={() => togglePnlMonth(m)}
                                    disabled={!exportConfig.includePnlSelected}
                                >
                                    M{String(m).padStart(2, '0')}
                                </button>
                            ))}
                        </div>
                        {/* <div className="reporting-hint">
                            Inclut prévision + réalisé des agrégats et sous-agrégats.
                        </div> */}
                    </div>

                    <div className="reporting-config-card">
                        <h4>Prévision budget</h4>
                        <label>
                            <span>Cycle</span>
                            <select value={budgetCycleCode} onChange={(e) => setBudgetCycleCode(e.target.value)}>
                                {CYCLE_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                            </select>
                        </label>
                        <div className="reporting-hint">Le cycle sélectionné pilote les prévisions budget exportées.</div>
                        <label><input type="checkbox" checked={exportConfig.includeMonthlyForecast} onChange={() => toggleConfigBool('includeMonthlyForecast')} /> Inclure Forecast_Mensuel_Detail</label>
                        <label><input type="checkbox" checked={exportConfig.includeSubaggregates} onChange={() => toggleConfigBool('includeSubaggregates')} /> Inclure agrégats + sous-agrégats</label>
                        <div className="reporting-hint">Mois pour Forecast_Mensuel_Detail :</div>
                        <div className="reporting-month-picker">
                            {(availableMonths || []).map((m) => (
                                <button
                                    type="button"
                                    key={`md-${m}`}
                                    className={`reporting-month-chip ${exportConfig.monthlyDetailMonths.includes(m) ? 'active' : ''}`}
                                    onClick={() => toggleMonthlyDetailMonth(m)}
                                    disabled={!exportConfig.includeMonthlyForecast}
                                >
                                    M{String(m).padStart(2, '0')}
                                </button>
                            ))}
                            {!availableMonths.length && <div className="reporting-hint">Aucun mois réalisé détecté</div>}
                        </div>
                        
                    </div>
                </div>

                <div className="reporting-config-summary">
                    <strong>Résumé export :</strong> Cycle budget = {budgetCycleCode} · P&L = {pnlMonthsText} · Mensuel détaillé = {selectedMonthlyDetailText}
                </div>
                {!loading && !!availableMonths.length && !hasValidMonthlyDetailSelection && (
                    <div className="reporting-error">Sélectionnez au moins un mois pour le Forecast_Mensuel_Detail.</div>
                )}
                {!loading && !!availableMonths.length && !hasValidPnlSelection && (
                    <div className="reporting-error">Activez au moins un mode P&L et sélectionnez un mois si « Mois sélectionnés » est actif.</div>
                )}
            </div>

            {error && <div className="reporting-error">{error}</div>}

            
        </div>
    );
}

export default Reporting;
