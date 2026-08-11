import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom';
import ApiService from '../services/api';
import '../styles/Reporting.css';

const CYCLE_OPTIONS = ['INITIAL', 'M03', 'M06', 'M08'];

function Reporting({ refreshTrigger = 0 }) {
    const now = new Date();
    const [targetYear, setTargetYear] = useState(now.getFullYear());
    const [budgetCycleCode, setBudgetCycleCode] = useState('INITIAL');

    const [loading, setLoading] = useState(false);
    const [exportLoading, setExportLoading] = useState(false);
    const [printLoading, setPrintLoading] = useState(false);
    const [error, setError] = useState('');
    const [preview, setPreview] = useState(null);

    const [showPreviewModal, setShowPreviewModal] = useState(false);
    const [previewSections, setPreviewSections] = useState(null);
    const [previewAction, setPreviewAction] = useState(null);
    const [previewLoading, setPreviewLoading] = useState(false);

    const [exportConfig, setExportConfig] = useState({
        includePnlSelected: true,
        includePnlGlobal: false,
        pnlMonths: [],
        monthlyDetailMonths: [],
        includeExecutiveSummary: true,
        includePnlFormatted: false,
        includeBudgetForecast: true,
        includeGlobalState: false,
        includeMonthlyForecast: false,
        includeCycles: false,
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

    const configPayload = useMemo(() => ({
        ...exportConfig,
        budgetCycleCode,
    }), [exportConfig, budgetCycleCode]);

    const openPreview = async (action) => {
        setPreviewLoading(true);
        setPreviewAction(action);
        setError('');
        try {
            const data = await ApiService.getReportingPreviewSections(targetYear, 'INITIAL', null, configPayload);
            setPreviewSections(data);
            setShowPreviewModal(true);
        } catch (e) {
            setError(e.message || 'Erreur chargement prévisualisation');
        } finally {
            setPreviewLoading(false);
        }
    };

    const handleExport = async () => {
        setExportLoading(true);
        setError('');
        try {
            await ApiService.exportReportingExcel(targetYear, 'INITIAL', null, configPayload);
        } catch (e) {
            setError(e.message || 'Erreur export reporting');
        } finally {
            setExportLoading(false);
        }
    };

    const handlePrint = async () => {
        setPrintLoading(true);
        setError('');
        try {
            await ApiService.printReporting(targetYear, 'INITIAL', null, configPayload);
        } catch (e) {
            setError(e.message || 'Erreur impression reporting');
        } finally {
            setPrintLoading(false);
        }
    };

    const handleConfirmPreview = async () => {
        setShowPreviewModal(false);
        if (previewAction === 'excel') {
            await handleExport();
        } else if (previewAction === 'print') {
            await handlePrint();
        }
        setPreviewSections(null);
        setPreviewAction(null);
    };

    const handleCancelPreview = () => {
        setShowPreviewModal(false);
        setPreviewSections(null);
        setPreviewAction(null);
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
                        <p className="reporting-subtitle">Pilotage d'export homogène avec les autres modules</p>
                    </div>
                </div>
            </div>

            <div className="reporting-toolbar reporting-toolbar-shell">
                <div className="reporting-toolbar-head">
                    <h3>Filtres et actions</h3>
                    <span>Export et impression selon la configuration sélectionnée</span>
                </div>

                <div className="reporting-toolbar-grid">
                    <label>
                        <span>Année</span>
                        <input type="number" min="2000" max="2100" value={targetYear} onChange={(e) => setTargetYear(Number(e.target.value || now.getFullYear()))} />
                    </label>
                    <label>
                        <span>Cycle budget</span>
                        <select value={budgetCycleCode} onChange={(e) => setBudgetCycleCode(e.target.value)}>
                            {CYCLE_OPTIONS.map((c) => <option key={c} value={c}>{c}</option>)}
                        </select>
                    </label>
                </div>

                <div className="reporting-actions">
                    <button className="btn-reporting" onClick={() => openPreview('print')} disabled={previewLoading || printLoading || !hasAnySection || !hasValidMonthlyDetailSelection || !hasValidPnlSelection}>{previewLoading && previewAction === 'print' ? 'Chargement...' : printLoading ? 'Impression...' : '🖨 Imprimer'}</button>
                    <button className="btn-reporting primary" onClick={() => openPreview('excel')} disabled={previewLoading || exportLoading || !hasAnySection || !hasValidMonthlyDetailSelection || !hasValidPnlSelection}>{previewLoading && previewAction === 'excel' ? 'Chargement...' : exportLoading ? 'Export...' : '⬇ Export Excel'}</button>
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
                        <div className="reporting-hint">Le cycle budget sélectionné en haut pilote les prévisions exportées.</div>
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

            {showPreviewModal && previewSections && ReactDOM.createPortal(
                <div className="csv-preview-modal">
                    <div className="csv-preview-backdrop" onClick={handleCancelPreview}></div>
                    <div className="csv-preview-container">
                        <div className="csv-preview-header">
                            <div className="csv-preview-title">
                                <span>📄</span>
                                <h3>Prévisualisation Reporting</h3>
                            </div>
                            <div className="csv-preview-meta">
                                <span className="csv-filename">{previewSections.target_year} — {previewSections.cycle_code}</span>
                                <span className="csv-count">{previewSections.sections?.length || 0} sections</span>
                            </div>
                            <button className="csv-preview-close" onClick={handleCancelPreview}>✕</button>
                        </div>

                        <div className="csv-preview-body">
                            {(previewSections.sections || []).map((section, sIdx) => (
                                <div key={sIdx} className="reporting-preview-section">
                                    <h4 className="reporting-preview-section-title">{section.title}</h4>
                                    {section.headers.length === 0 ? (
                                        <div className="csv-preview-empty">Aucune donnée</div>
                                    ) : (
                                        <table className="csv-preview-table">
                                            <thead>
                                                <tr>
                                                    {section.headers.map((h, hIdx) => (
                                                        <th key={hIdx}>{h}</th>
                                                    ))}
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {section.rows.map((row, rIdx) => (
                                                    <tr key={rIdx} className={section.row_classes?.[rIdx] || ''}>
                                                        {row.map((cell, cIdx) => (
                                                            <td key={cIdx}>{cell}</td>
                                                        ))}
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    )}
                                </div>
                            ))}
                        </div>

                        <div className="csv-preview-footer">
                            <button className="btn btn-secondary" onClick={handleCancelPreview}>
                                ✕ Annuler
                            </button>
                            <button
                                className="btn btn-primary"
                                onClick={handleConfirmPreview}
                                disabled={exportLoading || printLoading}
                            >
                                {previewAction === 'print' ? '🖨 Confirmer et Imprimer' : '⬇ Confirmer et Télécharger'}
                            </button>
                        </div>
                    </div>
                </div>,
                document.body
            )}
        </div>
    );
}

export default Reporting;
