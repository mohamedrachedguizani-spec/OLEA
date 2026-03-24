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
    const [catalogItems, setCatalogItems] = useState([]);
    const [chartCatalogMode, setChartCatalogMode] = useState('base'); // base | derived
    const [chartAgregatKey, setChartAgregatKey] = useState('ca_brut');
    const [chartData, setChartData] = useState([]);
    const [chartLoading, setChartLoading] = useState(false);

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

    const reloadAll = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            await Promise.all([loadStatus(), loadComparison(), loadCatalog()]);
        } catch (e) {
            setError(e.message || 'Erreur chargement forecast');
        } finally {
            setLoading(false);
        }
    }, [loadStatus, loadComparison, loadCatalog]);

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

    const totals = useMemo(() => {
        return comparisonRows.reduce(
            (acc, row) => {
                acc.forecast += Number(row.forecast_value || 0);
                acc.actual += Number(row.actual_value || 0);
                return acc;
            },
            { forecast: 0, actual: 0 }
        );
    }, [comparisonRows]);

    const selectedChartLabel = useMemo(() => {
        const item = catalogItems.find((c) => c.agregat_key === chartAgregatKey);
        return item?.agregat_label || chartAgregatKey;
    }, [catalogItems, chartAgregatKey]);

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
                    <div className="comparison-totals">
                        <span>Prévision (somme): {fmt(totals.forecast, 0)}</span>
                        <span>Réalisé (somme): {fmt(totals.actual, 0)}</span>
                    </div>
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
        </div>
    );
}

export default SageBfcForecast;
