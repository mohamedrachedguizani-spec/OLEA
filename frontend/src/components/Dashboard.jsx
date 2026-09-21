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
import { useAuth } from '../contexts/AuthContext';
import {
    FiActivity,
    FiArrowDown,
    FiArrowDownCircle,
    FiArrowUp,
    FiArrowUpCircle,
    FiBarChart2,
    FiCalendar,
    FiCheckCircle,
    FiClipboard,
    FiDollarSign,
    FiFileText,
    FiGrid,
    FiHome,
    FiMonitor,
    FiPieChart,
    FiRefreshCw,
    FiShield,
    FiTag,
    FiTarget,
    FiTrendingDown,
    FiTrendingUp,
    FiUser,
    FiUserCheck,
    FiUsers,
    FiUserX,
    FiZap,
} from 'react-icons/fi';

// ─── WebSocket URL ───
const WS_URL = API_BASE_URL.replace(/^http/i, 'ws') + '/ws/live';
const WS_RECONNECT_DELAY = 3000;

// ─── Section definitions ───
const SECTIONS = [
    { id: 'overview',   label: 'Vue d\'ensemble', icon: <FiHome />,       desc: 'Résumé global',       badgeKey: null,        accent: '#d4a528' },
    { id: 'tresorerie', label: 'Trésorerie',      icon: <FiDollarSign />, desc: 'Flux & solde caisse', badgeKey: 'ecritures', accent: '#b7482b' },
    { id: 'bfc',        label: 'Analyse BFC',      icon: <FiBarChart2 />,  desc: 'Résultat financier', badgeKey: 'periodes',   accent: '#2f343a' },
];

