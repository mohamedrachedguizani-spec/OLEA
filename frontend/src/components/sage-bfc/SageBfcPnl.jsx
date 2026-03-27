// src/components/sage-bfc/SageBfcPnl.js
import React, { useState, useMemo } from 'react';

// Normalisation pour données stockées avant la migration du mapping
const AGREGAT_ALIASES = {
    'Brand Fees': 'Honoraires & Sous-traitance',
    'Management Fees': 'Honoraires & Sous-traitance'
};

function SageBfcPnl({ resume, previousResume, lignes = [] }) {
    const [expandedSections, setExpandedSections] = useState({
        produits: true,
        charges: true,
        financier: false,
        resultat: true
    });
    const [expandedAgregat, setExpandedAgregat] = useState(null);

    const toggleSection = (section) => {
        setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
    };

    const toggleAgregat = (agregat) => {
        setExpandedAgregat(prev => prev === agregat ? null : agregat);
    };

    const fmt = (val) => {
        if (val == null) return '—';
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3
        }).format(val);
    };

    const fmtPct = (val) => {
        if (val == null) return '—';
        return new Intl.NumberFormat('fr-FR', {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3
        }).format(val);
    };

    const getDelta = (currentVal, prevVal) => {
        if (prevVal == null || prevVal === 0) return null;
        return ((currentVal - prevVal) / Math.abs(prevVal)) * 100;
    };

    // Grouper les lignes par agrégat pour le détail des codes
    // AGREGAT_ALIASES est défini au niveau module pour compatibilité anciennes données
    const lignesByAgregat = useMemo(() => {
        const map = {};
        lignes.forEach(l => {
            const key = AGREGAT_ALIASES[l.agregat_bfc] || l.agregat_bfc;
            if (!map[key]) map[key] = [];
            map[key].push(l);
        });
        return map;
    }, [lignes]);

    // Compatibilité rétro : avant la migration, honoraires ne contenait pas brand_fees/management_fees.
    // Détecter les anciennes données via les lignes (agrégat 'Brand Fees' ou 'Management Fees' encore présent).
    const hasLegacyAgregats = useMemo(
        () => lignes.some(l => l.agregat_bfc === 'Brand Fees' || l.agregat_bfc === 'Management Fees'),
        [lignes]
    );
    const effectiveHonoraires = r => r
        ? hasLegacyAgregats
            ? (r.honoraires || 0) + (r.brand_fees || 0) + (r.management_fees || 0)
            : (r.honoraires || 0)
        : 0;

    const pnlSections = [
        {
            key: 'produits',
            title: 'PRODUITS D\'EXPLOITATION',
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="23,6 13.5,15.5 8.5,10.5 1,18"/>
                    <polyline points="17,6 23,6 23,12"/>
                </svg>
            ),
            color: 'green',
            lines: [
                { label: 'Chiffre d\'Affaires Brut', value: resume.ca_brut, prevValue: previousResume?.ca_brut, agregat: 'CA Brut' },
                { label: 'Rétrocessions', value: -resume.retrocessions, prevValue: previousResume ? -previousResume.retrocessions : null, agregat: 'Retrocessions' },
                { label: 'Chiffre d\'Affaires Net', value: resume.ca_net, prevValue: previousResume?.ca_net, bold: true, isSubtotal: true },
                { label: 'Autres Produits d\'Exploitation', value: resume.autres_produits, prevValue: previousResume?.autres_produits, agregat: 'Autres Produits d\'Exploitation' },
                { label: 'TOTAL PRODUITS', value: resume.total_produits, prevValue: previousResume?.total_produits, bold: true, isTotal: true }
            ]
        },
        {
            key: 'charges',
            title: 'CHARGES D\'EXPLOITATION',
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="23,18 13.5,8.5 8.5,13.5 1,6"/>
                    <polyline points="17,18 23,18 23,12"/>
                </svg>
            ),
            color: 'red',
            lines: [
                { label: 'Frais de Personnel', value: resume.frais_personnel, prevValue: previousResume?.frais_personnel, agregat: 'Frais de Personnel' },
                { label: 'Honoraires & Sous-traitance', value: effectiveHonoraires(resume), prevValue: effectiveHonoraires(previousResume), agregat: 'Honoraires & Sous-traitance' },
                { label: 'Frais Commerciaux', value: resume.frais_commerciaux, prevValue: previousResume?.frais_commerciaux, agregat: 'Frais Commerciaux' },
                { label: 'Impôts et Taxes', value: resume.impots_taxes, prevValue: previousResume?.impots_taxes, agregat: 'Impôts et taxes' },
                { label: 'Fonctionnement Courant', value: resume.fonctionnement, prevValue: previousResume?.fonctionnement, agregat: 'Fonctionnement Courant' },
                { label: 'Autres Charges', value: resume.autres_charges, prevValue: previousResume?.autres_charges, agregat: 'Autres Charges' },
                { label: 'TOTAL CHARGES', value: resume.total_charges, prevValue: previousResume?.total_charges, bold: true, isTotal: true }
            ]
        },
        {
            key: 'financier',
            title: 'RÉSULTAT FINANCIER',
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>
                    <line x1="8" y1="21" x2="16" y2="21"/>
                    <line x1="12" y1="17" x2="12" y2="21"/>
                </svg>
            ),
            color: 'blue',
            lines: [
                { label: 'Produits Financiers', value: resume.produits_financiers, prevValue: previousResume?.produits_financiers, agregat: 'Produits Financiers' },
                { label: 'Charges Financières', value: resume.charges_financieres, prevValue: previousResume?.charges_financieres, agregat: 'Charges Financières' },
                { label: 'Résultat Financier', value: resume.resultat_financier, prevValue: previousResume?.resultat_financier, bold: true, isSubtotal: true },
                { label: 'Dotations Amort. & Provisions', value: resume.dotations, prevValue: previousResume?.dotations, agregat: 'Dotations Amortissements & Provisions' }
            ]
        },
        {
            key: 'resultat',
            title: 'RÉSULTAT',
            icon: (
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                    <polyline points="22,4 12,14.01 9,11.01"/>
                </svg>
            ),
            color: 'purple',
            lines: [
                { label: 'Résultat avant Impôt', value: resume.resultat_avant_impot, prevValue: previousResume?.resultat_avant_impot, bold: true },
                { label: 'Impôt sur les Sociétés', value: resume.impot_societes, prevValue: previousResume?.impot_societes, agregat: 'Impôt sur les sociétés' },
                { label: 'RÉSULTAT NET', value: resume.resultat_net, prevValue: previousResume?.resultat_net, bold: true, isTotal: true }
            ]
        }
    ];

    const hasPrevious = !!previousResume;

    // Compute ratio of charges vs produits for visual gauge
    const chargesRatio = resume.total_produits > 0 ? (resume.total_charges / resume.total_produits) * 100 : 0;

    return (
        <div className="sage-pnl-container">
            {/* EBITDA & RN Hero Cards */}
            <div className="pnl-hero-grid pnl-hero-grid-2">
                <div className={`pnl-hero-card ${resume.ebitda >= 0 ? 'hero-positive' : 'hero-negative'}`}>
                    <div className="hero-icon-wrap">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
                        </svg>
                    </div>
                    <div className="hero-content">
                        <span className="hero-label">EBITDA</span>
                        <span className="hero-value">{fmt(resume.ebitda)} <small>TND</small></span>
                        <div className="hero-meta">
                            <span className="hero-pct">{fmtPct(resume.ebitda_pct)}% du CA Net</span>
                            {hasPrevious && (
                                <span className={`hero-delta ${resume.ebitda >= previousResume.ebitda ? 'up' : 'down'}`}>
                                    {resume.ebitda >= previousResume.ebitda ? '↑' : '↓'} {fmt(Math.abs(resume.ebitda - previousResume.ebitda))}
                                </span>
                            )}
                        </div>
                    </div>
                    <div className="hero-gauge">
                        <div className="hero-gauge-track">
                            <div className="hero-gauge-fill" style={{ width: `${Math.min(Math.abs(resume.ebitda_pct), 100)}%` }} />
                        </div>
                    </div>
                </div>

                <div className={`pnl-hero-card ${resume.resultat_net >= 0 ? 'hero-positive' : 'hero-negative'}`}>
                    <div className="hero-icon-wrap">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                            <polyline points="22,4 12,14.01 9,11.01"/>
                        </svg>
                    </div>
                    <div className="hero-content">
                        <span className="hero-label">Résultat Net</span>
                        <span className="hero-value">{fmt(resume.resultat_net)} <small>TND</small></span>
                        <div className="hero-meta">
                            <span className="hero-pct">Marge: {fmtPct(resume.resultat_net_pct)}%  ·  Ratio C/P: {chargesRatio.toFixed(3)}%</span>
                            {hasPrevious && (
                                <span className={`hero-delta ${resume.resultat_net >= previousResume.resultat_net ? 'up' : 'down'}`}>
                                    {resume.resultat_net >= previousResume.resultat_net ? '↑' : '↓'} {fmt(Math.abs(resume.resultat_net - previousResume.resultat_net))}
                                </span>
                            )}
                        </div>
                    </div>
                    <div className="hero-gauge">
                        <div className="hero-gauge-track">
                            <div className="hero-gauge-fill" style={{ width: `${Math.min(Math.abs(resume.resultat_net_pct), 100)}%` }} />
                        </div>
                    </div>
                </div>
            </div>

            {/* P&L Table Header */}
            {hasPrevious && (
                <div className="pnl-table-header">
                    <span className="pnl-th-label">Poste</span>
                    <span className="pnl-th-value">Mois courant</span>
                    <span className="pnl-th-value">Mois précédent</span>
                    <span className="pnl-th-delta">Δ Variation</span>
                </div>
            )}

            {/* P&L Sections */}
            <div className="pnl-sections">
                {pnlSections.map((section) => (
                    <div key={section.key} className={`pnl-section pnl-section-${section.color}`}>
                        <button
                            className="pnl-section-header"
                            onClick={() => toggleSection(section.key)}
                        >
                            <span className="pnl-section-icon">{section.icon}</span>
                            <span className="pnl-section-title">{section.title}</span>
                            <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="2"
                                className={`pnl-section-chevron ${expandedSections[section.key] ? 'expanded' : ''}`}
                            >
                                <polyline points="6,9 12,15 18,9"/>
                            </svg>
                        </button>

                        {expandedSections[section.key] && (
                            <div className="pnl-section-body">
                                {section.lines.map((line, idx) => {
                                    const delta = hasPrevious && line.prevValue != null
                                        ? getDelta(line.value, line.prevValue)
                                        : null;
                                    const agregat = line.agregat;
                                    const isExpanded = agregat && expandedAgregat === agregat;
                                    const detailLignes = agregat ? (lignesByAgregat[agregat] || []) : [];
                                    const hasDetail = detailLignes.length > 0;

                                    return (
                                        <React.Fragment key={idx}>
                                            {/* Ligne principale de l'agrégat */}
                                            <div
                                                className={`pnl-row ${line.bold ? 'bold' : ''} ${line.isTotal ? 'total-row' : ''} ${line.isSubtotal ? 'subtotal-row' : ''} ${hasPrevious ? 'with-comparison' : ''} ${hasDetail ? 'pnl-row-clickable' : ''} ${isExpanded ? 'pnl-row-expanded' : ''}`}
                                                onClick={() => hasDetail && toggleAgregat(agregat)}
                                            >
                                                <span className="pnl-label">
                                                    {line.isTotal && <span className="pnl-total-marker" />}
                                                    {line.label}
                                                    {hasDetail && (
                                                        <span className="pnl-expand-icon">
                                                            {isExpanded ? '▾' : '▸'}
                                                        </span>
                                                    )}
                                                </span>
                                                <span className={`pnl-value ${line.value < 0 ? 'negative' : ''}`}>
                                                    {fmt(line.value)}
                                                </span>
                                                {hasPrevious && (
                                                    <>
                                                        <span className={`pnl-value pnl-prev-value ${line.prevValue < 0 ? 'negative' : ''}`}>
                                                            {fmt(line.prevValue)}
                                                        </span>
                                                        <span className={`pnl-delta ${delta > 0 ? 'delta-up' : delta < 0 ? 'delta-down' : ''}`}>
                                                            {delta != null ? (
                                                                <>
                                                                    <span className="pnl-delta-arrow">{delta > 0 ? '↑' : '↓'}</span>
                                                                    {Math.abs(delta).toFixed(3)}%
                                                                </>
                                                            ) : '—'}
                                                        </span>
                                                    </>
                                                )}
                                            </div>

                                            {/* Détail des codes comptables (affiché au clic) */}
                                            {isExpanded && detailLignes.length > 0 && (
                                                <div className="pnl-detail-codes">
                                                    <div className="pnl-detail-codes-header">
                                                        <span>Code</span>
                                                        <span className="pnl-detail-libelle-col">Libellé</span>
                                                        <span>Montant (TND)</span>
                                                    </div>
                                                    {detailLignes.map((l, di) => (
                                                        <div key={di} className="pnl-detail-code-row">
                                                            <span className="pnl-detail-code">{l.code_sage}</span>
                                                            <span className="pnl-detail-libelle">{l.libelle_sage}</span>
                                                            <span className="pnl-detail-amount">{fmt(l.montant_absolu)}</span>
                                                        </div>
                                                    ))}
                                                    <div className="pnl-detail-code-row pnl-detail-total">
                                                        <span className="pnl-detail-code"></span>
                                                        <span className="pnl-detail-libelle">Total {line.label}</span>
                                                        <span className="pnl-detail-amount pnl-detail-amount-total">
                                                            {fmt(detailLignes.reduce((s, l) => s + parseFloat(l.montant_absolu || 0), 0))}
                                                        </span>
                                                    </div>
                                                </div>
                                            )}
                                        </React.Fragment>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
}

export default SageBfcPnl;
