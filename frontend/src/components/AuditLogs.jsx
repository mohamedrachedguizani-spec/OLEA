import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';

function AuditLogs() {
    const { isSuperAdmin } = useAuth();
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');

    const [search, setSearch] = useState('');
    const [moduleFilter, setModuleFilter] = useState('');
    const [actionFilter, setActionFilter] = useState('');
    const [userIdFilter, setUserIdFilter] = useState('');
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');

    const [page, setPage] = useState(1);
    const [pageSize] = useState(25);
    const [total, setTotal] = useState(0);
    const [pages, setPages] = useState(1);

    const [selectedLog, setSelectedLog] = useState(null);

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
            if (userIdFilter) params.user_id = userIdFilter;
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
    }, [isSuperAdmin, search, page, pageSize, moduleFilter, actionFilter, userIdFilter, dateFrom, dateTo]);

    useEffect(() => {
        loadLogs();
    }, [loadLogs]);

    const moduleOptions = useMemo(() => {
        const values = new Set(logs.map((log) => log.module).filter(Boolean));
        return Array.from(values).sort();
    }, [logs]);

    const actionOptions = useMemo(() => {
        const values = new Set(logs.map((log) => log.action).filter(Boolean));
        return Array.from(values).sort();
    }, [logs]);

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
                    <div className="form-col">
                        <label>ID utilisateur</label>
                        <input
                            type="number"
                            className="form-control"
                            value={userIdFilter}
                            onChange={(e) => { setUserIdFilter(e.target.value); setPage(1); }}
                            placeholder="Ex: 12"
                        />
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
                                <td colSpan="6" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Chargement...
                                </td>
                            </tr>
                        ) : logs.length === 0 ? (
                            <tr>
                                <td colSpan="6" style={{ textAlign: 'center', padding: '1rem' }}>
                                    Aucun log trouvé
                                </td>
                            </tr>
                        ) : (
                            logs.map((log) => (
                                <tr key={log.id}>
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

            <div className="form-row config-pagination" style={{ marginTop: '1rem', alignItems: 'center' }}>
                <div className="form-col">
                    <span className="text-muted">
                        Page {page} / {pages}
                    </span>
                </div>
                <div className="form-col form-col-btn" style={{ display: 'flex', gap: '0.5rem' }}>
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                        disabled={page <= 1 || loading}
                    >
                        Précédent
                    </button>
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => setPage((p) => Math.min(pages, p + 1))}
                        disabled={page >= pages || loading}
                    >
                        Suivant
                    </button>
                </div>
            </div>

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
