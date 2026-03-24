import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ApiService from '../../services/api';
import {
    ResponsiveContainer,
    LineChart,
    Line,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    Legend,
} from 'recharts';

const CYCLE_OPTIONS = ['INITIAL', 'M03', 'M06', 'M08'];

function SageBfcForecast({ selectedMonth, refreshTrigger }) {
    const now = new Date();
    const inferredYear = useMemo(() => {
        if (selectedMonth && selectedMonth !== '__all_periods__') {
            const d = new Date(selectedMonth);
            if (!Number.isNaN(d.getTime())) return d.getFullYear();
        }
        return now.getFullYear();
    }, [selectedMonth, now]);

    const inferredMonth = useMemo(() => {
        if (selectedMonth && selectedMonth !== '__all_periods__') {
            const d = new Date(selectedMonth);
            if (!Number.isNaN(d.getTime())) return d.getMonth() + 1;
        }
        return now.getMonth() + 1;
    }, [selectedMonth, now]);

    const [targetYear, setTargetYear] = useState(inferredYear);
    const [compareCycle, setCompareCycle] = useState('INITIAL');
    const [compareMonth, setCompareMonth] = useState(inferredMonth);

    const [loading, setLoading] = useState(false);
    const [actionLoading, setActionLoading] = useState('');
    const [error, setError] = useState('');
    const [successMsg, setSuccessMsg] = useState('');

    const [cycleStatus, setCycleStatus] = useState([]);
    const [comparisonRows, setComparisonRows] = useState([]);
    const [annualRows, setAnnualRows] = useState([]);
    const [annualMeta, setAnnualMeta] = useState({
        cycle_phase: 'INITIAL',
        uploaded_months: [],
        cycle_cutoff_month: null,
    });
    const [catalogItems, setCatalogItems] = useState([]);
    const [chartCatalogMode, setChartCatalogMode] = useState('base'); // base | derived
    const [chartAgregatKey, setChartAgregatKey] = useState('ca_brut');
    const [activeView, setActiveView] = useState('annual'); // annual | monthly
    const [chartData, setChartData] = useState([]);
    const [chartLoading, setChartLoading] = useState(false);
    const [annualSearch, setAnnualSearch] = useState('');
    const [alertsOnly, setAlertsOnly] = useState(false);

    useEffect(() => {
        setTargetYear(inferredYear);
    }, [inferredYear]);

    useEffect(() => {
        setCompareMonth(inferredMonth);
    }, [inferredMonth]);

    const fmt = (v, digits = 2) => {
        if (v == null || Number.isNaN(Number(v))) return '—';
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(Number(v));
    };

    const fmtPct = (v) => {
        if (v == null || Number.isNaN(Number(v))) return '—';
        const n = Number(v);
        return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
    };

    const alertLabel = (level) => {
        if (level === 'positive') return 'Favorable';
        if (level === 'negative') return 'Défavorable';
        if (level === 'neutral') return 'Neutre';
        return '—';
    };

    const loadStatus = useCallback(async () => {
        const status = await ApiService.getForecastCyclesStatus(targetYear);
        setCycleStatus(status.cycles || []);
    }, [targetYear]);

    const loadCatalog = useCallback(async () => {
        const catalog = await ApiService.getForecastCatalog();
        setCatalogItems(catalog.items || []);
    }, [chartAgregatKey]);

    const loadComparison = useCallback(async () => {
        const res = await ApiService.getForecastComparison(targetYear, compareCycle, compareMonth);
        setComparisonRows(res.rows || []);
    }, [targetYear, compareCycle, compareMonth]);

    const loadAnnualComparison = useCallback(async () => {
        const res = await ApiService.getForecastAnnualComparison(targetYear, compareCycle);
        setAnnualRows(res.rows || []);
        setAnnualMeta({
            cycle_phase: res.cycle_phase || 'INITIAL',
            uploaded_months: res.uploaded_months || [],
            cycle_cutoff_month: res.cycle_cutoff_month ?? null,
        });
    }, [targetYear, compareCycle]);

    const reloadAll = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            await Promise.all([loadStatus(), loadComparison(), loadAnnualComparison(), loadCatalog()]);
        } catch (e) {
            setError(e.message || 'Erreur chargement forecast');
        } finally {
            setLoading(false);
        }
    }, [loadStatus, loadComparison, loadAnnualComparison, loadCatalog]);

    useEffect(() => {
        reloadAll();
    }, [reloadAll]);

    useEffect(() => {
        if (refreshTrigger > 0) {
            reloadAll();
        }
    }, [refreshTrigger, reloadAll]);

    const runAction = async (key, fn, okMessage) => {
        setActionLoading(key);
        setError('');
        setSuccessMsg('');
        try {
            await fn();
            setSuccessMsg(okMessage);
            await reloadAll();
        } catch (e) {
            setError(e.message || 'Erreur action forecast');
        } finally {
            setActionLoading('');
        }
    };

    const loadChartData = useCallback(async () => {
        if (!chartAgregatKey) return;
        setChartLoading(true);
        try {
            const yearSeries = await ApiService.getForecastYearValues(targetYear, compareCycle, chartAgregatKey);
            const monthlyComparisons = await Promise.all(
                Array.from({ length: 12 }, (_, idx) => idx + 1).map((m) =>
                    ApiService.getForecastComparison(targetYear, compareCycle, m)
                )
            );

            const points = Array.from({ length: 12 }, (_, idx) => {
                const month = idx + 1;
                const comparison = monthlyComparisons[idx];
                const row = (comparison.rows || []).find((r) => r.agregat_key === chartAgregatKey);
                return {
                    month,
                    monthLabel: `M${String(month).padStart(2, '0')}`,
                    forecast: yearSeries.values?.[month] ?? null,
                    actual: row?.actual_value ?? null,
                    ecart: row?.ecart_value ?? null,
                };
            });
            setChartData(points);
        } catch (e) {
            setError(e.message || 'Erreur chargement graphe');
        } finally {
            setChartLoading(false);
        }
    }, [targetYear, compareCycle, chartAgregatKey]);

    useEffect(() => {
        loadChartData();
    }, [loadChartData]);

    useEffect(() => {
        if (refreshTrigger > 0) {
            loadChartData();
        }
    }, [refreshTrigger, loadChartData]);

    const selectedChartLabel = useMemo(() => {
        const item = catalogItems.find((c) => c.agregat_key === chartAgregatKey);
        return item?.agregat_label || chartAgregatKey;
    }, [catalogItems, chartAgregatKey]);

    const annualFilteredRows = useMemo(() => {
        const q = annualSearch.trim().toLowerCase();
        return annualRows.filter((row) => {
            const byText =
                !q ||
                String(row.agregat_label || '').toLowerCase().includes(q) ||
                String(row.agregat_key || '').toLowerCase().includes(q) ||
                String(row.indicator_label || '').toLowerCase().includes(q);
            const byAlert = !alertsOnly || row.alert_level === 'negative';
            return byText && byAlert;
        });
    }, [annualRows, annualSearch, alertsOnly]);

    const dashboardKpis = useMemo(() => {
        const negativeAlerts = annualRows.filter((r) => r.alert_level === 'negative').length;
        const positiveAlerts = annualRows.filter((r) => r.alert_level === 'positive').length;
        const onTrack = annualRows.filter((r) => Number(r.taux_realisation_annuel_pct || 0) >= 100).length;
        return {
            total: annualRows.length,
            negativeAlerts,
            positiveAlerts,
            onTrack,
        };
    }, [annualRows]);

    const selectedCycleMeta = useMemo(() => {
        return cycleStatus.find((c) => c.cycle_code === compareCycle) || null;
    }, [cycleStatus, compareCycle]);

    const chartSelectableItems = useMemo(() => {
        if (chartCatalogMode === 'derived') {
            return catalogItems.filter((x) => x.is_derived);
        }
        return catalogItems.filter((x) => !x.is_derived);
    }, [catalogItems, chartCatalogMode]);

    useEffect(() => {
        if (!chartSelectableItems.length) return;
        const exists = chartSelectableItems.some((x) => x.agregat_key === chartAgregatKey);
        if (!exists) {
            setChartAgregatKey(chartSelectableItems[0].agregat_key);
        }
    }, [chartSelectableItems, chartAgregatKey]);

    return (
        <div className="forecast-panel">
            <div className="forecast-toolbar">
                <div className="forecast-toolbar-left">
                    <label className="forecast-field">
                        <span>Année</span>
                        <input
                            type="number"
                            min="2000"
                            max="2100"
                            value={targetYear}
                            onChange={(e) => setTargetYear(Number(e.target.value || now.getFullYear()))}
                        />
                    </label>

                    <label className="forecast-field">
                        <span>Cycle comparaison</span>
                        <select value={compareCycle} onChange={(e) => setCompareCycle(e.target.value)}>
                            {CYCLE_OPTIONS.map((c) => (
                                <option key={c} value={c}>{c}</option>
                            ))}
                        </select>
                    </label>

                    <label className="forecast-field">
                        <span>Mois comparaison</span>
                        <select value={compareMonth} onChange={(e) => setCompareMonth(Number(e.target.value))}>
                            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                                <option key={m} value={m}>M{String(m).padStart(2, '0')}</option>
                            ))}
                        </select>
                    </label>
                </div>

                <div className="forecast-toolbar-actions">
                    <button
                        className="btn-forecast"
                        onClick={() => runAction('import-hist', () => ApiService.importForecastHistorical(), 'Historique migré vers la base')}
                        disabled={!!actionLoading}
                    >
                        {actionLoading === 'import-hist' ? 'Import...' : 'Importer historique 2024/2025'}
                    </button>

                    <button
                        className="btn-forecast primary"
                        onClick={() => runAction('initial', () => ApiService.generateForecast(targetYear, 'INITIAL'), 'Budget initial généré')}
                        disabled={!!actionLoading}
                    >
                        {actionLoading === 'initial' ? 'Génération...' : `Générer budget initial ${targetYear}`}
                    </button>
                </div>
            </div>

            {(error || successMsg) && (
                <div className={`forecast-message ${error ? 'error' : 'success'}`}>
                    {error || successMsg}
                </div>
            )}

            <div className="forecast-dashboard-grid">
                <div className="forecast-kpi-card">
                    <div className="forecast-kpi-title">Agrégats suivis</div>
                    <div className="forecast-kpi-value">{dashboardKpis.total}</div>
                </div>
                <div className="forecast-kpi-card negative">
                    <div className="forecast-kpi-title">Alertes défavorables</div>
                    <div className="forecast-kpi-value">{dashboardKpis.negativeAlerts}</div>
                </div>
                <div className="forecast-kpi-card positive">
                    <div className="forecast-kpi-title">Indicateurs favorables</div>
                    <div className="forecast-kpi-value">{dashboardKpis.positiveAlerts}</div>
                </div>
                <div className="forecast-kpi-card info">
                    <div className="forecast-kpi-title">Réalisé ≥ 100%</div>
                    <div className="forecast-kpi-value">{dashboardKpis.onTrack}</div>
                </div>
            </div>

            <div className="forecast-section-head">
                <h3>Pilotage des cycles d'ajustement</h3>
                <span>{selectedCycleMeta?.cycle_label || 'Cycle non disponible'}</span>
            </div>

            <div className="forecast-cycles-grid">
                {cycleStatus.map((c) => (
                    <div key={c.cycle_code} className="forecast-cycle-card">
                        <div className="forecast-cycle-head">
                            <h4>{c.cycle_label}</h4>
                            <span className={`cycle-pill ${c.can_trigger ? 'ready' : 'blocked'}`}>
                                {c.can_trigger ? 'Prêt' : 'En attente'}
                            </span>
                        </div>

                        <div className="forecast-cycle-body">
                            <div><strong>Code:</strong> {c.cycle_code}</div>
                            <div><strong>Mois cycle:</strong> M{String(c.cycle_month).padStart(2, '0')}</div>
                            <div><strong>Mois uploadés:</strong> {(c.uploaded_months || []).join(', ') || '—'}</div>
                            <div><strong>Mois manquants:</strong> {(c.missing_months || []).join(', ') || 'Aucun'}</div>
                            <div><strong>Exécuté:</strong> {c.is_executed ? 'Oui' : 'Non'}</div>
                            {!!c.reason && <div className="cycle-reason">{c.reason}</div>}
                        </div>

                        <div className="forecast-cycle-actions">
                            <button
                                className="btn-forecast"
                                disabled={!c.can_trigger || !!actionLoading}
                                title={c.can_trigger ? `Lancer ${c.cycle_code}` : (c.reason || 'Cycle indisponible')}
                                onClick={() =>
                                    runAction(
                                        `run-${c.cycle_code}`,
                                        () => ApiService.runForecastCycle(targetYear, c.cycle_code),
                                        `Cycle ${c.cycle_code} exécuté`
                                    )
                                }
                            >
                                {actionLoading === `run-${c.cycle_code}` ? 'Exécution...' : `Lancer ${c.cycle_code}`}
                            </button>
                            {!c.can_trigger && (
                                <span className="cycle-action-hint">{c.reason || 'Cycle indisponible'}</span>
                            )}
                        </div>
                    </div>
                ))}
            </div>

            <div className="forecast-section-head">
                <h3>Vue de comparaison</h3>
                <span>Basculez entre l'analyse annuelle et mensuelle</span>
            </div>

            <div className="forecast-view-tabs">
                <button
                    className={`forecast-view-tab ${activeView === 'annual' ? 'active' : ''}`}
                    onClick={() => setActiveView('annual')}
                >
                    Comparaison annuelle
                </button>
                <button
                    className={`forecast-view-tab ${activeView === 'monthly' ? 'active' : ''}`}
                    onClick={() => setActiveView('monthly')}
                >
                    Comparaison mensuelle
                </button>
            </div>

            {activeView === 'annual' && (
                <div className="forecast-comparison-panel annual-comparison-panel">
                    <div className="comparison-header">
                        <h4>Comparaison globale annuelle — Prévision vs Réalisé ({targetYear} / {compareCycle})</h4>
                        <div className="comparison-totals annual-totals">
                            <span>Phase cycle: {annualMeta.cycle_phase || 'INITIAL'}</span>
                            <span>Mois réels: {(annualMeta.uploaded_months || []).join(', ') || '—'}</span>
                            {annualMeta.cycle_cutoff_month != null && (
                                <span>Palier cycle: M{String(annualMeta.cycle_cutoff_month).padStart(2, '0')}</span>
                            )}
                        </div>
                    </div>
                    <div className="annual-table-controls">
                        <label className="forecast-field annual-search-field">
                            <span>Recherche agrégat / indice</span>
                            <input
                                type="text"
                                placeholder="Ex: frais personnel"
                                value={annualSearch}
                                onChange={(e) => setAnnualSearch(e.target.value)}
                            />
                        </label>
                        <label className="annual-alerts-only">
                            <input
                                type="checkbox"
                                checked={alertsOnly}
                                onChange={(e) => setAlertsOnly(e.target.checked)}
                            />
                            <span>Afficher uniquement les alertes défavorables</span>
                        </label>
                        <div className="annual-rows-count">{annualFilteredRows.length} ligne(s)</div>
                    </div>

                    {loading ? (
                        <div className="forecast-loading">Chargement...</div>
                    ) : (
                        <div className="forecast-table-wrap">
                            <table className="forecast-table annual-forecast-table">
                                <thead>
                                    <tr>
                                        <th>Agrégat</th>
                                        <th>Nature</th>
                                        <th>Prévision annuelle</th>
                                        <th>Réalisé cumulé</th>
                                        <th>Taux réalisation annuel</th>
                                        <th>Reste budget</th>
                                        <th>Indice / alerte</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {annualFilteredRows.map((row) => (
                                        <tr key={`annual-${row.agregat_key}`}>
                                            <td>{row.agregat_label}</td>
                                            <td>
                                                <span className={`nature-pill ${row.nature}`}>
                                                    {row.nature}
                                                </span>
                                            </td>
                                            <td>{fmt(row.forecast_annual, 2)}</td>
                                            <td>{fmt(row.actual_total, 2)}</td>
                                            <td className={Number(row.taux_realisation_annuel_pct || 0) < 100 ? 'neg' : 'pos'}>{fmtPct(row.taux_realisation_annuel_pct)}</td>
                                            <td className={Number(row.remaining_budget || 0) < 0 ? 'neg' : 'pos'}>{fmt(row.remaining_budget, 2)}</td>
                                            <td>
                                                <div className="annual-indicator-cell">
                                                    <span className={`alert-pill ${row.alert_level || 'none'}`}>
                                                        {alertLabel(row.alert_level)}
                                                    </span>
                                                    <span className="annual-indicator-text">{row.indicator_label || '—'}</span>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}

            {activeView === 'monthly' && (
                <div className="forecast-comparison-panel">
                    <div className="forecast-chart-panel">
                        <div className="comparison-header">
                            <h4>Graphe mensuel Prévision vs Réel — {selectedChartLabel}</h4>
                            <div className="forecast-chart-controls">
                                    <div className="forecast-toggle-group">
                                        <button
                                            className={`forecast-toggle-btn ${chartCatalogMode === 'base' ? 'active' : ''}`}
                                            onClick={() => setChartCatalogMode('base')}
                                        >
                                            Base agrégats
                                        </button>
                                        <button
                                            className={`forecast-toggle-btn ${chartCatalogMode === 'derived' ? 'active' : ''}`}
                                            onClick={() => setChartCatalogMode('derived')}
                                        >
                                            P&L dérivés
                                        </button>
                                    </div>
                                <label className="forecast-field">
                                    <span>Agrégat</span>
                                    <select value={chartAgregatKey} onChange={(e) => setChartAgregatKey(e.target.value)}>
                                            {chartSelectableItems.map((it) => (
                                            <option key={it.agregat_key} value={it.agregat_key}>
                                                {it.agregat_label}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                            </div>
                        </div>

                        {chartLoading ? (
                            <div className="forecast-loading">Chargement graphe...</div>
                        ) : (
                            <div className="forecast-linechart-wrap">
                                <ResponsiveContainer width="100%" height={320}>
                                    <LineChart data={chartData} margin={{ top: 8, right: 20, left: 0, bottom: 8 }}>
                                        <CartesianGrid strokeDasharray="3 3" />
                                        <XAxis dataKey="monthLabel" />
                                        <YAxis />
                                        <Tooltip
                                            formatter={(value, name) => {
                                                if (value == null) return ['—', name];
                                                return [fmt(value, 2), name];
                                            }}
                                        />
                                        <Legend />
                                        <Line type="monotone" dataKey="forecast" name="Prévision" stroke="#2563eb" strokeWidth={2.5} dot={{ r: 2 }} />
                                        <Line type="monotone" dataKey="actual" name="Réalisé" stroke="#16a34a" strokeWidth={2.5} dot={{ r: 2 }} connectNulls />
                                        <Line type="monotone" dataKey="ecart" name="Écart" stroke="#ea580c" strokeWidth={2} dot={false} connectNulls />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        )}
                    </div>

                    <div className="comparison-header">
                        <h4>Comparaison Prévision vs Réalisé — {targetYear} / {compareCycle} / M{String(compareMonth).padStart(2, '0')}</h4>
                    </div>

                    {loading ? (
                        <div className="forecast-loading">Chargement...</div>
                    ) : (
                        <div className="forecast-table-wrap">
                            <table className="forecast-table">
                                <thead>
                                    <tr>
                                        <th>Agrégat</th>
                                        <th>Nature</th>
                                        <th>Prévision</th>
                                        <th>Réalisé</th>
                                        <th>Écart</th>
                                        <th>Écart %</th>
                                        <th>Alerte</th>
                                        <th>Modèle</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {comparisonRows.map((row) => (
                                        <tr key={row.agregat_key}>
                                            <td>{row.agregat_label}</td>
                                            <td>
                                                <span className={`nature-pill ${row.nature}`}>
                                                    {row.nature}
                                                </span>
                                            </td>
                                            <td>{fmt(row.forecast_value, 2)}</td>
                                            <td>{fmt(row.actual_value, 2)}</td>
                                            <td className={Number(row.ecart_value || 0) < 0 ? 'neg' : 'pos'}>{fmt(row.ecart_value, 2)}</td>
                                            <td className={Number(row.ecart_pct || 0) < 0 ? 'neg' : 'pos'}>{fmtPct(row.ecart_pct)}</td>
                                            <td>
                                                <span className={`alert-pill ${row.alert_level || 'none'}`}>
                                                    {alertLabel(row.alert_level)}
                                                </span>
                                            </td>
                                            <td>{row.model_name || '—'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default SageBfcForecast;
