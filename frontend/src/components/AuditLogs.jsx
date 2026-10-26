import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactDOM from 'react-dom';
import { FiShield, FiEye, FiTrash2, FiClock, FiUser, FiTag, FiDatabase } from 'react-icons/fi';
import ApiService, { API_BASE_URL } from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import './sage-bfc/SageBfcParser.css';
import './BalanceAgee.css';   // cartes, icônes d'action et fenêtre de confirmation partagées

const WS_URL = API_BASE_URL.replace(/^http/i, 'ws') + '/ws/live';
const WS_RECONNECT_DELAY = 3000;

const ACTION_STYLES = {
    create: { label: 'Création', tone: 'success' },
    created: { label: 'Création', tone: 'success' },
    import: { label: 'Import', tone: 'success' },
    update: { label: 'Modification', tone: 'warning' },
    updated: { label: 'Modification', tone: 'warning' },
    delete: { label: 'Suppression', tone: 'danger' },
    deleted: { label: 'Suppression', tone: 'danger' },
    login: { label: 'Connexion', tone: 'info' },
    logout: { label: 'Déconnexion', tone: 'muted' },
};

const actionMeta = (action) => {
    const raw = String(action || '').toLowerCase();
    return ACTION_STYLES[raw] || { label: raw ? raw.replaceAll('_', ' ') : 'Action', tone: 'muted' };
};
const displayModule = (module) => String(module || '-').replaceAll('_', ' ');
const displayEntity = (log) => [log.entity_type, log.entity_id].filter(Boolean).join(' · ') || '-';
const displayDate = (value) => value ? new Date(value).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'medium' }) : '-';
const detailEntries = (detail) => detail && typeof detail === 'object' ? Object.entries(detail) : [];
const detailSummary = (log) => {
    const entries = detailEntries(log.detail);
    if (!entries.length) return displayEntity(log);
    const [key, value] = entries[0];
    const text = typeof value === 'object' ? JSON.stringify(value) : String(value);
    return `${key.replaceAll('_', ' ')} : ${text}`;
};

