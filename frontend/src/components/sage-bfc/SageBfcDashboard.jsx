// src/components/sage-bfc/SageBfcDashboard.js
import React, { useMemo } from 'react';

function SageBfcDashboard({ monthlyData, sortedMonths, formatMonthLabel, formatMonthShort, currentResume, previousResume, selectedMonth }) {
    const fmt = (val) => {
        if (val == null) return '—';
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3
        }).format(val);
    };

    const fmtFull = (val) => {
        if (val == null) return '—';
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3
        }).format(val);
    };

    const fmtPct = (val) => {
        if (val == null) return '—';
        return `${val >= 0 ? '+' : ''}${val.toFixed(3)}%`;
    };

    const getDelta = (current, previous) => {
        if (previous == null || previous === 0) return null;
        return ((current - previous) / Math.abs(previous)) * 100;
    };

    // Données mensuelles préparées
    const monthsData = useMemo(() => {
        return sortedMonths.map(m => ({
            key: m,
            label: formatMonthShort(m),
            fullLabel: formatMonthLabel(m),
            resume: monthlyData[m]?.result?.resume || {},
            lignesCount: monthlyData[m]?.result?.lignes?.length || monthlyData[m]?.lignesCount || 0,
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
        { key: 'honoraires', label: 'Honoraires & Sous-trait.', section: 'charges', bold: false },
        /* { key: 'brand_fees', label: '↳ dont Brand Fees', section: 'charges', bold: false, isSubItem: true },
        { key: 'management_fees', label: '↳ dont Mgmt Fees', section: 'charges', bold: false, isSubItem: true }, */
        { key: 'frais_commerciaux', label: 'Frais Commerciaux', section: 'charges', bold: false },
        { key: 'impots_taxes', label: 'Impôts & Taxes', section: 'charges', bold: false },
        { key: 'fonctionnement', label: 'Fonctionnement', section: 'charges', bold: false },
        { key: 'autres_charges', label: 'Autres Charges', section: 'charges', bold: false },
        { key: 'total_charges', label: 'Total Charges', section: 'charges', bold: true, isTotal: true },
        { key: 'ebitda', label: 'EBITDA', section: 'ebitda', bold: true, highlight: true },
        { key: 'ebitda_pct', label: 'Marge EBITDA %', section: 'ebitda', bold: false, isPct: true },
        { key: 'resultat_financier', label: 'Résultat Financier', section: 'financier', bold: false },
        { key: 'resultat_exceptionnel', label: 'Résultat Exceptionnel', section: 'financier', bold: false },
        { key: 'dotations', label: 'Dotations', section: 'financier', bold: false },
        { key: 'resultat_avant_impot', label: 'Résultat avant IS', section: 'resultat', bold: true },
        { key: 'impot_societes', label: 'IS', section: 'resultat', bold: false },
        { key: 'resultat_net', label: 'Résultat Net', section: 'resultat', bold: true, highlight: true },
        { key: 'resultat_net_pct', label: 'Marge Nette %', section: 'resultat', bold: false, isPct: true },
    ];

    // KPIs pour le mois sélectionné
    const kpiCards = useMemo(() => {
        if (!currentResume) return [];
        const caNetDelta = getDelta(currentResume.ca_net, previousResume?.ca_net);
        const ebitdaDelta = getDelta(currentResume.ebitda, previousResume?.ebitda);
        const chargesDelta = getDelta(currentResume.total_charges, previousResume?.total_charges);
        const rnDelta = getDelta(currentResume.resultat_net, previousResume?.resultat_net);

        return [
            {
                label: 'CA Net',
                value: currentResume.ca_net,
                delta: caNetDelta,
                theme: 'primary',
                icon: (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="12" y1="1" x2="12" y2="23"/>
                        <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                    </svg>
                )
            },
            {
                label: 'EBITDA',
                value: currentResume.ebitda,
                delta: ebitdaDelta,
                badge: `${(currentResume.ebitda_pct || 0).toFixed(3)}%`,
                theme: currentResume.ebitda >= 0 ? 'success' : 'danger',
                icon: (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                    </svg>
                )
            },
            {
                label: 'Charges Exploitation',
                value: currentResume.total_charges,
                delta: chargesDelta,
                theme: 'warning',
                subInfo: `vs Produits : ${fmtFull(currentResume.total_produits)} TND`,
                icon: (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="23,18 13.5,8.5 8.5,13.5 1,6"/>
                        <polyline points="17,18 23,18 23,12"/>
                    </svg>
                )
            },
            {
                label: 'Résultat Net',
                value: currentResume.resultat_net,
                delta: rnDelta,
                badge: `${(currentResume.resultat_net_pct || 0).toFixed(3)}%`,
                theme: currentResume.resultat_net >= 0 ? 'success' : 'danger',
                icon: (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                        <polyline points="22,4 12,14.01 9,11.01"/>
                    </svg>
                )
            },
            
        ];
    }, [currentResume, previousResume]);

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
            {/* ─── KPIs du mois sélectionné ─── */}
            {currentResume && (
                <div className="dash-kpis-grid">
                    {kpiCards.map((kpi, idx) => (
                        <div key={idx} className={`dash-kpi-card kpi-theme-${kpi.theme}`}>
                            <div className="kpi-header">
                                <span className="kpi-icon-wrap">{kpi.icon}</span>
                                {kpi.badge && <span className="kpi-badge-pill">{kpi.badge}</span>}
                            </div>
                            <div className="kpi-body">
                                <span className={`kpi-value ${kpi.value < 0 ? 'negative' : ''}`}>
                                    {fmtFull(kpi.value)}
                                </span>
                                <span className="kpi-unit">TND</span>
                            </div>
                            <div className="kpi-footer">
                                <span className="kpi-label">{kpi.label}</span>
                                {kpi.delta != null && (
                                    <span className={`kpi-indicator ${kpi.delta >= 0 ? 'up' : 'down'}`}>
                                        {kpi.delta >= 0 ? '↑' : '↓'} {Math.abs(kpi.delta).toFixed(3)}%
                                    </span>
                                )}
                            </div>
                            {kpi.subInfo && (
                                <div className="kpi-sub-info">{kpi.subInfo}</div>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* ─── Tableau P&L comparatif mensuel ─── */}
            {sortedMonths.length > 0 && (
                <div className="dashboard-comparison-section">
                    <h3 className="dashboard-section-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{width: 20, height: 20}}>
                            <line x1="18" y1="20" x2="18" y2="10"/>
                            <line x1="12" y1="20" x2="12" y2="4"/>
                            <line x1="6" y1="20" x2="6" y2="14"/>
                        </svg>
                        Comparaison P&L mensuelle
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
                                            className={`comparison-row ${row.bold ? 'bold' : ''} ${row.isTotal ? 'total-row' : ''} ${row.highlight ? 'highlight-row' : ''} ${row.isSubItem ? 'sub-item-row' : ''} section-${row.section}`}
                                        >
                                            <td className="comparison-label">{row.label}</td>
                                            {monthsData.map(m => {
                                                const val = m.resume[row.key];
                                                return (
                                                    <td key={m.key} className={`comparison-value ${val < 0 ? 'negative' : ''}`}>
                                                        {row.isPct ? `${(val || 0).toFixed(3)}%` : fmt(val)}
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
            )}
        </div>
    );
}

export default SageBfcDashboard;
