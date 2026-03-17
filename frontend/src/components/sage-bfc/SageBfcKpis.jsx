// src/components/sage-bfc/SageBfcKpis.js
import React from 'react';

function SageBfcKpis({ resume, previousResume }) {
    const formatMontant = (montant) => {
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(montant);
    };

    const formatPct = (pct) => {
        return new Intl.NumberFormat('fr-FR', {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
            signDisplay: 'exceptZero'
        }).format(pct);
    };

    const getDelta = (current, previous) => {
        if (!previous || previous === 0) return null;
        return ((current - previous) / Math.abs(previous)) * 100;
    };

    const kpis = [
        {
            label: 'CA Net',
            value: resume.ca_net,
            prevValue: previousResume?.ca_net,
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="12" y1="1" x2="12" y2="23"/>
                    <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                </svg>
            ),
            theme: 'primary',
            badge: null,
            detail: { label: 'Brut', value: formatMontant(resume.ca_brut) },
            detail2: { label: 'Rétro', value: formatMontant(resume.retrocessions) }
        },
        {
            label: 'EBITDA',
            value: resume.ebitda,
            prevValue: previousResume?.ebitda,
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="23,6 13.5,15.5 8.5,10.5 1,18"/>
                    <polyline points="17,6 23,6 23,12"/>
                </svg>
            ),
            theme: resume.ebitda >= 0 ? 'success' : 'danger',
            badge: `${formatPct(resume.ebitda_pct)}%`,
            detail: { label: 'Marge', value: `${formatPct(resume.ebitda_pct)}%` },
            detail2: null
        },
        {
            label: 'Charges Exploitation',
            value: resume.total_charges,
            prevValue: previousResume?.total_charges,
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="23,18 13.5,8.5 8.5,13.5 1,6"/>
                    <polyline points="17,18 23,18 23,12"/>
                </svg>
            ),
            theme: 'warning',
            badge: null,
            detail: { label: 'Produits', value: formatMontant(resume.total_produits) },
            detail2: null
        },
        {
            label: 'Résultat Net',
            value: resume.resultat_net,
            prevValue: previousResume?.resultat_net,
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                    <polyline points="22,4 12,14.01 9,11.01"/>
                </svg>
            ),
            theme: resume.resultat_net >= 0 ? 'success' : 'danger',
            badge: `${formatPct(resume.resultat_net_pct)}%`,
            detail: { label: 'Marge nette', value: `${formatPct(resume.resultat_net_pct)}%` },
            detail2: null
        }
    ];

    return (
        <div className="sage-kpis-grid">
            {kpis.map((kpi, index) => {
                const delta = getDelta(kpi.value, kpi.prevValue);
                return (
                    <div key={index} className={`sage-kpi-card kpi-theme-${kpi.theme}`}>
                        <div className="kpi-header">
                            <span className="kpi-icon-wrap">
                                {kpi.icon}
                            </span>
                            {kpi.badge && (
                                <span className="kpi-badge-pill">
                                    {kpi.badge}
                                </span>
                            )}
                        </div>
                        <div className="kpi-body">
                            <span className={`kpi-value ${kpi.value < 0 ? 'negative' : ''}`}>
                                {formatMontant(kpi.value)}
                            </span>
                            <span className="kpi-unit">TND</span>
                        </div>
                        <div className="kpi-footer">
                            <span className="kpi-label">{kpi.label}</span>
                            {delta != null && (
                                <span className={`kpi-indicator ${delta >= 0 ? 'up' : 'down'}`}>
                                    {delta >= 0 ? '↑' : '↓'} {Math.abs(delta).toFixed(1)}%
                                </span>
                            )}
                        </div>
                        {(kpi.detail || kpi.detail2) && (
                            <div className="kpi-detail-row">
                                {kpi.detail && (
                                    <span className="kpi-detail-item">
                                        <span className="kpi-detail-label">{kpi.detail.label}</span>
                                        <span className="kpi-detail-value">{kpi.detail.value}</span>
                                    </span>
                                )}
                                {kpi.detail2 && (
                                    <span className="kpi-detail-item">
                                        <span className="kpi-detail-label">{kpi.detail2.label}</span>
                                        <span className="kpi-detail-value">{kpi.detail2.value}</span>
                                    </span>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

export default SageBfcKpis;
