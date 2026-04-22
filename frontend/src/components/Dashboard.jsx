// src/components/Dashboard.jsx
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
    AreaChart, Area,
    BarChart, Bar,
    LineChart, Line,
    PieChart, Pie, Cell,
    ComposedChart,
    XAxis, YAxis, CartesianGrid, Tooltip, Legend,
    ResponsiveContainer,
} from 'recharts';
import ApiService, { API_BASE_URL } from '../services/api';

// ─── WebSocket URL ───
const WS_URL = API_BASE_URL.replace(/^http/i, 'ws') + '/ws/live';
const WS_RECONNECT_DELAY = 3000;

// ─── Section definitions ───
const SECTIONS = [
    { id: 'overview',   label: 'Vue d\'ensemble', icon: '🏠', desc: 'Résumé global',       badgeKey: null,       accent: '#d4a528' },
    { id: 'tresorerie', label: 'Trésorerie',      icon: '💰', desc: 'Flux & solde caisse', badgeKey: 'ecritures', accent: '#b7482b' },
    { id: 'bfc',        label: 'Analyse BFC',     icon: '📊', desc: 'Résultat financier',  badgeKey: 'periodes',  accent: '#2f343a' },
];

// ─── Couleurs thématiques ───
const COLORS = {
    primary: '#b7482b',
    primaryLight: '#cd7458',
    debit: '#d4a528',
    debitLight: '#f5d26d',
    credit: '#b7482b',
    creditLight: '#dc9880',
    purple: '#2f343a',
    success: '#8f7b2d',
    danger: '#863421',
    neutral: '#7a838d',
    bg: '#f7f7f5',
};

const PIE_COLORS = ['#d4a528', '#b7482b', '#2f343a', '#cd7458', '#f5d26d', '#8f7b2d', '#7a838d'];

