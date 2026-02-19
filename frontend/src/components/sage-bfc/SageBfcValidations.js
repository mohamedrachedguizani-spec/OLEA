// src/components/sage-bfc/SageBfcValidations.js
import React, { useState, useMemo } from 'react';

function SageBfcValidations({ validations, alertes }) {
    const [expandedValidation, setExpandedValidation] = useState(null);
    const [filterStatus, setFilterStatus] = useState('all');

    const fmt = (val) => {
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(val);
    };

    const getStatusConfig = (statut) => {
        switch (statut) {
            case 'OK':
                return {
                    color: 'success',
                    icon: (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                            <polyline points="22,4 12,14.01 9,11.01"/>
                        </svg>
                    ),
                    label: 'Validé'
                };
            case 'ALERTE':
                return {
                    color: 'danger',
                    icon: (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/>
                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                    ),
                    label: 'Alerte'
                };
            case 'INFO':
                return {
                    color: 'info',
                    icon: (
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="16" x2="12" y2="12"/>
                            <line x1="12" y1="8" x2="12.01" y2="8"/>
                        </svg>
                    ),
                    label: 'Information'
                };
            default:
                return { color: 'neutral', icon: null, label: statut };
        }
    };

    const countByStatut = (statut) => validations.filter(v => v.statut === statut).length;

    const filteredValidations = useMemo(() => {
        if (filterStatus === 'all') return validations;
        return validations.filter(v => v.statut === filterStatus);
    }, [validations, filterStatus]);

    const okCount = countByStatut('OK');
    const alerteCount = countByStatut('ALERTE');
    const infoCount = countByStatut('INFO');
    const totalCount = validations.length;
    const successRate = totalCount > 0 ? Math.round((okCount / totalCount) * 100) : 0;

    return (
        <div className="sage-validations-container">
            {/* Score overview */}
            <div className="val-overview">
                <div className="val-score-card">
                    <div className="val-score-ring">
                        <svg viewBox="0 0 100 100">
                            <circle cx="50" cy="50" r="42" fill="none" stroke="var(--border-light)" strokeWidth="8" />
                            <circle
                                cx="50" cy="50" r="42" fill="none"
                                stroke={successRate >= 80 ? 'var(--success)' : successRate >= 50 ? 'var(--warning)' : 'var(--error)'}
                                strokeWidth="8"
                                strokeLinecap="round"
                                strokeDasharray={`${(successRate / 100) * 264} 264`}
                                transform="rotate(-90 50 50)"
                                className="val-ring-progress"
                            />
                        </svg>
                        <div className="val-score-center">
                            <span className="val-score-value">{successRate}%</span>
                            <span className="val-score-label">Score</span>
                        </div>
                    </div>
                    <div className="val-score-detail">
                        <span className="val-score-title">Taux de conformité</span>
                        <span className="val-score-sub">{okCount} sur {totalCount} validations réussies</span>
                    </div>
                </div>

                <div className="val-stats-row">
                    <button
                        className={`val-stat-chip val-chip-success ${filterStatus === 'OK' ? 'active' : ''}`}
                        onClick={() => setFilterStatus(filterStatus === 'OK' ? 'all' : 'OK')}
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <polyline points="20,6 9,17 4,12"/>
                        </svg>
                        <span className="val-chip-count">{okCount}</span>
                        <span className="val-chip-label">Validées</span>
                    </button>
                    <button
                        className={`val-stat-chip val-chip-danger ${filterStatus === 'ALERTE' ? 'active' : ''}`}
                        onClick={() => setFilterStatus(filterStatus === 'ALERTE' ? 'all' : 'ALERTE')}
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/>
                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                        <span className="val-chip-count">{alerteCount}</span>
                        <span className="val-chip-label">Alertes</span>
                    </button>
                    <button
                        className={`val-stat-chip val-chip-info ${filterStatus === 'INFO' ? 'active' : ''}`}
                        onClick={() => setFilterStatus(filterStatus === 'INFO' ? 'all' : 'INFO')}
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="16" x2="12" y2="12"/>
                            <line x1="12" y1="8" x2="12.01" y2="8"/>
                        </svg>
                        <span className="val-chip-count">{infoCount}</span>
                        <span className="val-chip-label">Informations</span>
                    </button>
                </div>
            </div>

            {/* Alertes globales */}
            {alertes && alertes.length > 0 && (
                <div className="val-global-alerts">
                    <div className="val-global-alerts-header">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/>
                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                        <span>Alertes globales ({alertes.length})</span>
                    </div>
                    <ul className="val-alerts-list">
                        {alertes.map((alerte, idx) => (
                            <li key={idx}>{alerte}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* Liste des validations */}
            {filteredValidations.length > 0 ? (
                <div className="val-cards-list">
                    {filteredValidations.map((validation, idx) => {
                        const config = getStatusConfig(validation.statut);
                        const isExpanded = expandedValidation === idx;
                        const ecartPct = validation.montant_attendu !== 0
                            ? ((validation.ecart / validation.montant_attendu) * 100)
                            : 0;
                        const matchRate = validation.montant_attendu !== 0
                            ? Math.max(0, 100 - Math.abs(ecartPct))
                            : 100;

                        return (
                            <div
                                key={idx}
                                className={`val-card val-card-${config.color} ${isExpanded ? 'expanded' : ''}`}
                            >
                                <button
                                    className="val-card-header"
                                    onClick={() => setExpandedValidation(isExpanded ? null : idx)}
                                >
                                    <div className="val-card-status">{config.icon}</div>
                                    <div className="val-card-main">
                                        <span className="val-card-name">{validation.nom}</span>
                                        <span className={`val-card-badge badge-${config.color}`}>
                                            {config.label}
                                        </span>
                                    </div>
                                    <div className="val-card-preview">
                                        <span className={`val-card-ecart ${Math.abs(validation.ecart) > 0 ? 'has-ecart' : ''}`}>
                                            {fmt(validation.ecart)} TND
                                        </span>
                                    </div>
                                    <svg
                                        viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                                        className={`val-card-chevron ${isExpanded ? 'expanded' : ''}`}
                                    >
                                        <polyline points="6,9 12,15 18,9"/>
                                    </svg>
                                </button>

                                {isExpanded && (
                                    <div className="val-card-body">
                                        {validation.description && (
                                            <p className="val-card-desc">{validation.description}</p>
                                        )}

                                        <div className="val-metrics-grid">
                                            <div className="val-metric">
                                                <span className="val-metric-label">Montant réel</span>
                                                <span className="val-metric-value">{fmt(validation.montant_reel)}</span>
                                                <span className="val-metric-unit">TND</span>
                                            </div>
                                            <div className="val-metric">
                                                <span className="val-metric-label">Montant attendu</span>
                                                <span className="val-metric-value">{fmt(validation.montant_attendu)}</span>
                                                <span className="val-metric-unit">TND</span>
                                            </div>
                                            <div className="val-metric">
                                                <span className="val-metric-label">Écart</span>
                                                <span className={`val-metric-value ${Math.abs(validation.ecart) > 0 ? 'has-ecart' : ''}`}>
                                                    {fmt(validation.ecart)}
                                                </span>
                                                <span className="val-metric-unit">TND</span>
                                            </div>
                                            <div className="val-metric">
                                                <span className="val-metric-label">Conformité</span>
                                                <span className={`val-metric-value ${matchRate >= 95 ? '' : 'has-ecart'}`}>
                                                    {matchRate.toFixed(1)}%
                                                </span>
                                                <div className="val-metric-bar">
                                                    <div
                                                        className="val-metric-bar-fill"
                                                        style={{
                                                            width: `${matchRate}%`,
                                                            background: matchRate >= 95 ? 'var(--success)' : matchRate >= 80 ? 'var(--warning)' : 'var(--error)'
                                                        }}
                                                    />
                                                </div>
                                            </div>
                                        </div>

                                        {/* Horizontal comparison */}
                                        <div className="val-comparison">
                                            <div className="val-comp-row">
                                                <span className="val-comp-label">Réel</span>
                                                <div className="val-comp-bar-track">
                                                    <div
                                                        className="val-comp-bar-fill val-comp-reel"
                                                        style={{
                                                            width: `${Math.min(
                                                                (Math.abs(validation.montant_reel) / Math.max(Math.abs(validation.montant_reel), Math.abs(validation.montant_attendu), 1)) * 100,
                                                                100
                                                            )}%`
                                                        }}
                                                    />
                                                </div>
                                                <span className="val-comp-val">{fmt(validation.montant_reel)}</span>
                                            </div>
                                            <div className="val-comp-row">
                                                <span className="val-comp-label">Attendu</span>
                                                <div className="val-comp-bar-track">
                                                    <div
                                                        className="val-comp-bar-fill val-comp-attendu"
                                                        style={{
                                                            width: `${Math.min(
                                                                (Math.abs(validation.montant_attendu) / Math.max(Math.abs(validation.montant_reel), Math.abs(validation.montant_attendu), 1)) * 100,
                                                                100
                                                            )}%`
                                                        }}
                                                    />
                                                </div>
                                                <span className="val-comp-val">{fmt(validation.montant_attendu)}</span>
                                            </div>
                                        </div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            ) : (
                <div className="val-empty">
                    <div className="val-empty-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                            <polyline points="22,4 12,14.01 9,11.01"/>
                        </svg>
                    </div>
                    <h4>Aucune validation{filterStatus !== 'all' ? ' pour ce filtre' : ''}</h4>
                    <p>
                        {filterStatus !== 'all'
                            ? 'Essayez de modifier le filtre pour voir d\'autres résultats.'
                            : 'Les validations IT Costs et Brand Fees seront exécutées si la configuration le prévoit.'}
                    </p>
                    {filterStatus !== 'all' && (
                        <button className="val-empty-reset" onClick={() => setFilterStatus('all')}>
                            Voir toutes les validations
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}

export default SageBfcValidations;