const ADMIN_SECTIONS = [
    { id: 'overview', label: 'Vue d\'ensemble', icon: <FiShield />,   desc: 'Superadmin',         badgeKey: 'users',    accent: '#863421' },
    { id: 'audit',    label: 'Audit',            icon: <FiFileText />, desc: 'Activité & modules', badgeKey: 'audit',    accent: '#b7482b' },
    { id: 'users',    label: 'Utilisateurs',     icon: <FiUsers />,    desc: 'Comptes & sessions', badgeKey: 'sessions', accent: '#2f343a' },
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

function usePrefersReducedMotion() {
    const [prefersReducedMotion, setPrefersReducedMotion] = useState(() => (
        typeof window !== 'undefined'
        && typeof window.matchMedia === 'function'
        && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ));

    useEffect(() => {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
        const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        const handleChange = (event) => setPrefersReducedMotion(event.matches);

        setPrefersReducedMotion(mediaQuery.matches);
        mediaQuery.addEventListener?.('change', handleChange);
        return () => mediaQuery.removeEventListener?.('change', handleChange);
    }, []);

    return prefersReducedMotion;
}

function useStableSeriesData(data) {
    const cacheRef = useRef({ signature: '', data: [] });
    const nextData = Array.isArray(data) ? data : [];
    const signature = JSON.stringify(nextData);

    if (cacheRef.current.signature !== signature) {
        cacheRef.current = { signature, data: nextData };
    }

    return cacheRef.current.data;
}

const FinancialTrendChart = React.memo(function FinancialTrendChart({ data, animate }) {
    return (
        <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                <XAxis dataKey="periode" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={60} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="ca_net" name="CA Net" stroke={COLORS.primary}
                    strokeWidth={2.5} dot={{ r: 4, fill: COLORS.primary }} activeDot={{ r: 6 }}
                    isAnimationActive={animate} animationDuration={900} animationEasing="ease-out" animationBegin={0} />
                <Line type="monotone" dataKey="ebitda" name="EBITDA" stroke={COLORS.debit}
                    strokeWidth={2} dot={{ r: 3, fill: COLORS.debit }}
                    isAnimationActive={animate} animationDuration={900} animationEasing="ease-out" animationBegin={120} />
                <Line type="monotone" dataKey="resultat_net" name="Résultat Net" stroke={COLORS.purple}
                    strokeWidth={2} dot={{ r: 3, fill: COLORS.purple }}
                    isAnimationActive={animate} animationDuration={900} animationEasing="ease-out" animationBegin={240} />
            </LineChart>
        </ResponsiveContainer>
    );
});

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

function Dashboard({ refreshTrigger, onNavigate }) {
    const { isSuperAdmin } = useAuth();
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [filterType, setFilterType] = useState('month');
    const [dateDebut, setDateDebut] = useState('');
    const [dateFin, setDateFin] = useState('');
    const today = new Date();
    const [bfcFilterMode, setBfcFilterMode] = useState('period');
    const [bfcYear, setBfcYear] = useState(String(today.getFullYear()));
    const [bfcMonth, setBfcMonth] = useState('');
    const [bfcYears, setBfcYears] = useState([]);
    const [lastUpdate, setLastUpdate] = useState(new Date());
    const [activeSection, setActiveSection] = useState('overview');
    const [wsConnected, setWsConnected] = useState(false);

    // ── WebSocket temps réel ──
    const wsRef = useRef(null);
    const reconnectTimer = useRef(null);
    const loadDataRef = useRef(null);
    const isSuperAdminRef = useRef(isSuperAdmin);
    const bfcYearInitializedRef = useRef(false);

    // ── Période ──
    const getDateRange = useCallback(() => {
        if (!isSuperAdmin && activeSection === 'bfc') {
            if (bfcFilterMode === 'all') return { debut: null, fin: null };
            if (bfcFilterMode === 'custom') {
                return { debut: dateDebut || null, fin: dateFin || null };
            }
            const selectedYear = Number(bfcYear);
            if (!selectedYear) return { debut: null, fin: null };
            if (!bfcMonth) {
                return { debut: `${selectedYear}-01-01`, fin: `${selectedYear}-12-31` };
            }
            const selectedMonth = Number(bfcMonth);
            const lastDay = new Date(selectedYear, selectedMonth, 0).getDate();
            return {
                debut: `${selectedYear}-${bfcMonth}-01`,
                fin: `${selectedYear}-${bfcMonth}-${String(lastDay).padStart(2, '0')}`,
            };
        }
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
    }, [filterType, dateDebut, dateFin, isSuperAdmin, activeSection, bfcFilterMode, bfcYear, bfcMonth]);

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const { debut, fin } = getDateRange();
            const res = isSuperAdmin
                ? await ApiService.getAdminDashboard(debut, fin)
                : await ApiService.getGlobalDashboard(debut, fin);
            setData(res);
            setLastUpdate(new Date());
        } catch (err) {
            // Pas de log console
        } finally {
            setLoading(false);
        }
    }, [getDateRange, isSuperAdmin]);

    // Keep loadDataRef in sync so the WebSocket callback always calls the latest version
    useEffect(() => { loadDataRef.current = loadData; }, [loadData]);
    useEffect(() => { isSuperAdminRef.current = isSuperAdmin; }, [isSuperAdmin]);

    // ── WebSocket connection ──
    const connectWs = useCallback(() => {
        if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            setWsConnected(true);
        };

        ws.onmessage = (event) => {
            try {
                const { channel } = JSON.parse(event.data);
                // Reload the dashboard when any relevant channel fires
                const channels = isSuperAdminRef.current
                    ? ['users', 'audit', 'sessions']
                    : ['caisse', 'migration', 'sage_bfc', 'forecast'];
                if (channels.includes(channel)) {
                    loadDataRef.current?.();
                }
            } catch (err) {
                // Pas de log
            }
        };

        ws.onclose = (event) => {
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
            if (wsRef.current) {
                wsRef.current.onopen = null;
                wsRef.current.onmessage = null;
                wsRef.current.onerror = null;
                wsRef.current.onclose = null;
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [connectWs]);

    // Initial load + reload on filter/trigger change
    useEffect(() => { loadData(); }, [loadData, refreshTrigger, filterType]);

    useEffect(() => {
        if (filterType === 'custom' && dateDebut && dateFin) loadData();
    }, [dateDebut, dateFin, filterType, loadData]);

    useEffect(() => {
        if (isSuperAdmin) return;
        ApiService.getSageBfcMonthlyYears()
            .then(result => {
                const years = result?.years || [];
                setBfcYears(years);
                if (years.length && !bfcYearInitializedRef.current) {
                    setBfcYear(String(years[0]));
                    setBfcMonth('');
                    bfcYearInitializedRef.current = true;
                }
            })
            .catch(() => setBfcYears([]));
    }, [isSuperAdmin, refreshTrigger]);

    // ── Derived data ──
    const caisse = data?.caisse;
    const migration = data?.migration;
    const bfc = data?.bfc;
    const bfcTrendData = useStableSeriesData(bfc?.tendance);
    const prefersReducedMotion = usePrefersReducedMotion();
    const animateBfcTrend = !prefersReducedMotion && bfcTrendData.length > 1;
    const overview = data?.overview;
    const adminUsers = data?.users;
    const adminSessions = data?.sessions;
    const adminAudit = data?.audit;
    const adminRealtime = data?.realtime;

    const tauxMigration = useMemo(() => {
        if (!caisse || caisse.nombre_ecritures === 0) return 0;
        return Math.round((caisse.ecritures_migrees / caisse.nombre_ecritures) * 100);
    }, [caisse]);

    const rolePieData = useMemo(() => {
        if (!adminUsers?.roles) return [];
        return Object.entries(adminUsers.roles).map(([name, value]) => ({ name, value }));
    }, [adminUsers]);

    const auditModuleData = useMemo(() => adminAudit?.by_module || [], [adminAudit]);
    const auditTimelineData = useMemo(() => {
        if (!adminAudit?.timeline) return [];
        return adminAudit.timeline.map((row) => ({
            ...row,
            day: row.day,
        }));
    }, [adminAudit]);

    const userStatusData = useMemo(() => ([
        { name: 'Actifs', value: adminUsers?.active || 0 },
        { name: 'Inactifs', value: adminUsers?.inactive || 0 },
    ]), [adminUsers]);

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
    const monthLabels = [
        'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
    ];
    const bfcPeriodLabel = bfcFilterMode === 'all'
        ? 'Toutes périodes'
        : bfcFilterMode === 'custom'
            ? 'Personnalisé'
            : `${bfcMonth ? monthLabels[Number(bfcMonth) - 1] : 'Toute l’année'} ${bfcYear}`;
    const isBfcMonthlySelection = bfcFilterMode === 'period' && Boolean(bfcMonth);
    const bfcSelectedMonthLabel = isBfcMonthlySelection
        ? `${monthLabels[Number(bfcMonth) - 1]} ${bfcYear}`
        : '';
    const bfcPnlPeriodLabel = bfc?.premiere_periode && bfc?.derniere_periode
        ? (bfc.premiere_periode === bfc.derniere_periode
            ? bfc.derniere_periode
            : `de ${bfc.premiere_periode} à ${bfc.derniere_periode}`)
        : 'indisponible';

    const navSections = isSuperAdmin ? ADMIN_SECTIONS : SECTIONS;

    const openOverviewTarget = useCallback((target) => {
        if (target === 'tresorerie' || target === 'bfc') {
            setActiveSection(target);
            return;
        }
        onNavigate?.(target);
    }, [onNavigate]);

    const openLatestBfcYear = useCallback(() => {
        const latestYear = overview?.kpis?.latest_bfc_year;
        if (latestYear) setBfcYear(String(latestYear));
        setBfcMonth('');
        setBfcFilterMode('period');
        setActiveSection('bfc');
    }, [overview?.kpis?.latest_bfc_year]);

    useEffect(() => {
        if (isSuperAdmin && !['overview', 'audit', 'users'].includes(activeSection)) {
            setActiveSection('overview');
        }
        if (!isSuperAdmin && ['audit', 'users'].includes(activeSection)) {
            setActiveSection('overview');
        }
    }, [isSuperAdmin, activeSection]);

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
                    <h2 className="gd-main-title">
                        {isSuperAdmin ? 'Tableau de Bord ' : 'Tableau de Bord Global'}
                    </h2>
                    <div className="gd-header-meta">
                        <span className="gd-period-badge">
                            {activeSection === 'bfc' && !isSuperAdmin ? bfcPeriodLabel : periodLabels[filterType]}
                        </span>
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
                    {activeSection === 'bfc' && !isSuperAdmin ? (
                        <div className="gd-bfc-filters">
                            <div className={`gd-filter-group gd-filter-selects ${bfcFilterMode === 'period' ? 'active' : ''}`}>
                                <label className="gd-filter-select-field">
                                    <span>Année</span>
                                    <select aria-label="Année BFC" value={bfcYear} onChange={e => { setBfcYear(e.target.value); setBfcFilterMode('period'); }}>
                                        {(bfcYears.length ? bfcYears : [Number(bfcYear)]).map(year => (
                                            <option key={year} value={year}>{year}</option>
                                        ))}
                                    </select>
                                </label>
                                <label className="gd-filter-select-field">
                                    <span>Mois</span>
                                    <select aria-label="Mois BFC" value={bfcMonth} onChange={e => { setBfcMonth(e.target.value); setBfcFilterMode('period'); }}>
                                        <option value="">Toute la Periode</option>
                                        {monthLabels.map((month, index) => (
                                            <option key={month} value={String(index + 1).padStart(2, '0')}>{month}</option>
                                        ))}
                                    </select>
                                </label>
                                <button className={`gd-filter-pill ${bfcFilterMode === 'all' ? 'active' : ''}`} onClick={() => setBfcFilterMode('all')}>Tout</button>
                                <button className={`gd-filter-pill ${bfcFilterMode === 'custom' ? 'active' : ''}`} onClick={() => setBfcFilterMode('custom')}>Custom</button>
                            </div>
                        </div>
                    ) : (
                        <div className="gd-filter-group">
                            {['today', 'week', 'month', 'year', 'all', 'custom'].map(t => (
                                <button key={t} className={`gd-filter-pill ${filterType === t ? 'active' : ''}`}
                                    onClick={() => setFilterType(t)}>
                                    {{ today: 'Jour', week: 'Semaine', month: 'Mois', year: 'Année', all: 'Tout', custom: 'Custom' }[t]}
                                </button>
                            ))}
                        </div>
                    )}
                    {((activeSection === 'bfc' && bfcFilterMode === 'custom') || (activeSection !== 'bfc' && filterType === 'custom')) && (
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
                {navSections.map(s => {
                    let badge = null;
                    if (isSuperAdmin) {
                        badge = s.badgeKey === 'users' ? (adminUsers?.total || 0)
                            : s.badgeKey === 'audit' ? (adminAudit?.total_24h || 0)
                            : s.badgeKey === 'sessions' ? (adminSessions?.active_users || 0)
                            : null;
                    } else {
                        badge = s.badgeKey === 'ecritures' ? (caisse?.nombre_ecritures || 0)
                            : s.badgeKey === 'pieces'    ? (migration?.nb_pieces || 0)
                            : s.badgeKey === 'periodes'  ? (bfc?.nb_periodes || 0)
                            : null;
                    }
                    const isActive = activeSection === s.id;
                    return (
                        <button key={s.id}
                            className={`gd-snav-card ${isActive ? 'active' : ''}`}
                            onClick={() => s.id === 'bfc' ? openLatestBfcYear() : setActiveSection(s.id)}
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

            {isSuperAdmin ? (
                <>
                    {/* ══════ SECTION: SUPERADMIN OVERVIEW ══════ */}
                    {(activeSection === 'overview') && (
                        <>
                            <div className="gd-kpi-row">
                                <KpiCard icon={<FiUsers />} label="Utilisateurs" color="primary"
                                    value={adminUsers?.total || 0}
                                    sub={`${adminUsers?.active || 0} actifs`} loading={loading} />
                                <KpiCard icon={<FiUserCheck />} label="Actifs" color="success"
                                    value={adminUsers?.active || 0}
                                    sub={`${adminUsers?.inactive || 0} inactifs`} loading={loading} />
                                <KpiCard icon={<FiUserX />} label="Inactifs" color="danger"
                                    value={adminUsers?.inactive || 0} loading={loading} />
                                <KpiCard icon={<FiMonitor />} label="Sessions actives" color="purple"
                                    value={adminSessions?.total_sessions || 0}
                                    sub={`Utilisateurs: ${adminSessions?.active_users || 0}`} loading={loading} />
                                <KpiCard icon={<FiFileText />} label="Audit 24h" color="debit"
                                    value={adminAudit?.total_24h || 0} loading={loading} />
                                <KpiCard icon={<FiCalendar />} label="Audit 7j" color="neutral"
                                    value={adminAudit?.total_7d || 0}
                                    sub={`WS: ${adminRealtime?.ws_clients || 0}`} loading={loading} />
                            </div>

                            <div className="gd-row-2col">
                                <Section title="Activité d'audit" subtitle="Évolution des actions" icon={<FiTrendingUp />} className="gd-col-large">
                                    {auditTimelineData.length > 0 ? (
                                        <ResponsiveContainer width="100%" height={280}>
                                            <LineChart data={auditTimelineData} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                                <XAxis dataKey="day" tickFormatter={fmtDate} fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                                <YAxis fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={45} allowDecimals={false} />
                                                <Tooltip content={<CustomTooltip formatter={(v) => v} />} />
                                                <Legend wrapperStyle={{ fontSize: 12 }} />
                                                <Line type="monotone" dataKey="cnt" name="Actions" stroke={COLORS.primary} strokeWidth={2.5} dot={false} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    ) : <EmptyChart message="Aucune activité sur cette période" />}
                                </Section>

                                <Section title="Répartition des rôles" subtitle="Utilisateurs par rôle" icon={<FiPieChart />} className="gd-col-small">
                                    {rolePieData.length > 0 ? (
                                        <div className="gd-pie-wrap">
                                            <ResponsiveContainer width="100%" height={200}>
                                                <PieChart>
                                                    <Pie data={rolePieData} cx="50%" cy="50%" innerRadius={55} outerRadius={80}
                                                        paddingAngle={4} dataKey="value" strokeWidth={0}>
                                                        {rolePieData.map((_, idx) => (
                                                            <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                                                        ))}
                                                    </Pie>
                                                    <Tooltip formatter={(v) => v} />
                                                </PieChart>
                                            </ResponsiveContainer>
                                        </div>
                                    ) : <EmptyChart message="Aucun utilisateur" />}
                                </Section>
                            </div>
                        </>
                    )}

                    {/* ══════ SECTION: SUPERADMIN AUDIT ══════ */}
                    {(activeSection === 'audit') && (
                        <div className="gd-row-2col">
                            <Section title="Activité par module" subtitle="Top modules sur la période" icon={<FiGrid />} className="gd-col-large">
                                {auditModuleData.length > 0 ? (
                                    <ResponsiveContainer width="100%" height={280}>
                                        <BarChart data={auditModuleData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                            <XAxis dataKey="module" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                            <YAxis fontSize={11} tick={{ fill: 'var(--text-muted)' }} allowDecimals={false} />
                                            <Tooltip content={<CustomTooltip formatter={(v) => v} />} />
                                            <Legend wrapperStyle={{ fontSize: 12 }} />
                                            <Bar dataKey="cnt" name="Actions" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                ) : <EmptyChart message="Aucune activité" />}
                            </Section>

                            <Section title="Chronologie" subtitle="Flux d'actions" icon={<FiCalendar />} className="gd-col-small">
                                {auditTimelineData.length > 0 ? (
                                    <ResponsiveContainer width="100%" height={200}>
                                        <AreaChart data={auditTimelineData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                                            <defs>
                                                <linearGradient id="adminAuditGrad" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor={COLORS.primary} stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor={COLORS.primary} stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                            <XAxis dataKey="day" tickFormatter={fmtDate} fontSize={10} tick={{ fill: 'var(--text-muted)' }} />
                                            <YAxis fontSize={10} tick={{ fill: 'var(--text-muted)' }} allowDecimals={false} />
                                            <Tooltip content={<CustomTooltip formatter={(v) => v} />} />
                                            <Area type="monotone" dataKey="cnt" name="Actions" stroke={COLORS.primary} fill="url(#adminAuditGrad)" strokeWidth={2} />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                ) : <EmptyChart message="Aucune activité" />}
                            </Section>
                        </div>
                    )}

                    {/* ══════ SECTION: SUPERADMIN USERS ══════ */}
                    {(activeSection === 'users') && (
                        <div className="gd-row-2col">
                            <Section title="Actifs vs Inactifs" subtitle="Statut des comptes" icon={<FiUser />} className="gd-col-large">
                                {userStatusData.some(d => d.value > 0) ? (
                                    <ResponsiveContainer width="100%" height={280}>
                                        <BarChart data={userStatusData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                            <XAxis dataKey="name" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                            <YAxis fontSize={11} tick={{ fill: 'var(--text-muted)' }} allowDecimals={false} />
                                            <Tooltip content={<CustomTooltip formatter={(v) => v} />} />
                                            <Bar dataKey="value" name="Utilisateurs" fill={COLORS.debit} radius={[4, 4, 0, 0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                ) : <EmptyChart message="Aucun compte" />}
                            </Section>

                            <Section title="Rôles" subtitle="Répartition par rôle" icon={<FiGrid />} className="gd-col-small">
                                {rolePieData.length > 0 ? (
                                    <div className="gd-pie-wrap">
                                        <ResponsiveContainer width="100%" height={200}>
                                            <PieChart>
                                                <Pie data={rolePieData} cx="50%" cy="50%" innerRadius={55} outerRadius={80}
                                                    paddingAngle={4} dataKey="value" strokeWidth={0}>
                                                    {rolePieData.map((_, idx) => (
                                                        <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                                                    ))}
                                                </Pie>
                                                <Tooltip formatter={(v) => v} />
                                            </PieChart>
                                        </ResponsiveContainer>
                                    </div>
                                ) : <EmptyChart message="Aucun utilisateur" />}
                            </Section>
                        </div>
                    )}
                </>
            ) : (
                <>
                    {/* ══════ SECTION: VUE D'ENSEMBLE ══════ */}
                    {(activeSection === 'overview') && (
                        <>
                            {/* KPI GLOBAUX */}
                            <div className="gd-kpi-row gd-kpi-row-5">
                                <KpiCard icon={<FiDollarSign />} label="Solde Caisse" color="primary"
                                    value={fmtMontant(caisse?.solde_actuel || 0)} unit="TND"
                                    trend={caisse?.solde_actuel >= 0 ? 'up' : 'down'}
                                    trendLabel={caisse?.solde_actuel >= 0 ? 'Positif' : 'Négatif'}
                                    onClick={() => openOverviewTarget('tresorerie')} loading={loading} />
                                <KpiCard icon={<FiRefreshCw />} label="Taux Migration" color="purple"
                                    value={`${tauxMigration}%`}
                                    sub={`${caisse?.ecritures_migrees || 0} / ${caisse?.nombre_ecritures || 0}`}
                                    onClick={() => openOverviewTarget('tresorerie')} loading={loading} />
                                <KpiCard icon={<FiCheckCircle />} label="Balance Sage" color={migration?.equilibre ? 'success' : 'danger'}
                                    value={migration?.equilibre ? 'Équilibrée' : 'Déséquilibrée'}
                                    sub={`${migration?.nb_pieces || 0} pièces`}
                                    onClick={() => openOverviewTarget('tresorerie')} loading={loading} />
                                <KpiCard icon={<FiBarChart2 />} label="CA Net BFC" color="debit"
                                    value={fmtMontant(overview?.kpis?.ca_net || 0)} unit="TND"
                                    sub={overview?.kpis?.latest_bfc_year ? `Cumul ${overview.kpis.latest_bfc_year}` : 'Aucune période'}
                                    onClick={openLatestBfcYear} loading={loading} />
                                <KpiCard icon={<FiTarget />} label="Résultat Net BFC" color={(overview?.kpis?.resultat_net || 0) >= 0 ? 'success' : 'danger'}
                                    value={fmtMontant(overview?.kpis?.resultat_net || 0)} unit="TND"
                                    sub={`${(overview?.kpis?.resultat_net_pct || 0).toFixed(3)}% · Cumul ${overview?.kpis?.latest_bfc_year || '—'}`}
                                    onClick={openLatestBfcYear} loading={loading} />
                            </div>

                            <div className="gd-row-2col">
                                <Section title="Comparaison N-1" subtitle="Période filtrée face à la même période précédente" icon={<FiTrendingUp />} className="gd-col-large">
                                    {overview?.comparison?.available ? (
                                        <ResponsiveContainer width="100%" height={285}>
                                            <BarChart data={overview.comparison.data} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                                <XAxis dataKey="name" fontSize={10} interval={0} tick={{ fill: 'var(--text-muted)' }} />
                                                <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={60} />
                                                <Tooltip content={<CustomTooltip />} />
                                                <Legend wrapperStyle={{ fontSize: 12 }} />
                                                <Bar dataKey="n_1" name="N-1" fill={COLORS.neutral} radius={[4, 4, 0, 0]} />
                                                <Bar dataKey="periode" name="Période filtrée" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    ) : <EmptyChart message="Aucune donnée disponible pour la comparaison N-1" />}
                                </Section>

                                <Section title="Centre d'attention" subtitle="Anomalies et actions prioritaires" icon={<FiMonitor />} className="gd-col-small">
                                    <FinancialAlerts alerts={overview?.alerts || []} onSelect={(alert) => openOverviewTarget(alert.target_section)} />
                                </Section>
                            </div>

                        </>
                    )}

            {/* ══════ SECTION: TRÉSORERIE ══════ */}
            {(activeSection === 'tresorerie') && (
                <>
                    {/* KPIs Caisse */}
                    <div className="gd-kpi-row gd-kpi-row-4">
                        <KpiCard icon={<FiDollarSign />} label="Solde Caisse" color="primary"
                            value={fmtMontant(caisse?.solde_actuel || 0)} unit="TND"
                            trend={caisse?.solde_actuel >= 0 ? 'up' : 'down'}
                            trendLabel={caisse?.solde_actuel >= 0 ? 'Positif' : 'Négatif'} loading={loading} />
                        <KpiCard icon={<FiArrowDownCircle />} label="Total Entrées" color="debit"
                            value={fmtMontant(caisse?.total_debit || 0)} unit="TND"
                            sub={`${caisse?.nombre_ecritures || 0} écritures`} loading={loading} />
                        <KpiCard icon={<FiArrowUpCircle />} label="Total Sorties" color="credit"
                            value={fmtMontant(caisse?.total_credit || 0)} unit="TND" loading={loading} />
                        <KpiCard icon={<FiActivity />} label="Différence Nette" color={((caisse?.total_debit || 0) - (caisse?.total_credit || 0)) >= 0 ? 'success' : 'danger'}
                            value={fmtMontant((caisse?.total_debit || 0) - (caisse?.total_credit || 0))} unit="TND" loading={loading} />
                    </div>

                    {/* Flux Area Chart — full width */}
                    <Section title="Flux de Trésorerie" subtitle="Évolution journalière avec solde cumulé" icon={<FiTrendingUp />}>
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
                        <Section title="Top Libellés" subtitle="Par volume d'opérations" icon={<FiTag />} className="gd-col-large">
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

                        <Section title="Répartition" subtitle="Entrées vs Sorties" icon={<FiPieChart />} className="gd-col-small">
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
                                <KpiCard icon={<FiBarChart2 />} label={isBfcMonthlySelection ? `Période · ${bfcSelectedMonthLabel}` : 'Périodes'} color="neutral"
                                    value={bfc.nb_periodes}
                                    sub={`Dernière : ${bfc.derniere_periode}`} loading={loading} />
                                <KpiCard icon={<FiDollarSign />} label={isBfcMonthlySelection ? `CA Net · ${bfcSelectedMonthLabel}` : 'CA Net cumulé'} color="primary"
                                    value={fmtMontant(bfc.pnl_cumule?.ca_net || 0)} unit="TND"
                                    sub={isBfcMonthlySelection ? 'Mois sélectionné' : 'Cumul réalisé'} loading={loading} />
                                <KpiCard icon={<FiTrendingUp />} label={isBfcMonthlySelection ? `EBITDA · ${bfcSelectedMonthLabel}` : 'EBITDA cumulé'} color={bfc.pnl_cumule?.ebitda >= 0 ? 'success' : 'danger'}
                                    value={fmtMontant(bfc.pnl_cumule?.ebitda || 0)} unit="TND"
                                    sub={`${(bfc.pnl_cumule?.ebitda_pct || 0).toFixed(3)}%${isBfcMonthlySelection ? '' : ' (cumul)'}`} loading={loading} />
                                <KpiCard icon={<FiTarget />} label={isBfcMonthlySelection ? `Résultat Net · ${bfcSelectedMonthLabel}` : 'Résultat Net cumulé'} color={bfc.pnl_cumule?.resultat_net >= 0 ? 'success' : 'danger'}
                                    value={fmtMontant(bfc.pnl_cumule?.resultat_net || 0)} unit="TND"
                                    sub={`${(bfc.pnl_cumule?.resultat_net_pct || 0).toFixed(3)}%${isBfcMonthlySelection ? '' : ' (cumul)'}`} loading={loading} />
                            </div>

                            {/* Tendance + P&L */}
                            <div className="gd-row-2col">
                                <Section title="Tendance Financière" subtitle="CA Net / EBITDA / Résultat Net" icon={<FiTrendingDown />} className="gd-col-large">
                                    <FinancialTrendChart data={bfcTrendData} animate={animateBfcTrend} />
                                </Section>

                                <Section title="Compte de Résultat" subtitle={`Période : ${bfcPnlPeriodLabel}`} icon={<FiClipboard />} className="gd-col-small">
                                    {bfc.pnl_detail ? (
                                        <div className="gd-pnl-detail">
                                            <PnlRow label="CA Net" value={bfc.pnl_detail.ca_net} bold />
                                            <PnlRow label="Total Produits" value={bfc.pnl_detail.total_produits} />
                                            <PnlRow label="Total Charges" value={-bfc.pnl_detail.total_charges} />
                                            <div className="gd-pnl-sep" />
                                            <PnlRow label="EBITDA" value={bfc.pnl_detail.ebitda} bold pct={bfc.pnl_detail.ebitda_pct} />
                                            <PnlRow label="Rés. Financier" value={bfc.pnl_detail.resultat_financier} />
                                            <PnlRow label="Résultat Exceptionnel" value={bfc.pnl_detail.resultat_exceptionnel} />
                                            <PnlRow label="Dotations" value={-bfc.pnl_detail.dotations} />
                                            <PnlRow label="Impôt sur les sociétés" value={-bfc.pnl_detail.impot_societes} />
                                            <div className="gd-pnl-sep" />
                                            <PnlRow label="Résultat Net" value={bfc.pnl_detail.resultat_net} bold highlight pct={bfc.pnl_detail.resultat_net_pct} />
                                        </div>
                                    ) : <EmptyChart message="Aucun P&L disponible" />}
                                </Section>
                            </div>

                            {/* Analyses décisionnelles complémentaires */}
                            <div className="gd-row-2col">
                                <Section title="Résultat financier" subtitle="Produits et charges financières par mois" icon={<FiActivity />} className="gd-col-large">
                                    <ResponsiveContainer width="100%" height={290}>
                                        <ComposedChart data={bfc.tendance} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                            <XAxis dataKey="periode" fontSize={11} tick={{ fill: 'var(--text-muted)' }} />
                                            <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={60} />
                                            <Tooltip content={<CustomTooltip />} />
                                            <Legend wrapperStyle={{ fontSize: 12 }} />
                                            <Bar dataKey="produits_financiers" name="Produits financiers" fill={COLORS.debit} radius={[4, 4, 0, 0]} barSize={22} />
                                            <Bar dataKey="charges_financieres" name="Charges financières" fill={COLORS.creditLight} radius={[4, 4, 0, 0]} barSize={22} />
                                            <Line type="monotone" dataKey="resultat_financier" name="Résultat financier" stroke={COLORS.purple}
                                                strokeWidth={2.5} dot={{ r: 4, fill: COLORS.purple }} />
                                        </ComposedChart>
                                    </ResponsiveContainer>
                                </Section>

                                <Section title="Structure des charges" subtitle="Poids des postes sur la période" icon={<FiPieChart />} className="gd-col-small">
                                    <ChargeStructure data={bfc.charge_structure || []} />
                                </Section>
                            </div>

                            <Section title="Comparaison N-1" subtitle="Même période de l'année précédente" icon={<FiTrendingUp />}>
                                    {bfc.comparison_n1?.available ? (
                                        <ResponsiveContainer width="100%" height={310}>
                                            <BarChart data={bfc.comparison_n1.data} margin={{ top: 10, right: 15, left: 0, bottom: 20 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                                                <XAxis dataKey="name" fontSize={10} interval={0} tick={{ fill: 'var(--text-muted)' }} />
                                                <YAxis tickFormatter={fmtShort} fontSize={11} tick={{ fill: 'var(--text-muted)' }} width={60} />
                                                <Tooltip content={<CustomTooltip />} />
                                                <Legend wrapperStyle={{ fontSize: 12 }} />
                                                <Bar dataKey="n_1" name="N-1" fill={COLORS.neutral} radius={[4, 4, 0, 0]} />
                                                <Bar dataKey="periode" name="Période filtrée" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    ) : <EmptyChart message="Aucune donnée disponible sur la même période N-1" />}
                            </Section>

                            <Section title="Points d'attention" subtitle="Signaux calculés sur la période filtrée" icon={<FiMonitor />}>
                                <FinancialAlerts alerts={bfc.alerts || []} />
                            </Section>

                            {/* Produits vs Charges */}
                            {bfc.tendance.length > 1 && (
                                <Section title="Produits vs Charges" subtitle="Comparaison mensuelle" icon={<FiZap />}>
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
                        <Section title="Analyse BFC" subtitle="Aucune donnée disponible" icon={<FiBarChart2 />}>
                            <EmptyChart message="Aucune période BFC importée. Importez un fichier balance Sage pour alimenter cette section." />
                        </Section>
                    )}
                </>
            )}

                </>
            )}

            {/* ══════ FOOTER ══════ */}
            {/* {isSuperAdmin ? (
                <div className="gd-footer-stats">
                    <div className="gd-footer-tile">
                        <span className="gd-footer-icon">👥</span>
                        <div>
                            <span className="gd-footer-label">Utilisateurs actifs</span>
                            <span className="gd-footer-val">{adminUsers?.active || 0}</span>
                        </div>
                    </div>
                    <div className="gd-footer-tile">
                        <span className="gd-footer-icon">🧾</span>
                        <div>
                            <span className="gd-footer-label">Audit 24h</span>
                            <span className="gd-footer-val">{adminAudit?.total_24h || 0} actions</span>
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
            ) : (
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
            )} */}
        </div>
    );
}

// ═══════════════════════════════════════════════════════════
// SOUS-COMPOSANTS
// ═══════════════════════════════════════════════════════════

function KpiCard({ icon, label, color, value, unit, sub, trend, trendLabel, loading, onClick }) {
    const CardTag = onClick ? 'button' : 'div';
    return (
        <CardTag type={onClick ? 'button' : undefined} onClick={onClick}
            className={`gd-kpi gd-kpi-${color} ${onClick ? 'gd-kpi-clickable' : ''} ${loading ? 'gd-shimmer' : ''}`}>
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
                        {trend === 'up' ? <FiArrowUp /> : <FiArrowDown />} {trendLabel}
                    </span>
                )}
                {sub && <span className="gd-kpi-sub">{sub}</span>}
            </div>
        </CardTag>
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

function ChargeStructure({ data }) {
    if (!data.length) return <EmptyChart message="Aucune charge sur la période filtrée" />;
    const total = data.reduce((sum, item) => sum + item.value, 0);
    return (
        <div className="gd-pie-wrap">
            <ResponsiveContainer width="100%" height={190}>
                <PieChart>
                    <Pie data={data} cx="50%" cy="50%" innerRadius={52} outerRadius={78}
                        paddingAngle={3} dataKey="value" strokeWidth={0}>
                        {data.map((item, index) => <Cell key={item.name} fill={PIE_COLORS[index % PIE_COLORS.length]} />)}
                    </Pie>
                    <Tooltip content={<CustomTooltip />} />
                </PieChart>
            </ResponsiveContainer>
            <div className="gd-charge-legend">
                {data.map((item, index) => (
                    <div className="gd-charge-item" key={item.name}>
                        <span className="gd-pie-dot" style={{ background: PIE_COLORS[index % PIE_COLORS.length] }} />
                        <span className="gd-charge-name">{item.name}</span>
                        <strong>{total ? (item.value / total * 100).toFixed(1) : '0.0'}%</strong>
                    </div>
                ))}
            </div>
        </div>
    );
}

function FinancialAlerts({ alerts, onSelect }) {
    if (!alerts.length) return <EmptyChart message="Aucun signal disponible" />;
    return (
        <div className="gd-financial-alerts">
            {alerts.map((alert, index) => {
                const AlertTag = onSelect && alert.target_section ? 'button' : 'div';
                return (
                <AlertTag type={AlertTag === 'button' ? 'button' : undefined}
                    onClick={AlertTag === 'button' ? () => onSelect(alert) : undefined}
                    className={`gd-financial-alert gd-financial-alert-${alert.level} ${AlertTag === 'button' ? 'clickable' : ''}`}
                    key={`${alert.title}-${index}`}>
                    <span className="gd-financial-alert-icon">
                        {alert.level === 'success' ? <FiCheckCircle /> : alert.level === 'danger' ? <FiTrendingDown /> : <FiActivity />}
                    </span>
                    <div>
                        <strong>{alert.title}</strong>
                        <p>{alert.message}</p>
                    </div>
                </AlertTag>
                );
            })}
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