// ─── Formatters ───
const fmtMontant = (v) =>
    new Intl.NumberFormat('fr-TN', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(v);

const fmtShort = (v) => {
    if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(3) + 'M';
    if (Math.abs(v) >= 1_000) return (v / 1_000).toFixed(3) + 'K';
    return v.toFixed(3);
};

const fmtDate = (d) => {
    const dt = new Date(d);
    return dt.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
};

// ─── Custom Tooltip ───
function CustomTooltip({ active, payload, label, formatter }) {
    if (!active || !payload?.length) return null;
    return (
        <div className="gd-tooltip">
            <p className="gd-tooltip-label">{label}</p>
            {payload.map((p, i) => (
                <div key={i} className="gd-tooltip-row">
                    <span className="gd-tooltip-dot" style={{ background: p.color }} />
                    <span className="gd-tooltip-name">{p.name}</span>
                    <span className="gd-tooltip-val">
                        {formatter ? formatter(p.value) : fmtMontant(p.value)} {!formatter && 'TND'}
                    </span>
                </div>
            ))}
        </div>
    );
}

// ─── Section wrapper réutilisable ───
function Section({ title, subtitle, icon, children, className = '' }) {
    return (
        <div className={`gd-section ${className}`}>
            <div className="gd-section-header">
                <div className="gd-section-title-group">
                    {icon && <span className="gd-section-icon">{icon}</span>}
                    <div>
                        <h3 className="gd-section-title">{title}</h3>
                        {subtitle && <span className="gd-section-subtitle">{subtitle}</span>}
                    </div>
                </div>
            </div>
            <div className="gd-section-body">{children}</div>
        </div>
    );
}

// ═══════════════════════════════════════════════════════════
// COMPOSANT PRINCIPAL
// ═══════════════════════════════════════════════════════════

function Dashboard({ refreshTrigger }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [filterType, setFilterType] = useState('month');
    const [dateDebut, setDateDebut] = useState('');
    const [dateFin, setDateFin] = useState('');
    const [lastUpdate, setLastUpdate] = useState(new Date());
    const [activeSection, setActiveSection] = useState('overview');
    const [wsConnected, setWsConnected] = useState(false);

    // ── WebSocket temps réel ──
    const wsRef = useRef(null);
    const reconnectTimer = useRef(null);
    const loadDataRef = useRef(null);

    // ── Période ──
    const getDateRange = useCallback(() => {
        const today = new Date();
        let debut = null, fin = today.toISOString().split('T')[0];
        switch (filterType) {
            case 'today':
                debut = fin; break;
            case 'week':
                const w = new Date(today);
                w.setDate(today.getDate() - today.getDay() + 1);
                debut = w.toISOString().split('T')[0]; break;
            case 'month':
                debut = new Date(today.getFullYear(), today.getMonth(), 1).toISOString().split('T')[0]; break;
            case 'year':
                debut = new Date(today.getFullYear(), 0, 1).toISOString().split('T')[0]; break;
            case 'custom':
                debut = dateDebut || null;
                fin = dateFin || null; break;
            default:
                debut = null; fin = null;
        }
        return { debut, fin };
    }, [filterType, dateDebut, dateFin]);

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const { debut, fin } = getDateRange();
            const res = await ApiService.getGlobalDashboard(debut, fin);
            setData(res);
            setLastUpdate(new Date());
        } catch (err) {
            console.error('Erreur chargement dashboard global:', err);
        } finally {
            setLoading(false);
        }
    }, [getDateRange]);

    // Keep loadDataRef in sync so the WebSocket callback always calls the latest version
    useEffect(() => { loadDataRef.current = loadData; }, [loadData]);

    // ── WebSocket connection ──
    const connectWs = useCallback(() => {
        if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log('[Dashboard WS] ✅ Connecté');
            setWsConnected(true);
        };

        ws.onmessage = (event) => {
            try {
                const { channel } = JSON.parse(event.data);
                // Reload the dashboard when any relevant channel fires
                if (['caisse', 'migration', 'sage_bfc'].includes(channel)) {
                    console.log(`[Dashboard WS] 📡 Refresh → ${channel}`);
                    loadDataRef.current?.();
                }
            } catch (err) {
                console.warn('[Dashboard WS] Message invalide:', err);
            }
        };

        ws.onclose = (event) => {
            console.log('[Dashboard WS] 🔌 Déconnecté — reconnexion…');
            setWsConnected(false);
            wsRef.current = null;
            if (event?.code === 1008) {
                return;
            }
            reconnectTimer.current = setTimeout(connectWs, WS_RECONNECT_DELAY);
        };

        ws.onerror = () => { /* onclose sera appelé */ };

        wsRef.current = ws;
    }, []);

    // Connect WebSocket on mount, cleanup on unmount
    useEffect(() => {
        connectWs();
        return () => {
            clearTimeout(reconnectTimer.current);
            if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
        };
    }, [connectWs]);

    // Initial load + reload on filter/trigger change
    useEffect(() => { loadData(); }, [loadData, refreshTrigger, filterType]);

    useEffect(() => {
        if (filterType === 'custom' && dateDebut && dateFin) loadData();
    }, [dateDebut, dateFin, filterType, loadData]);

    // ── Derived data ──
    const caisse = data?.caisse;
    const migration = data?.migration;
    const bfc = data?.bfc;

    const tauxMigration = useMemo(() => {
        if (!caisse || caisse.nombre_ecritures === 0) return 0;
        return Math.round((caisse.ecritures_migrees / caisse.nombre_ecritures) * 100);
    }, [caisse]);

    // ── Pie data ──
    const pieData = useMemo(() => {
        if (!caisse) return [];
        return [
            { name: 'Débit (Entrées)', value: caisse.total_debit },
            { name: 'Crédit (Sorties)', value: caisse.total_credit },
        ].filter(d => d.value > 0);
    }, [caisse]);

    const periodLabels = {
        today: "Aujourd'hui", week: 'Cette semaine', month: 'Ce mois',
        year: 'Cette année', custom: 'Personnalisé', all: 'Toutes périodes'
    };

    if (loading && !data) {
        return (
            <div className="gd-loading">
                <div className="gd-loading-spinner" />
                <p>Chargement du tableau de bord…</p>
            </div>
        );
    }

    return (
        <div className="gd-dashboard fade-in">
            {/* ══════ HEADER ══════ */}
            <div className="gd-header">
                <div className="gd-header-left">
                    <h2 className="gd-main-title">Tableau de Bord Global</h2>
                    <div className="gd-header-meta">
                        <span className="gd-period-badge">{periodLabels[filterType]}</span>
                        <span className={`gd-ws-badge ${wsConnected ? 'connected' : 'disconnected'}`}>
                            <span className="gd-ws-dot" />
                            {wsConnected ? 'Temps réel' : 'Hors ligne'}
                        </span>
                        <span className="gd-update-time">
                            Mis à jour : {lastUpdate.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                    </div>
                </div>
                <div className="gd-header-right">
                    <div className="gd-filter-group">
                        {['today', 'week', 'month', 'year', 'all', 'custom'].map(t => (
                            <button key={t} className={`gd-filter-pill ${filterType === t ? 'active' : ''}`}
                                onClick={() => setFilterType(t)}>
                                {{ today: 'Jour', week: 'Semaine', month: 'Mois', year: 'Année', all: 'Tout', custom: 'Custom' }[t]}
                            </button>
                        ))}
                    </div>
                    {filterType === 'custom' && (
                        <div className="gd-date-range">
                            <input type="date" value={dateDebut} onChange={e => setDateDebut(e.target.value)} />
                            <span>→</span>
                            <input type="date" value={dateFin} onChange={e => setDateFin(e.target.value)} />
                        </div>
                    )}
                </div>
            </div>

            {/* ══════ SECTION NAV ══════ */}
            <div className="gd-section-nav">
                {SECTIONS.map(s => {
                    const badge = s.badgeKey === 'ecritures' ? (caisse?.nombre_ecritures || 0)
                                : s.badgeKey === 'pieces'    ? (migration?.nb_pieces || 0)
                                : s.badgeKey === 'periodes'  ? (bfc?.nb_periodes || 0)
                                : null;
                    const isActive = activeSection === s.id;
                    return (
                        <button key={s.id}
                            className={`gd-snav-card ${isActive ? 'active' : ''}`}
                            onClick={() => setActiveSection(s.id)}
                            style={{ '--snav-accent': s.accent }}>
                            <div className="gd-snav-icon-wrap">
                                <span className="gd-snav-icon">{s.icon}</span>
                            </div>
                            <div className="gd-snav-body">
                                <span className="gd-snav-label">{s.label}</span>
                                <span className="gd-snav-desc">{s.desc}</span>
                            </div>
                            {badge !== null && (
                                <span className="gd-snav-badge">{badge}</span>
                            )}
                            {isActive && <span className="gd-snav-indicator" />}
                        </button>
                    );
                })}
            </div>

            {/* ══════ SECTION: VUE D'ENSEMBLE ══════ */}
            {(activeSection === 'overview') && (
                <>
                    {/* KPI GLOBAUX */}
                    <div className="gd-kpi-row">
                        <KpiCard icon="💰" label="Solde Caisse" color="primary"
                            value={fmtMontant(caisse?.solde_actuel || 0)} unit="TND"
                            trend={caisse?.solde_actuel >= 0 ? 'up' : 'down'}
                            trendLabel={caisse?.solde_actuel >= 0 ? 'Positif' : 'Négatif'} loading={loading} />
                        <KpiCard icon="📥" label="Total Entrées" color="debit"
                            value={fmtMontant(caisse?.total_debit || 0)} unit="TND"
                            sub={`${caisse?.nombre_ecritures || 0} écritures`} loading={loading} />
                        <KpiCard icon="📤" label="Total Sorties" color="credit"
                            value={fmtMontant(caisse?.total_credit || 0)} unit="TND" loading={loading} />
                        <KpiCard icon="🔄" label="Taux Migration" color="purple"
                            value={`${tauxMigration}%`}
                            sub={`${caisse?.ecritures_migrees || 0} / ${caisse?.nombre_ecritures || 0}`} loading={loading} />
                        <KpiCard icon="⚖️" label="Balance Sage" color={migration?.equilibre ? 'success' : 'danger'}
                            value={migration?.equilibre ? 'Équilibrée' : 'Déséquilibrée'}
                            sub={`${migration?.nb_pieces || 0} pièces`} loading={loading} />
                        <KpiCard icon="📊" label="Périodes BFC" color="neutral"
                            value={bfc?.nb_periodes || 0}
                            sub={bfc?.derniere_periode ? `Dernier : ${bfc.derniere_periode}` : 'Aucune donnée'} loading={loading} />
                    </div>

                    {/* Résumé rapide — Flux + Répartition */}
                    <div className="gd-row-2col">
                        <Section title="Flux de Trésorerie" subtitle="Évolution journalière" icon="📈" className="gd-col-large">
                            {caisse?.evolution?.length > 0 ? (
                                <ResponsiveContainer width="100%" height={280}>
                                    <ComposedChart data={caisse.evolution} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                        <defs>
                                            <linearGradient id="gradDebit" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor={COLORS.debit} stopOpacity={0.3} />
                                                <stop offset="95%" stopColor={COLORS.debit} stopOpacity={0} />
                                            </linearGradient>
                                            <linearGradient id="gradCredit" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor={COLORS.credit} stopOpacity={0.3} />
                                                <stop offset="95%" stopColor={COLORS.credit} stopOpacity={0} />
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                        <XAxis dataKey="jour" tickFormatter={fmtDate} fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                        <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={55} />
                                        <Tooltip content={<CustomTooltip />} />
                                        <Legend wrapperStyle={{ fontSize: 12 }} />
                                        <Area type="monotone" dataKey="debit" name="Débit" stroke={COLORS.debit} fill="url(#gradDebit)" strokeWidth={2} />
                                        <Area type="monotone" dataKey="credit" name="Crédit" stroke={COLORS.credit} fill="url(#gradCredit)" strokeWidth={2} />
                                        <Line type="monotone" dataKey="solde_cumul" name="Solde cumulé" stroke={COLORS.primary} strokeWidth={2.5} dot={false} strokeDasharray="6 3" />
                                    </ComposedChart>
                                </ResponsiveContainer>
                            ) : <EmptyChart message="Aucune écriture sur cette période" />}
                        </Section>

                        <Section title="Répartition" subtitle="Entrées vs Sorties" icon="🍩" className="gd-col-small">
                            {pieData.length > 0 ? (
                                <div className="gd-pie-wrap">
                                    <ResponsiveContainer width="100%" height={200}>
                                        <PieChart>
                                            <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={80}
                                                paddingAngle={4} dataKey="value" strokeWidth={0}>
                                                <Cell fill={COLORS.debit} />
                                                <Cell fill={COLORS.credit} />
                                            </Pie>
                                            <Tooltip formatter={(v) => `${fmtMontant(v)} TND`} />
                                        </PieChart>
                                    </ResponsiveContainer>
                                    <div className="gd-pie-legend">
                                        <div className="gd-pie-item">
                                            <span className="gd-pie-dot" style={{ background: COLORS.debit }} />
                                            <div>
                                                <span className="gd-pie-lbl">Entrées</span>
                                                <span className="gd-pie-val">{fmtMontant(caisse.total_debit)} TND</span>
                                                <span className="gd-pie-pct">
                                                    {((caisse.total_debit / (caisse.total_debit + caisse.total_credit)) * 100).toFixed(3)}%
                                                </span>
                                            </div>
                                        </div>
                                        <div className="gd-pie-item">
                                            <span className="gd-pie-dot" style={{ background: COLORS.credit }} />
                                            <div>
                                                <span className="gd-pie-lbl">Sorties</span>
                                                <span className="gd-pie-val">{fmtMontant(caisse.total_credit)} TND</span>
                                                <span className="gd-pie-pct">
                                                    {((caisse.total_credit / (caisse.total_debit + caisse.total_credit)) * 100).toFixed(3)}%
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : <EmptyChart message="Aucune donnée" />}
                        </Section>
                    </div>
                </>
            )}

            {/* ══════ SECTION: TRÉSORERIE ══════ */}
            {(activeSection === 'tresorerie') && (
                <>
                    {/* KPIs Caisse */}
                    <div className="gd-kpi-row gd-kpi-row-4">
                        <KpiCard icon="💰" label="Solde Caisse" color="primary"
                            value={fmtMontant(caisse?.solde_actuel || 0)} unit="TND"
                            trend={caisse?.solde_actuel >= 0 ? 'up' : 'down'}
                            trendLabel={caisse?.solde_actuel >= 0 ? 'Positif' : 'Négatif'} loading={loading} />
                        <KpiCard icon="📥" label="Total Entrées" color="debit"
                            value={fmtMontant(caisse?.total_debit || 0)} unit="TND"
                            sub={`${caisse?.nombre_ecritures || 0} écritures`} loading={loading} />
                        <KpiCard icon="📤" label="Total Sorties" color="credit"
                            value={fmtMontant(caisse?.total_credit || 0)} unit="TND" loading={loading} />
                        <KpiCard icon="💹" label="Différence Nette" color={((caisse?.total_debit || 0) - (caisse?.total_credit || 0)) >= 0 ? 'success' : 'danger'}
                            value={fmtMontant((caisse?.total_debit || 0) - (caisse?.total_credit || 0))} unit="TND" loading={loading} />
                    </div>

                    {/* Flux Area Chart — full width */}
                    <Section title="Flux de Trésorerie" subtitle="Évolution journalière avec solde cumulé" icon="📈">
                        {caisse?.evolution?.length > 0 ? (
                            <ResponsiveContainer width="100%" height={320}>
                                <ComposedChart data={caisse.evolution} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                    <defs>
                                        <linearGradient id="gradDebit2" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor={COLORS.debit} stopOpacity={0.3} />
                                            <stop offset="95%" stopColor={COLORS.debit} stopOpacity={0} />
                                        </linearGradient>
                                        <linearGradient id="gradCredit2" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor={COLORS.credit} stopOpacity={0.3} />
                                            <stop offset="95%" stopColor={COLORS.credit} stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                    <XAxis dataKey="jour" tickFormatter={fmtDate} fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                    <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={55} />
                                    <Tooltip content={<CustomTooltip />} />
                                    <Legend wrapperStyle={{ fontSize: 12 }} />
                                    <Area type="monotone" dataKey="debit" name="Débit" stroke={COLORS.debit} fill="url(#gradDebit2)" strokeWidth={2} />
                                    <Area type="monotone" dataKey="credit" name="Crédit" stroke={COLORS.credit} fill="url(#gradCredit2)" strokeWidth={2} />
                                    <Line type="monotone" dataKey="solde_cumul" name="Solde cumulé" stroke={COLORS.primary} strokeWidth={2.5} dot={false} strokeDasharray="6 3" />
                                </ComposedChart>
                            </ResponsiveContainer>
                        ) : <EmptyChart message="Aucune écriture sur cette période" />}
                    </Section>

                    {/* Top libellés + Répartition */}
                    <div className="gd-row-2col">
                        <Section title="Top Libellés" subtitle="Par volume d'opérations" icon="🏷️" className="gd-col-large">
                            {caisse?.top_libelles?.length > 0 ? (
                                <ResponsiveContainer width="100%" height={280}>
                                    <BarChart data={caisse.top_libelles} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" horizontal={false} />
                                        <XAxis type="number" tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                        <YAxis dataKey="libelle" type="category" width={120} fontSize={11}
                                            tick={{ fill: 'var(--text-primary)' }}
                                            tickFormatter={(v) => v.length > 18 ? v.slice(0, 18) + '…' : v} />
                                        <Tooltip content={<CustomTooltip />} />
                                        <Legend wrapperStyle={{ fontSize: 12 }} />
                                        <Bar dataKey="total_debit" name="Débit" fill={COLORS.debit} radius={[0, 4, 4, 0]} barSize={14} />
                                        <Bar dataKey="total_credit" name="Crédit" fill={COLORS.credit} radius={[0, 4, 4, 0]} barSize={14} />
                                    </BarChart>
                                </ResponsiveContainer>
                            ) : <EmptyChart message="Aucun libellé pour cette période" />}
                        </Section>

                        <Section title="Répartition" subtitle="Entrées vs Sorties" icon="🍩" className="gd-col-small">
                            {pieData.length > 0 ? (
                                <div className="gd-pie-wrap">
                                    <ResponsiveContainer width="100%" height={200}>
                                        <PieChart>
                                            <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={80}
                                                paddingAngle={4} dataKey="value" strokeWidth={0}>
                                                <Cell fill={COLORS.debit} />
                                                <Cell fill={COLORS.credit} />
                                            </Pie>
                                            <Tooltip formatter={(v) => `${fmtMontant(v)} TND`} />
                                        </PieChart>
                                    </ResponsiveContainer>
                                    <div className="gd-pie-legend">
                                        <div className="gd-pie-item">
                                            <span className="gd-pie-dot" style={{ background: COLORS.debit }} />
                                            <div>
                                                <span className="gd-pie-lbl">Entrées</span>
                                                <span className="gd-pie-val">{fmtMontant(caisse.total_debit)} TND</span>
                                                <span className="gd-pie-pct">
                                                    {((caisse.total_debit / (caisse.total_debit + caisse.total_credit)) * 100).toFixed(3)}%
                                                </span>
                                            </div>
                                        </div>
                                        <div className="gd-pie-item">
                                            <span className="gd-pie-dot" style={{ background: COLORS.credit }} />
                                            <div>
                                                <span className="gd-pie-lbl">Sorties</span>
                                                <span className="gd-pie-val">{fmtMontant(caisse.total_credit)} TND</span>
                                                <span className="gd-pie-pct">
                                                    {((caisse.total_credit / (caisse.total_debit + caisse.total_credit)) * 100).toFixed(3)}%
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ) : <EmptyChart message="Aucune donnée" />}
                        </Section>
                    </div>
                </>
            )}

            {/* ══════ SECTION: BFC ══════ */}
            {(activeSection === 'bfc') && (
                <>
                    {bfc && bfc.nb_periodes > 0 ? (
                        <>
                            {/* KPIs BFC */}
                            <div className="gd-kpi-row gd-kpi-row-4">
                                <KpiCard icon="📊" label="Périodes" color="neutral"
                                    value={bfc.nb_periodes}
                                    sub={`Dernière : ${bfc.derniere_periode}`} loading={loading} />
                                <KpiCard icon="💵" label="CA Net" color="primary"
                                    value={fmtMontant(bfc.pnl_cumule?.ca_net || 0)} unit="TND"
                                    sub="Cumul réalisé" loading={loading} />
                                <KpiCard icon="📈" label="EBITDA" color={bfc.pnl_cumule?.ebitda >= 0 ? 'success' : 'danger'}
                                    value={fmtMontant(bfc.pnl_cumule?.ebitda || 0)} unit="TND"
                                    sub={`${(bfc.pnl_cumule?.ebitda_pct || 0).toFixed(3)}% (cumul)`} loading={loading} />
                                <KpiCard icon="🎯" label="Résultat Net" color={bfc.pnl_cumule?.resultat_net >= 0 ? 'success' : 'danger'}
                                    value={fmtMontant(bfc.pnl_cumule?.resultat_net || 0)} unit="TND"
                                    sub={`${(bfc.pnl_cumule?.resultat_net_pct || 0).toFixed(3)}% (cumul)`} loading={loading} />
                            </div>

                            {/* Tendance + P&L */}
                            <div className="gd-row-2col">
                                <Section title="Tendance Financière" subtitle="CA Net / EBITDA / Résultat Net" icon="📉" className="gd-col-large">
                                    <ResponsiveContainer width="100%" height={300}>
                                        <LineChart data={bfc.tendance} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                            <XAxis dataKey="periode" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                            <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={60} />
                                            <Tooltip content={<CustomTooltip />} />
                                            <Legend wrapperStyle={{ fontSize: 12 }} />
                                            <Line type="monotone" dataKey="ca_net" name="CA Net" stroke={COLORS.primary}
                                                strokeWidth={2.5} dot={{ r: 4, fill: COLORS.primary }} activeDot={{ r: 6 }} />
                                            <Line type="monotone" dataKey="ebitda" name="EBITDA" stroke={COLORS.debit}
                                                strokeWidth={2} dot={{ r: 3, fill: COLORS.debit }} />
                                            <Line type="monotone" dataKey="resultat_net" name="Résultat Net" stroke={COLORS.purple}
                                                strokeWidth={2} dot={{ r: 3, fill: COLORS.purple }} />
                                        </LineChart>
                                    </ResponsiveContainer>
                                </Section>

                                <Section title="Compte de Résultat" subtitle={`Période : ${bfc.derniere_periode}`} icon="📋" className="gd-col-small">
                                    {bfc.pnl_detail ? (
                                        <div className="gd-pnl-detail">
                                            <PnlRow label="CA Net" value={bfc.pnl_detail.ca_net} bold />
                                            <PnlRow label="Total Produits" value={bfc.pnl_detail.total_produits} />
                                            <PnlRow label="Total Charges" value={-Math.abs(bfc.pnl_detail.total_charges)} />
                                            <div className="gd-pnl-sep" />
                                            <PnlRow label="EBITDA" value={bfc.pnl_detail.ebitda} bold pct={bfc.pnl_detail.ebitda_pct} />
                                            <PnlRow label="Rés. Financier" value={bfc.pnl_detail.resultat_financier} />
                                            <PnlRow label="Résultat Exceptionnel" value={bfc.pnl_detail.resultat_exceptionnel} />
                                            <PnlRow label="Dotations" value={-Math.abs(bfc.pnl_detail.dotations)} />
                                            <PnlRow label="Impôt sur les sociétés" value={-Math.abs(bfc.pnl_detail.impot_societes)} />
                                            <div className="gd-pnl-sep" />
                                            <PnlRow label="Résultat Net" value={bfc.pnl_detail.resultat_net} bold highlight pct={bfc.pnl_detail.resultat_net_pct} />
                                        </div>
                                    ) : <EmptyChart message="Aucun P&L disponible" />}
                                </Section>
                            </div>

                            {/* Produits vs Charges */}
                            {bfc.tendance.length > 1 && (
                                <Section title="Produits vs Charges" subtitle="Comparaison mensuelle" icon="⚡">
                                    <ResponsiveContainer width="100%" height={260}>
                                        <BarChart data={bfc.tendance} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                            <XAxis dataKey="periode" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                            <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={60} />
                                            <Tooltip content={<CustomTooltip />} />
                                            <Legend wrapperStyle={{ fontSize: 12 }} />
                                            <Bar dataKey="total_produits" name="Produits" fill={COLORS.success} radius={[4, 4, 0, 0]} barSize={28} />
                                            <Bar dataKey="total_charges" name="Charges" fill={COLORS.credit} radius={[4, 4, 0, 0]} barSize={28} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                </Section>
                            )}
                        </>
                    ) : (
                        <Section title="Analyse BFC" subtitle="Aucune donnée disponible" icon="📊">
                            <EmptyChart message="Aucune période BFC importée. Importez un fichier balance Sage pour alimenter cette section." />
                        </Section>
                    )}
                </>
            )}

            {/* ══════ FOOTER ══════ */}
            <div className="gd-footer-stats">
                <div className="gd-footer-tile">
                    <span className="gd-footer-icon">💹</span>
                    <div>
                        <span className="gd-footer-label">Différence Nette</span>
                        <span className={`gd-footer-val ${(caisse?.total_debit - caisse?.total_credit) >= 0 ? 'positive' : 'negative'}`}>
                            {fmtMontant((caisse?.total_debit || 0) - (caisse?.total_credit || 0))} TND
                        </span>
                    </div>
                </div>
                <div className="gd-footer-tile">
                    <span className="gd-footer-icon">📦</span>
                    <div>
                        <span className="gd-footer-label">Écritures Sage</span>
                        <span className="gd-footer-val">{migration?.total_ecritures || 0} lignes</span>
                    </div>
                </div>
                <div className="gd-footer-tile">
                    <span className={`gd-footer-icon ${wsConnected ? 'gd-pulse' : ''}`}>
                        {wsConnected ? '🟢' : '🔴'}
                    </span>
                    <div>
                        <span className="gd-footer-label">Connexion</span>
                        <span className="gd-footer-val">{wsConnected ? 'Temps réel actif' : 'Reconnexion…'}</span>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ═══════════════════════════════════════════════════════════
// SOUS-COMPOSANTS
// ═══════════════════════════════════════════════════════════

function KpiCard({ icon, label, color, value, unit, sub, trend, trendLabel, loading }) {
    return (
        <div className={`gd-kpi gd-kpi-${color} ${loading ? 'gd-shimmer' : ''}`}>
            <div className="gd-kpi-top">
                <span className="gd-kpi-icon">{icon}</span>
                <span className="gd-kpi-label">{label}</span>
            </div>
            <div className="gd-kpi-mid">
                <span className="gd-kpi-value">{value}</span>
                {unit && <span className="gd-kpi-unit">{unit}</span>}
            </div>
            <div className="gd-kpi-bot">
                {trend && (
                    <span className={`gd-kpi-trend ${trend}`}>
                        {trend === 'up' ? '▲' : '▼'} {trendLabel}
                    </span>
                )}
                {sub && <span className="gd-kpi-sub">{sub}</span>}
            </div>
        </div>
    );
}

function PnlRow({ label, value, bold, highlight, pct }) {
    const color = value >= 0 ? 'var(--success, #10b981)' : 'var(--error, #ef4444)';
    return (
        <div className={`gd-pnl-row ${bold ? 'bold' : ''} ${highlight ? 'highlight' : ''}`}>
            <span className="gd-pnl-label">{label}</span>
            <div className="gd-pnl-vals">
                <span className="gd-pnl-amount" style={highlight ? { color } : {}}>
                    {fmtMontant(value)} TND
                </span>
                {pct !== undefined && (
                    <span className="gd-pnl-pct" style={{ color }}>{pct >= 0 ? '+' : ''}{pct.toFixed(3)}%</span>
                )}
            </div>
        </div>
    );
}

function EmptyChart({ message }) {
    return (
        <div className="gd-empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="40" height="40">
                <path d="M3 3v18h18" /><path d="M18 9l-5 5-4-4-6 6" />
            </svg>
            <p>{message}</p>
        </div>
    );
}

export default Dashboard;
