// src/components/Dashboard.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import ApiService from '../services/api';

function Dashboard({ refreshTrigger }) {
    const [stats, setStats] = useState({
        solde_actuel: 0,
        total_debit: 0,
        total_credit: 0,
        nombre_ecritures: 0,
        ecritures_migrees: 0,
        ecritures_en_attente: 0,
        evolution: [],
        top_libelles: []
    });
    const [loading, setLoading] = useState(true);
    const [filterType, setFilterType] = useState('month');
    const [dateDebut, setDateDebut] = useState('');
    const [dateFin, setDateFin] = useState('');
    const [lastUpdate, setLastUpdate] = useState(new Date());
    const intervalRef = useRef(null);

    const getDateRange = useCallback(() => {
        const today = new Date();
        let debut = null;
        let fin = today.toISOString().split('T')[0];

        switch (filterType) {
            case 'today':
                debut = fin;
                break;
            case 'week':
                const weekStart = new Date(today);
                weekStart.setDate(today.getDate() - today.getDay() + 1);
                debut = weekStart.toISOString().split('T')[0];
                break;
            case 'month':
                debut = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0];
                break;
            case 'year':
                debut = new Date(today.getFullYear(), 0, 1).toISOString().split('T')[0];
                break;
            case 'custom':
                debut = dateDebut || null;
                fin = dateFin || null;
                break;
            default:
                debut = null;
                fin = null;
        }
        return { debut, fin };
    }, [filterType, dateDebut, dateFin]);

    const loadStats = useCallback(async () => {
        setLoading(true);
        try {
            const { debut, fin } = getDateRange();
            const data = await ApiService.getDashboardStats(debut, fin);
            setStats(data);
            setLastUpdate(new Date());
        } catch (error) {
            console.error('Erreur chargement statistiques:', error);
        } finally {
            setLoading(false);
        }
    }, [getDateRange]);

    // Auto-refresh every 30 seconds
    useEffect(() => {
        loadStats();
        intervalRef.current = setInterval(() => {
            loadStats();
        }, 30000);
        
        return () => {
            if (intervalRef.current) {
                clearInterval(intervalRef.current);
            }
        };
    }, [loadStats, refreshTrigger, filterType]);

    useEffect(() => {
        if (filterType === 'custom' && dateDebut && dateFin) {
            loadStats();
        }
    }, [dateDebut, dateFin, filterType, loadStats]);

    const formatMontant = (montant) => {
        return new Intl.NumberFormat('fr-TN', {
            minimumFractionDigits: 3,
            maximumFractionDigits: 3
        }).format(montant);
    };

    const formatShortMontant = (montant) => {
        if (montant >= 1000000) return (montant / 1000000).toFixed(1) + 'M';
        if (montant >= 1000) return (montant / 1000).toFixed(1) + 'K';
        return montant.toFixed(0);
    };

    const getMaxValue = () => {
        if (!stats.evolution || stats.evolution.length === 0) return 100;
        const max = Math.max(...stats.evolution.map(e => Math.max(e.debit, e.credit)));
        return max || 100;
    };

    const getYAxisTicks = () => {
        const max = getMaxValue();
        const step = max / 4;
        return [0, step, step * 2, step * 3, max];
    };

    const getPeriodLabel = () => {
        const labels = {
            today: "Aujourd'hui",
            week: 'Cette semaine',
            month: 'Ce mois',
            year: 'Cette année',
            custom: 'Période personnalisée',
            all: 'Toutes les périodes'
        };
        return labels[filterType] || 'Période';
    };

    return (
        <div className="dashboard fade-in">
            {/* En-tête du Dashboard */}
            <div className="dashboard-header">
                <div className="dashboard-title">
                    <h2>Tableau de Bord</h2>
                    <div className="dashboard-meta">
                        <span className="period-badge">{getPeriodLabel()}</span>
                        <span className="update-time">
                            Mis à jour: {lastUpdate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                    </div>
                </div>
                <div className="dashboard-filters">
                    <div className="filter-group">
                        {['today', 'week', 'month', 'year', 'all', 'custom'].map(type => (
                            <button
                                key={type}
                                className={`filter-pill ${filterType === type ? 'active' : ''}`}
                                onClick={() => setFilterType(type)}
                            >
                                {type === 'today' && "Jour"}
                                {type === 'week' && 'Semaine'}
                                {type === 'month' && 'Mois'}
                                {type === 'year' && 'Année'}
                                {type === 'all' && 'Tout'}
                                {type === 'custom' && 'Custom'}
                            </button>
                        ))}
                    </div>
                    {filterType === 'custom' && (
                        <div className="date-range">
                            <input type="date" value={dateDebut} onChange={(e) => setDateDebut(e.target.value)} />
                            <span className="date-separator">→</span>
                            <input type="date" value={dateFin} onChange={(e) => setDateFin(e.target.value)} />
                        </div>
                    )}
                </div>
            </div>

            {/* KPI Cards */}
            <div className="kpi-grid">
                <div className={`kpi-card kpi-primary ${loading ? 'shimmer' : ''}`}>
                    <div className="kpi-header">
                        <span className="kpi-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
                            </svg>
                        </span>
                        <span className="kpi-badge">Solde</span>
                    </div>
                    <div className="kpi-body">
                        <span className={`kpi-value ${stats.solde_actuel >= 0 ? 'positive' : 'negative'}`}>
                            {formatMontant(stats.solde_actuel)}
                        </span>
                        <span className="kpi-unit">TND</span>
                    </div>
                    <div className="kpi-footer">
                        <span className={`kpi-indicator ${stats.solde_actuel >= 0 ? 'up' : 'down'}`}>
                            {stats.solde_actuel >= 0 ? '↑' : '↓'} Solde actuel
                        </span>
                    </div>
                </div>

                <div className={`kpi-card kpi-debit ${loading ? 'shimmer' : ''}`}>
                    <div className="kpi-header">
                        <span className="kpi-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M12 19V5M5 12l7-7 7 7"/>
                            </svg>
                        </span>
                        <span className="kpi-badge">Entrées</span>
                    </div>
                    <div className="kpi-body">
                        <span className="kpi-value">{formatMontant(stats.total_debit)}</span>
                        <span className="kpi-unit">TND</span>
                    </div>
                    <div className="kpi-footer">
                        <span className="kpi-label">Total Débit</span>
                    </div>
                </div>

                <div className={`kpi-card kpi-credit ${loading ? 'shimmer' : ''}`}>
                    <div className="kpi-header">
                        <span className="kpi-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M12 5v14M19 12l-7 7-7-7"/>
                            </svg>
                        </span>
                        <span className="kpi-badge">Sorties</span>
                    </div>
                    <div className="kpi-body">
                        <span className="kpi-value">{formatMontant(stats.total_credit)}</span>
                        <span className="kpi-unit">TND</span>
                    </div>
                    <div className="kpi-footer">
                        <span className="kpi-label">Total Crédit</span>
                    </div>
                </div>

                <div className={`kpi-card kpi-count ${loading ? 'shimmer' : ''}`}>
                    <div className="kpi-header">
                        <span className="kpi-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                <polyline points="14,2 14,8 20,8"/>
                                <line x1="16" y1="13" x2="8" y2="13"/>
                                <line x1="16" y1="17" x2="8" y2="17"/>
                            </svg>
                        </span>
                        <span className="kpi-badge">Total</span>
                    </div>
                    <div className="kpi-body">
                        <span className="kpi-value">{stats.nombre_ecritures}</span>
                        <span className="kpi-unit">écritures</span>
                    </div>
                    <div className="kpi-footer">
                        <div className="kpi-breakdown">
                            <span className="migrated">{stats.ecritures_migrees} migrées</span>
                            <span className="pending">{stats.ecritures_en_attente} en attente</span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Charts Section */}
            <div className="charts-grid">
                {/* Left Column - Stacked Charts */}
                <div className="charts-column">
                    {/* Bar Chart with Axes */}
                    <div className="chart-panel chart-panel-compact">
                        <div className="panel-header">
                            <h3>Évolution des Flux Financiers</h3>
                            <div className="chart-legend-inline">
                                <span className="legend-dot debit"></span> Débit
                                <span className="legend-dot credit"></span> Crédit
                            </div>
                        </div>
                        <div className="panel-body panel-body-compact">
                            {stats.evolution && stats.evolution.length > 0 ? (
                                <div className="chart-container chart-container-compact">
                                    {/* Y Axis */}
                                    <div className="y-axis">
                                        <span className="axis-title">Montant (TND)</span>
                                        <div className="y-ticks">
                                            {getYAxisTicks().reverse().map((tick, i) => (
                                                <span key={i} className="tick-label">{formatShortMontant(tick)}</span>
                                            ))}
                                        </div>
                                    </div>
                                    
                                    {/* Chart Area */}
                                    <div className="chart-area">
                                        <div className="grid-lines">
                                            {[0, 1, 2, 3, 4].map(i => (
                                                <div key={i} className="grid-line"></div>
                                            ))}
                                        </div>
                                        <div className="bars-container">
                                            {stats.evolution.map((item, index) => (
                                                <div key={index} className="bar-column">
                                                    <div className="bar-pair">
                                                        <div 
                                                            className="bar bar-debit" 
                                                            style={{ height: `${(item.debit / getMaxValue()) * 100}%` }}
                                                        >
                                                            <span className="bar-tooltip">{formatMontant(item.debit)} TND</span>
                                                        </div>
                                                        <div 
                                                            className="bar bar-credit"
                                                            style={{ height: `${(item.credit / getMaxValue()) * 100}%` }}
                                                        >
                                                            <span className="bar-tooltip">{formatMontant(item.credit)} TND</span>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                        {/* X Axis */}
                                        <div className="x-axis">
                                            {stats.evolution.map((item, index) => (
                                                <span key={index} className="x-label">
                                                    {new Date(item.jour).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' })}
                                                </span>
                                            ))}
                                        </div>
                                        <span className="x-axis-title">Date</span>
                                    </div>
                                </div>
                            ) : (
                                <div className="empty-state">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                        <path d="M3 3v18h18"/>
                                        <path d="M18 9l-5 5-4-4-6 6"/>
                                    </svg>
                                    <p>Aucune donnée disponible pour cette période</p>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Répartition Débit/Crédit - New Visualization */}
                    <div className="chart-panel chart-panel-compact">
                        <div className="panel-header">
                            <h3>Répartition Débit / Crédit</h3>
                            <div className="chart-legend-inline">
                                <span className="legend-dot debit"></span> Entrées
                                <span className="legend-dot credit"></span> Sorties
                            </div>
                        </div>
                        <div className="panel-body panel-body-compact">
                            {(stats.total_debit > 0 || stats.total_credit > 0) ? (
                                <div className="repartition-chart">
                                    <div className="donut-container">
                                        <svg viewBox="0 0 100 100" className="donut-chart">
                                            {/* Background circle */}
                                            <circle
                                                cx="50"
                                                cy="50"
                                                r="40"
                                                fill="none"
                                                stroke="var(--border-light)"
                                                strokeWidth="12"
                                            />
                                            {/* Debit arc */}
                                            <circle
                                                cx="50"
                                                cy="50"
                                                r="40"
                                                fill="none"
                                                stroke="#3b82f6"
                                                strokeWidth="12"
                                                strokeDasharray={`${(stats.total_debit / (stats.total_debit + stats.total_credit)) * 251.2} 251.2`}
                                                strokeDashoffset="0"
                                                transform="rotate(-90 50 50)"
                                                className="donut-segment"
                                            />
                                            {/* Credit arc */}
                                            <circle
                                                cx="50"
                                                cy="50"
                                                r="40"
                                                fill="none"
                                                stroke="#f97316"
                                                strokeWidth="12"
                                                strokeDasharray={`${(stats.total_credit / (stats.total_debit + stats.total_credit)) * 251.2} 251.2`}
                                                strokeDashoffset={`${-(stats.total_debit / (stats.total_debit + stats.total_credit)) * 251.2}`}
                                                transform="rotate(-90 50 50)"
                                                className="donut-segment"
                                            />
                                        </svg>
                                        <div className="donut-center">
                                            <span className="donut-total-label">Total</span>
                                            <span className="donut-total-value">{formatShortMontant(stats.total_debit + stats.total_credit)}</span>
                                            <span className="donut-total-unit">TND</span>
                                        </div>
                                    </div>
                                    <div className="repartition-details">
                                        <div className="repartition-item debit">
                                            <div className="repartition-color"></div>
                                            <div className="repartition-info">
                                                <span className="repartition-label">Entrées (Débit)</span>
                                                <span className="repartition-value">{formatMontant(stats.total_debit)} TND</span>
                                                <span className="repartition-percent">
                                                    {((stats.total_debit / (stats.total_debit + stats.total_credit)) * 100).toFixed(1)}%
                                                </span>
                                            </div>
                                        </div>
                                        <div className="repartition-item credit">
                                            <div className="repartition-color"></div>
                                            <div className="repartition-info">
                                                <span className="repartition-label">Sorties (Crédit)</span>
                                                <span className="repartition-value">{formatMontant(stats.total_credit)} TND</span>
                                                <span className="repartition-percent">
                                                    {((stats.total_credit / (stats.total_debit + stats.total_credit)) * 100).toFixed(1)}%
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="empty-state">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                        <circle cx="12" cy="12" r="10"/>
                                        <path d="M12 6v6l4 2"/>
                                    </svg>
                                    <p>Aucune donnée disponible</p>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Top Libellés Panel */}
                <div className="chart-panel">
                    <div className="panel-header">
                        <h3>Top Libellés</h3>
                    </div>
                    <div className="panel-body">
                        {stats.top_libelles && stats.top_libelles.length > 0 ? (
                            <div className="ranking-list">
                                {stats.top_libelles.map((item, index) => (
                                    <div key={index} className="ranking-item">
                                        <div className="rank-badge">{index + 1}</div>
                                        <div className="rank-content">
                                            <span className="rank-label">{item.libelle}</span>
                                            <div className="rank-bar-container">
                                                <div 
                                                    className="rank-bar"
                                                    style={{ width: `${(item.occurrences / (stats.top_libelles[0]?.occurrences || 1)) * 100}%` }}
                                                ></div>
                                            </div>
                                            <div className="rank-meta">
                                                <span className="count">{item.occurrences}×</span>
                                                <span className="amounts">
                                                    <span className="debit">+{formatShortMontant(item.total_debit)}</span>
                                                    <span className="credit">-{formatShortMontant(item.total_credit)}</span>
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        ) : (
                            <div className="empty-state">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                                    <polyline points="14,2 14,8 20,8"/>
                                </svg>
                                <p>Aucun libellé pour cette période</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Quick Stats */}
            <div className="quick-stats">
                <div className="stat-tile">
                    <div className="tile-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                        </svg>
                    </div>
                    <div className="tile-content">
                        <span className="tile-label">Différence Nette</span>
                        <span className={`tile-value ${(stats.total_debit - stats.total_credit) >= 0 ? 'positive' : 'negative'}`}>
                            {formatMontant(stats.total_debit - stats.total_credit)} TND
                        </span>
                    </div>
                </div>
                <div className="stat-tile">
                    <div className="tile-icon">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10"/>
                            <polyline points="12,6 12,12 16,14"/>
                        </svg>
                    </div>
                    <div className="tile-content">
                        <span className="tile-label">Taux Migration</span>
                        <span className="tile-value">
                            {stats.nombre_ecritures > 0 
                                ? Math.round((stats.ecritures_migrees / stats.nombre_ecritures) * 100) 
                                : 0}%
                        </span>
                    </div>
                </div>
                <div className="stat-tile">
                    <div className="tile-icon refresh-indicator">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M23 4v6h-6"/>
                            <path d="M1 20v-6h6"/>
                            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
                        </svg>
                    </div>
                    <div className="tile-content">
                        <span className="tile-label">Auto-refresh</span>
                        <span className="tile-value">30s</span>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Dashboard;
