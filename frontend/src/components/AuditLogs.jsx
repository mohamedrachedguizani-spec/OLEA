import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ApiService, { API_BASE_URL } from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const WS_URL = API_BASE_URL.replace(/^http/i, 'ws') + '/ws/live';
const WS_RECONNECT_DELAY = 3000;

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
            if (wsRef.current) { wsRef.current.close(); wsRef.current = null; }
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
        if (!window.confirm(`Supprimer ${selectedIds.length} log(s) sélectionné(s) ?`)) return;
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
        }
    };

    if (!isSuperAdmin) {
        return (
            <div className="olea-card fade-in">
                <div className="card-header">
                    <h2 className="card-title">
                        <span className="icon">🛡️</span>
                        Audit
                    </h2>
                </div>
                <div className="alert alert-danger slide-down">
                    Accès réservé au superadmin.
                </div>
            </div>
        );
    }

    return (
        <div className="olea-card fade-in">
            <div className="card-header">
                <div className="config-header">
                    <h2 className="card-title">
                        <span className="icon">🛡️</span>
                        Audit des actions
                    </h2>
                    <span className="badge badge-primary">{total}</span>
                </div>
            </div>

            {message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

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
                            className="btn btn-danger"
                            type="button"
                            title="Supprimer la sélection"
                            onClick={handleDeleteSelected}
                            disabled={loading || selectedIds.length === 0}
                        >
                            🗑️
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

            <div className="table-responsive">
                <table className="olea-table">
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
                            <th className="text-center">Détails</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="7" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Chargement...
                                </td>
                            </tr>
                        ) : logs.length === 0 ? (
                            <tr>
                                <td colSpan="7" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Aucun log trouvé
                                </td>
                            </tr>
                        ) : (
                            logs.map((log) => (
                                <tr key={log.id}>
                                    <td className="text-center">
                                        <input
                                            type="checkbox"
                                            checked={selectedIds.includes(log.id)}
                                            onChange={() => toggleSelectOne(log.id)}
                                        />
                                    </td>
                                    <td>{log.created_at ? new Date(log.created_at).toLocaleString('fr-FR') : '-'}</td>
                                    <td>{log.username || log.user_id || '-'}</td>
                                    <td>{log.module}</td>
                                    <td>{log.action}</td>
                                    <td>{[log.entity_type, log.entity_id].filter(Boolean).join(' / ') || '-'}</td>
                                    <td className="text-center">
                                        <button
                                            className="btn btn-sm btn-secondary"
                                            onClick={() => setSelectedLog(log)}
                                        >
                                            Voir
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

            {selectedLog && (
                <div className="um-modal-overlay" onClick={() => setSelectedLog(null)}>
                    <div className="um-modal um-modal-wide" onClick={(e) => e.stopPropagation()}>
                        <div className="um-modal-header">
                            <h3>Détails du log</h3>
                            <button className="um-modal-close" onClick={() => setSelectedLog(null)}>×</button>
                        </div>
                        <div className="um-modal-body" style={{ whiteSpace: 'pre-wrap' }}>
                            {JSON.stringify(selectedLog, null, 2)}
                        </div>
                        <div className="um-modal-footer">
                            <button className="btn btn-secondary" onClick={() => setSelectedLog(null)}>
                                Fermer
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default AuditLogs;