function AuditLogs() {
    const { isSuperAdmin } = useAuth();
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');

    const [search, setSearch] = useState('');
    const [moduleFilter, setModuleFilter] = useState('');
    const [actionFilter, setActionFilter] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');

    const [page, setPage] = useState(1);
    const [pageSize] = useState(25);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(1);

    const [selectedLog, setSelectedLog] = useState(null);
    const [showTechnical, setShowTechnical] = useState(false);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [selectedIds, setSelectedIds] = useState([]);
    const [moduleOptions, setModuleOptions] = useState([]);

    const wsRef = useRef(null);
    const reconnectTimer = useRef(null);
    const loadLogsRef = useRef(null);

    const loadLogs = useCallback(async () => {
        if (!isSuperAdmin) return;
        setLoading(true);
        setMessage('');
        try {
            const params = {
                search,
                page,
                page_size: pageSize,
            };
            if (moduleFilter) params.module = moduleFilter;
            if (actionFilter) params.action = actionFilter;
            if (dateFrom) params.date_from = dateFrom;
            if (dateTo) params.date_to = dateTo;

            const data = await ApiService.getAuditLogs(params);
            const items = Array.isArray(data?.items) ? data.items : [];
            setLogs(items);
            setTotal(Number(data?.total ?? items.length));
            setPages(Number(data?.pages ?? 1));
            setPage(Number(data?.page ?? page));
        } catch (error) {
            setMessage(`Erreur lors du chargement: ${error.message}`);
        } finally {
            setLoading(false);
        }
    }, [isSuperAdmin, search, page, pageSize, moduleFilter, actionFilter, dateFrom, dateTo]);

    useEffect(() => { loadLogsRef.current = loadLogs; }, [loadLogs]);

    useEffect(() => {
        loadLogs();
    }, [loadLogs]);

    useEffect(() => {
        if (!isSuperAdmin) return;
        ApiService.getAuditModules()
            .then((data) => {
                const items = Array.isArray(data?.items) ? data.items : [];
                setModuleOptions(items);
            })
            .catch(() => {
                setModuleOptions([]);
            });
    }, [isSuperAdmin]);

    useEffect(() => {
        setSelectedIds([]);
    }, [logs]);

    const connectWs = useCallback(() => {
        if (!isSuperAdmin) return;
        if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

        const ws = new WebSocket(WS_URL);

        ws.onmessage = (event) => {
            try {
                const { channel } = JSON.parse(event.data);
                if (channel === 'audit') {
                    loadLogsRef.current?.();
                }
            } catch {
                // ignore invalid messages
            }
        };

        ws.onclose = (event) => {
            wsRef.current = null;
            if (event?.code === 1008) return;
            reconnectTimer.current = setTimeout(connectWs, WS_RECONNECT_DELAY);
        };

        ws.onerror = () => { /* onclose handled */ };

        wsRef.current = ws;
    }, [isSuperAdmin]);

    useEffect(() => {
        connectWs();
        return () => {
            clearTimeout(reconnectTimer.current);
            if (wsRef.current) {
                wsRef.current.onmessage = null;
                wsRef.current.onerror = null;
                wsRef.current.onclose = null;
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [connectWs]);

    const actionOptions = useMemo(() => {
        const values = new Set(logs.map((log) => log.action).filter(Boolean));
        return Array.from(values).sort();
    }, [logs]);

    const allSelected = logs.length > 0 && selectedIds.length === logs.length;

    const toggleSelectAll = () => {
        if (allSelected) {
            setSelectedIds([]);
        } else {
            setSelectedIds(logs.map((log) => log.id));
        }
    };

    const toggleSelectOne = (id) => {
        setSelectedIds((prev) => (
            prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
        ));
    };

    const handleDeleteSelected = async () => {
        if (!selectedIds.length) return;
        setLoading(true);
        setMessage('');
        try {
            const result = await ApiService.deleteAuditLogs(selectedIds);
            setMessage(`${result.deleted} log(s) supprimé(s)`);
            setSelectedIds([]);
            await loadLogs();
        } catch (error) {
            setMessage(`Erreur lors de la suppression: ${error.message}`);
        } finally {
            setLoading(false);
            setConfirmDelete(false);
        }
    };

    const openLog = (log) => {
        setSelectedLog(log);
        setShowTechnical(false);
    };

    if (!isSuperAdmin) {
        return (
            <div className="sage-bfc-container fade-in">
                <div className="sage-bfc-header">
                    <div>
                        <h2 className="sage-bfc-title">
                            <span className="sage-bfc-title-icon"><FiShield /></span>
                            Audit des actions
                        </h2>
                    </div>
                </div>
                <div className="sage-bfc-error"><div><strong>Accès refusé</strong><p>Accès réservé au superadmin.</p></div></div>
            </div>
        );
    }

    return (
        <div className="sage-bfc-container fade-in">
            <div className="sage-bfc-header">
                <div>
                    <h2 className="sage-bfc-title">
                        <span className="sage-bfc-title-icon"><FiShield /></span>
                        Audit des actions
                    </h2>
                    <p className="sage-bfc-subtitle">Journal des actions effectuées par les utilisateurs</p>
                </div>
                <div className="sage-bfc-nav">
                    <span className="sage-nav-btn active" style={{ cursor: 'default' }}>
                        Journal
                        <span className="ba-nav-count" title={`${total} log(s)`}>{total}</span>
                    </span>
                </div>
            </div>

            {message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

            <div className="ba-card">
            <div className="olea-form mb-4">
                <div className="form-row">
                    <div className="form-col form-col-lg">
                        <label>Recherche</label>
                        <input
                            type="text"
                            className="form-control"
                            value={search}
                            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                            placeholder="Utilisateur, module, action, entité..."
                        />
                    </div>
                    <div className="form-col">
                        <label>Module</label>
                        <select
                            className="form-control"
                            value={moduleFilter}
                            onChange={(e) => { setModuleFilter(e.target.value); setPage(1); }}
                        >
                            <option value="">Tous</option>
                            {moduleOptions.map((m) => (
                                <option key={m} value={m}>{m}</option>
                            ))}
                        </select>
                    </div>
                    <div className="form-col">
                        <label>Action</label>
                        <select
                            className="form-control"
                            value={actionFilter}
                            onChange={(e) => { setActionFilter(e.target.value); setPage(1); }}
                        >
                            <option value="">Toutes</option>
                            {actionOptions.map((a) => (
                                <option key={a} value={a}>{a}</option>
                            ))}
                        </select>
                    </div>
                    <div className="form-col form-col-btn" style={{ display: 'flex', alignItems: 'flex-end' }}>
                        <button
                            className="reco-icon-button reco-icon-button-danger"
                            type="button"
                            title="Supprimer la sélection"
                            aria-label="Supprimer la sélection"
                            onClick={() => setConfirmDelete(true)}
                            disabled={loading || selectedIds.length === 0}
                        >
                            <FiTrash2 />
                        </button>
                    </div>
                </div>
                <div className="form-row" style={{ marginTop: '0.75rem' }}>
                    <div className="form-col">
                        <label>Du</label>
                        <input
                            type="date"
                            className="form-control"
                            value={dateFrom}
                            onChange={(e) => { setDateFrom(e.target.value); setPage(1); }}
                        />
                    </div>
                    <div className="form-col">
                        <label>Au</label>
                        <input
                            type="date"
                            className="form-control"
                            value={dateTo}
                            onChange={(e) => { setDateTo(e.target.value); setPage(1); }}
                        />
                    </div>
                </div>
            </div>

            </div>

            <div className="ba-card">
            <div className="table-responsive">
                        <table className="olea-table audit-table">
                    <thead>
                        <tr>
                            <th className="text-center">
                                <input
                                    type="checkbox"
                                    checked={allSelected}
                                    onChange={toggleSelectAll}
                                />
                            </th>
                            <th>Date</th>
                            <th>Utilisateur</th>
                            <th>Module</th>
                            <th>Action</th>
                            <th>Entité</th>
                            <th>Résumé</th>
                            <th className="text-center">Détails</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="8" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Chargement...
                                </td>
                            </tr>
                        ) : logs.length === 0 ? (
                            <tr>
                                <td colSpan="8" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Aucun log trouvé
                                </td>
                            </tr>
                        ) : (
                            logs.map((log) => (
                                <tr key={log.id} className="ba-row audit-log-row" onClick={() => openLog(log)}>
                                    <td className="text-center" onClick={(e) => e.stopPropagation()}>
                                        <input
                                            type="checkbox"
                                            checked={selectedIds.includes(log.id)}
                                            onChange={() => toggleSelectOne(log.id)}
                                        />
                                    </td>
                                    <td><strong>{log.created_at ? new Date(log.created_at).toLocaleDateString('fr-FR') : '-'}</strong><small className="audit-muted-line">{log.created_at ? new Date(log.created_at).toLocaleTimeString('fr-FR') : ''}</small></td>
                                    <td><strong>{log.username || 'Utilisateur inconnu'}</strong><small className="audit-muted-line">ID : {log.user_id || '-'}</small></td>
                                    <td><span className="audit-module-badge">{displayModule(log.module)}</span></td>
                                    <td><span className={`audit-action-badge audit-action-${actionMeta(log.action).tone}`}>{actionMeta(log.action).label}</span></td>
                                    <td>{displayEntity(log)}</td>
                                    <td className="audit-summary-cell" title={detailSummary(log)}>{detailSummary(log)}</td>
                                    <td className="text-center">
                                        <button
                                            type="button"
                                            className="reco-icon-button"
                                            title="Voir les détails"
                                            aria-label="Voir les détails"
                                            onClick={(e) => { e.stopPropagation(); openLog(log); }}
                                        >
                                            <FiEye />
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {pages > 1 && (
                <div className="lignes-pagination">
                    <button
                        className="pagination-btn"
                        disabled={page === 1 || loading}
                        onClick={() => setPage(1)}
                        title="Première page"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                            <polyline points="11 17 6 12 11 7" />
                            <polyline points="18 17 13 12 18 7" />
                        </svg>
                    </button>
                    <button
                        className="pagination-btn"
                        disabled={page <= 1 || loading}
                        onClick={() => setPage((p) => p - 1)}
                        title="Page précédente"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                            <polyline points="15 18 9 12 15 6" />
                        </svg>
                    </button>

                    <div className="pagination-pages">
                        {Array.from({ length: Math.min(5, pages) }, (_, i) => {
                            let pageNumber;
                            if (pages <= 5) {
                                pageNumber = i + 1;
                            } else if (page <= 3) {
                                pageNumber = i + 1;
                            } else if (page >= pages - 2) {
                                pageNumber = pages - 4 + i;
                            } else {
                                pageNumber = page - 2 + i;
                            }
                            return (
                                <button
                                    key={pageNumber}
                                    className={`pagination-page ${page === pageNumber ? 'active' : ''}`}
                                    onClick={() => setPage(pageNumber)}
                                    disabled={loading}
                                >
                                    {pageNumber}
                                </button>
                            );
                        })}
                    </div>

                    <button
                        className="pagination-btn"
                        disabled={page >= pages || loading}
                        onClick={() => setPage((p) => p + 1)}
                        title="Page suivante"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                            <polyline points="9 18 15 12 9 6" />
                        </svg>
                    </button>
                    <button
                        className="pagination-btn"
                        disabled={page === pages || loading}
                        onClick={() => setPage(pages)}
                        title="Dernière page"
                    >
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '14px', height: '14px' }}>
                            <polyline points="13 17 18 12 13 7" />
                            <polyline points="6 17 11 12 6 7" />
                        </svg>
                    </button>
                </div>
            )}
            </div>

            {selectedLog && ReactDOM.createPortal(
                <div className="um-modal-overlay audit-log-overlay" onClick={() => setSelectedLog(null)}>
                    <div className="um-modal um-modal-wide audit-log-modal" onClick={(e) => e.stopPropagation()}>
                        <div className="um-modal-header audit-modal-heading">
                            <div>
                                <h3>Détails du log</h3>
                                <div className="audit-modal-subtitle">
                                    <span className={`audit-action-badge audit-action-${actionMeta(selectedLog.action).tone}`}>{actionMeta(selectedLog.action).label}</span>
                                    <span>{displayModule(selectedLog.module)}</span>
                                </div>
                            </div>
                            <button className="um-modal-close" onClick={() => setSelectedLog(null)}>×</button>
                        </div>
                        <div className="um-modal-body audit-modal-body">
                            <div className="audit-detail-grid">
                                <div className="audit-detail-card"><span><FiClock /> Date</span><strong>{displayDate(selectedLog.created_at)}</strong></div>
                                <div className="audit-detail-card"><span><FiUser /> Utilisateur</span><strong>{selectedLog.username || 'Utilisateur inconnu'} <small>(ID : {selectedLog.user_id || '-'})</small></strong></div>
                                <div className="audit-detail-card"><span><FiTag /> Entité</span><strong>{displayEntity(selectedLog)}</strong></div>
                                <div className="audit-detail-card"><span><FiDatabase /> Adresse IP</span><strong>{selectedLog.ip_address || '-'}</strong></div>
                            </div>
                            <section className="audit-detail-section">
                                <h4>Informations de l’opération</h4>
                                <div className="audit-detail-list">
                                    <div><span>Module</span><strong>{displayModule(selectedLog.module)}</strong></div>
                                    <div><span>Action</span><strong>{actionMeta(selectedLog.action).label}</strong></div>
                                    <div><span>Type d’entité</span><strong>{selectedLog.entity_type || '-'}</strong></div>
                                    <div><span>Identifiant</span><strong>{selectedLog.entity_id || '-'}</strong></div>
                                </div>
                            </section>
                            <section className="audit-detail-section">
                                <h4>Données associées</h4>
                                {detailEntries(selectedLog.detail).length ? (
                                    <div className="audit-detail-list">
                                        {detailEntries(selectedLog.detail).map(([key, value]) => (
                                            <div key={key}><span>{key.replaceAll('_', ' ')}</span><strong>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</strong></div>
                                        ))}
                                    </div>
                                ) : <p className="audit-empty-detail">Aucune donnée complémentaire.</p>}
                            </section>
                            <button type="button" className="audit-technical-toggle" onClick={() => setShowTechnical((value) => !value)}>
                                {showTechnical ? 'Masquer les données techniques' : 'Afficher les données techniques'}
                            </button>
                            {showTechnical && <pre className="audit-json-block">{JSON.stringify(selectedLog, null, 2)}</pre>}
                        </div>
                        <div className="um-modal-footer">
                            <button className="btn btn-secondary" onClick={() => setSelectedLog(null)}>
                                Fermer
                            </button>
                        </div>
                    </div>
                </div>,
                document.body
            )}

            {confirmDelete && ReactDOM.createPortal(
                <div className="sage-close-overlay" role="alertdialog" aria-modal="true"
                    onClick={() => !loading && setConfirmDelete(false)}>
                    <div className="sage-close-overlay-card ba-confirm" onClick={(e) => e.stopPropagation()}>
                        <h4>Supprimer les logs sélectionnés ?</h4>
                        <p><strong>{selectedIds.length}</strong> log(s) seront supprimés du journal d'audit.</p>
                        <p className="ba-confirm-warn">Cette action est définitive.</p>
                        <div className="ba-confirm-actions">
                            <button type="button" className="btn btn-secondary" onClick={() => setConfirmDelete(false)} disabled={loading}>Annuler</button>
                            <button type="button" className="btn btn-primary" onClick={handleDeleteSelected} disabled={loading}>
                                {loading ? 'Suppression…' : 'Supprimer'}
                            </button>
                        </div>
                    </div>
                </div>,
                document.body
            )}
        </div>
    );
}

export default AuditLogs;
