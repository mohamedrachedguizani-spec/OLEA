// src/components/sage-bfc/SageBfcDashboard.js
import React, { useMemo } from 'react';

function SageBfcDashboard({ monthlyData, sortedMonths, formatMonthLabel, formatMonthShort }) {
    const fmt = (val) => {
        if (val == null) return '—';
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0
        }).format(val);
    };

    const fmtFull = (val) => {
        if (val == null) return '—';
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(val);
    };

    const fmtPct = (val) => {
        if (val == null) return '—';
        return `${val >= 0 ? '+' : ''}${val.toFixed(1)}%`;
    };

    const getDelta = (current, previous) => {
        if (previous == null || previous === 0) return null;
        return ((current - previous) / Math.abs(previous)) * 100;
    };

    // Données de comparaison mensuelles
    const monthsData = useMemo(() => {
        return sortedMonths.map(m => ({
            key: m,
            label: formatMonthShort(m),
            fullLabel: formatMonthLabel(m),
            resume: monthlyData[m]?.result?.resume || {},
            lignesCount: monthlyData[m]?.result?.lignes?.length || monthlyData[m]?.lignesCount || 0,
            validationsCount: monthlyData[m]?.result?.validations?.length || 0,
            alertesCount: (monthlyData[m]?.result?.validations || []).filter(v => v.statut === 'ALERTE').length,
            uploadDate: monthlyData[m]?.uploadDate
        }));
    }, [sortedMonths, monthlyData, formatMonthShort, formatMonthLabel]);

    // Lignes du tableau P&L de comparaison
    const comparisonRows = [
        { key: 'ca_brut', label: 'CA Brut', section: 'produits', bold: false },
        { key: 'retrocessions', label: 'Rétrocessions', section: 'produits', bold: false },
        { key: 'ca_net', label: 'CA Net', section: 'produits', bold: true },
        { key: 'autres_produits', label: 'Autres Produits', section: 'produits', bold: false },
        { key: 'total_produits', label: 'Total Produits', section: 'produits', bold: true, isTotal: true },
        { key: 'frais_personnel', label: 'Frais Personnel', section: 'charges', bold: false },
        { key: 'honoraires', label: 'Honoraires', section: 'charges', bold: false },
        { key: 'frais_commerciaux', label: 'Frais Commerciaux', section: 'charges', bold: false },
        { key: 'impots_taxes', label: 'Impôts & Taxes', section: 'charges', bold: false },
        { key: 'fonctionnement', label: 'Fonctionnement', section: 'charges', bold: false },
        { key: 'autres_charges', label: 'Autres Charges', section: 'charges', bold: false },
        { key: 'total_charges', label: 'Total Charges', section: 'charges', bold: true, isTotal: true },
        { key: 'ebitda', label: 'EBITDA', section: 'ebitda', bold: true, highlight: true },
        { key: 'ebitda_pct', label: 'Marge EBITDA %', section: 'ebitda', bold: false, isPct: true },
        { key: 'resultat_financier', label: 'Résultat Financier', section: 'financier', bold: false },
        { key: 'dotations', label: 'Dotations', section: 'financier', bold: false },
        { key: 'resultat_avant_impot', label: 'Résultat avant IS', section: 'resultat', bold: true },
        { key: 'impot_societes', label: 'IS', section: 'resultat', bold: false },
        { key: 'resultat_net', label: 'Résultat Net', section: 'resultat', bold: true, highlight: true },
        { key: 'resultat_net_pct', label: 'Marge Nette %', section: 'resultat', bold: false, isPct: true },
    ];

    // Calcul des max pour les barres visuelles
    const maxValues = useMemo(() => {
        const max = {};
        ['ca_net', 'ebitda', 'total_charges', 'resultat_net'].forEach(key => {
            max[key] = Math.max(...monthsData.map(m => Math.abs(m.resume[key] || 0)), 1);
        });
        return max;
    }, [monthsData]);

    if (sortedMonths.length === 0) {
        return (
            <div className="dashboard-empty">
                <div className="dashboard-empty-icon">📊</div>
                <h4>Aucune donnée mensuelle</h4>
                <p>Chargez une balance SAGE pour commencer l'analyse.</p>
            </div>
        );
    }

    return (
        <div className="sage-dashboard-container">
            {/* Résumé global */}
            <div className="dashboard-summary-grid">
                <div className="dashboard-summary-card">
                    <div className="summary-card-icon">📅</div>
                    <div className="summary-card-info">
                        <span className="summary-card-value">{sortedMonths.length}</span>
                        <span className="summary-card-label">Mois chargés</span>
                    </div>
                </div>
                <div className="dashboard-summary-card">
                    <div className="summary-card-icon">📋</div>
                    <div className="summary-card-info">
                        <span className="summary-card-value">
                            {monthsData.reduce((s, m) => s + m.lignesCount, 0)}
                        </span>
                        <span className="summary-card-label">Lignes totales</span>
                    </div>
                </div>
                <div className="dashboard-summary-card">
                    <div className="summary-card-icon">⚠️</div>
                    <div className="summary-card-info">
                        <span className="summary-card-value">
                            {monthsData.reduce((s, m) => s + m.alertesCount, 0)}
                        </span>
                        <span className="summary-card-label">Alertes totales</span>
                    </div>
                </div>
                <div className="dashboard-summary-card">
                    <div className="summary-card-icon">💰</div>
                    <div className="summary-card-info">
                        <span className={`summary-card-value ${monthsData[monthsData.length - 1]?.resume?.resultat_net < 0 ? 'negative' : ''}`}>
                            {fmtFull(monthsData[monthsData.length - 1]?.resume?.resultat_net)}
                        </span>
                        <span className="summary-card-label">Dernier RN (TND)</span>
                    </div>
                </div>
            </div>

            {/* Barres visuelles d'évolution pour les KPIs clés */}
            {/* <div className="dashboard-evolution-section">
                <h3 className="dashboard-section-title">
                    <span>📈</span> Évolution mensuelle
                </h3>
                <div className="evolution-charts">
                    {['ca_net', 'ebitda', 'total_charges', 'resultat_net'].map(key => {
                        const labelMap = {
                            ca_net: 'CA Net',
                            ebitda: 'EBITDA',
                            total_charges: 'Total Charges',
                            resultat_net: 'Résultat Net'
                        };
                        const colorMap = {
                            ca_net: 'var(--primary-500)',
                            ebitda: 'var(--success)',
                            total_charges: 'var(--warning)',
                            resultat_net: 'var(--info)'
                        };
                        return (
                            <div key={key} className="evolution-chart-card">
                                <div className="evolution-chart-header">
                                    <span className="evolution-chart-label">{labelMap[key]}</span>
                                </div>
                                <div className="evolution-bars">
                                    {monthsData.map((m, idx) => {
                                        const val = m.resume[key] || 0;
                                        const pct = (Math.abs(val) / maxValues[key]) * 100;
                                        return (
                                            <div key={m.key} className="evolution-bar-item" title={`${m.fullLabel}: ${fmtFull(val)} TND`}>
                                                <div className="evolution-bar-track">
                                                    <div
                                                        className="evolution-bar-fill"
                                                        style={{
                                                            height: `${Math.max(pct, 3)}%`,
                                                            background: val < 0 ? 'var(--error)' : colorMap[key],
                                                            opacity: 0.6 + (idx / monthsData.length) * 0.4
                                                        }}
                                                    />
                                                </div>
                                                <span className="evolution-bar-label">{m.label}</span>
                                                <span className={`evolution-bar-value ${val < 0 ? 'negative' : ''}`}>
                                                    {fmt(val)}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div> */}

            {/* Tableau de comparaison P&L mensuel */}
            <div className="dashboard-comparison-section">
                <h3 className="dashboard-section-title">
                    <span>📊</span> Comparaison P&L mensuelle
                </h3>
                <div className="comparison-table-wrapper">
                    <table className="comparison-table">
                        <thead>
                            <tr>
                                <th className="comparison-th-label">Poste</th>
                                {monthsData.map(m => (
                                    <th key={m.key} className="comparison-th-month">
                                        {m.label}
                                    </th>
                                ))}
                                {monthsData.length >= 2 && (
                                    <th className="comparison-th-delta">Δ Dernier</th>
                                )}
                            </tr>
                        </thead>
                        <tbody>
                            {comparisonRows.map((row) => {
                                const lastIdx = monthsData.length - 1;
                                const prevIdx = lastIdx - 1;
                                const lastVal = monthsData[lastIdx]?.resume?.[row.key];
                                const prevVal = prevIdx >= 0 ? monthsData[prevIdx]?.resume?.[row.key] : null;
                                const delta = getDelta(lastVal, prevVal);

                                return (
                                    <tr
                                        key={row.key}
                                        className={`comparison-row ${row.bold ? 'bold' : ''} ${row.isTotal ? 'total-row' : ''} ${row.highlight ? 'highlight-row' : ''} section-${row.section}`}
                                    >
                                        <td className="comparison-label">{row.label}</td>
                                        {monthsData.map(m => {
                                            const val = m.resume[row.key];
                                            return (
                                                <td key={m.key} className={`comparison-value ${val < 0 ? 'negative' : ''}`}>
                                                    {row.isPct ? `${(val || 0).toFixed(1)}%` : fmt(val)}
                                                </td>
                                            );
                                        })}
                                        {monthsData.length >= 2 && (
                                            <td className={`comparison-delta ${delta > 0 ? 'delta-up' : delta < 0 ? 'delta-down' : ''}`}>
                                                {delta != null ? fmtPct(delta) : '—'}
                                            </td>
                                        )}
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Détail par mois */}
            <div className="dashboard-months-section">
                <h3 className="dashboard-section-title">
                    <span>📁</span> Détails par mois
                </h3>
                <div className="months-detail-grid">
                    {monthsData.map((m, idx) => {
                        const prevResume = idx > 0 ? monthsData[idx - 1].resume : null;
                        const rnDelta = getDelta(m.resume.resultat_net, prevResume?.resultat_net);
                        return (
                            <div key={m.key} className="month-detail-card">
                                <div className="month-detail-header">
                                    <span className="month-detail-title">{m.fullLabel}</span>
                                    <span className={`month-detail-rn ${m.resume.resultat_net >= 0 ? 'positive' : 'negative'}`}>
                                        {fmtFull(m.resume.resultat_net)} TND
                                    </span>
                                </div>
                                <div className="month-detail-body">
                                    <div className="month-detail-row">
                                        <span>CA Net</span>
                                        <span>{fmtFull(m.resume.ca_net)}</span>
                                    </div>
                                    <div className="month-detail-row">
                                        <span>EBITDA</span>
                                        <span className={m.resume.ebitda < 0 ? 'negative' : ''}>
                                            {fmtFull(m.resume.ebitda)}
                                        </span>
                                    </div>
                                    <div className="month-detail-row">
                                        <span>Marge EBITDA</span>
                                        <span>{(m.resume.ebitda_pct || 0).toFixed(1)}%</span>
                                    </div>
                                    <div className="month-detail-row">
                                        <span>Lignes mappées</span>
                                        <span>{m.lignesCount}</span>
                                    </div>
                                    {m.alertesCount > 0 && (
                                        <div className="month-detail-row alerte">
                                            <span>⚠️ Alertes</span>
                                            <span>{m.alertesCount}</span>
                                        </div>
                                    )}
                                </div>
                                {rnDelta != null && (
                                    <div className={`month-detail-footer ${rnDelta >= 0 ? 'delta-up' : 'delta-down'}`}>
                                        {rnDelta >= 0 ? '↗' : '↘'} {rnDelta >= 0 ? '+' : ''}{rnDelta.toFixed(1)}% vs mois précédent
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}

export default SageBfcDashboard;
