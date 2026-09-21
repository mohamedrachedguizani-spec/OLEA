// src/components/RapprochementBancaire.jsx
import React, { useState, useRef, useEffect } from 'react';
import ReactDOM from 'react-dom';
import {
    FiCalendar,
    FiCreditCard,
    FiDownload,
    FiEye,
    FiFileText,
    FiSearch,
    FiTrash2,
    FiX,
} from 'react-icons/fi';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import './sage-bfc/SageBfcParser.css';

const getCurrentPeriod = () => {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
};

function ReconciliationSummary({ stats, formatAmount }) {
    const automationRate = Math.max(0, Math.min(100, Number(stats.automation_rate) || 0));
    return (
        <section className="reco-summary" aria-labelledby="reco-summary-title">
            <div className="reco-summary-heading">
                <div>
                    <span className="reco-opening-eyebrow">Vue de contrôle</span>
                    <h3 id="reco-summary-title">Synthèse du rapprochement</h3>
                </div>
                <span className={stats.discrepancies_count ? 'reco-summary-status warning' : 'reco-summary-status success'}>
                    {stats.discrepancies_count ? `${stats.discrepancies_count} écart(s) à traiter` : 'Aucun écart de montant'}
                </span>
            </div>
            <div className="reco-summary-body">
                <div className="reco-summary-volume">
                    <h4>Activité analysée</h4>
                    <dl>
                        <div><dt>Mouvements banque</dt><dd>{stats.total_bank_movements}</dd></div>
                        <div><dt>Écritures SAGE</dt><dd>{stats.total_sage_movements}</dd></div>
                        <div><dt>Rapprochées automatiquement</dt><dd>{stats.auto_reconciled_count}</dd></div>
                    </dl>
                </div>
                <div className="reco-summary-control">
                    <div className="reco-rate-line">
                        <div><span>Taux d’automatisation</span><strong>{automationRate.toFixed(2)} %</strong></div>
                        <div className="reco-progress" role="progressbar" aria-valuenow={automationRate} aria-valuemin="0" aria-valuemax="100">
                            <span style={{ width: `${automationRate}%` }} />
                        </div>
                    </div>
                    <div className="reco-discrepancy-line">
                        <div><span>Écarts de montant</span><strong>{stats.discrepancies_count}</strong></div>
                        <div><span>Montant cumulé</span><strong>{formatAmount(stats.total_discrepancy_amount)} TND</strong></div>
                    </div>
                </div>
            </div>
        </section>
    );
}

function OpeningBalanceControl({ context, formatAmount }) {
    if (!context) return null;
    const statusLabels = {
        conforme: 'Soldes de départ conformes',
        ecart: 'Écart initial détecté',
        unverifiable: 'Contrôle initial non vérifiable',
    };
    const displayBalance = (balance) => balance?.amount === null || balance?.amount === undefined
        ? 'Non détecté'
        : `${formatAmount(balance.amount)} TND`;

    return (
        <section className={`reco-opening-panel reco-opening-${context.opening_status}`}>
            <div className="reco-opening-header">
                <div>
                    <span className="reco-opening-eyebrow">Contrôle préalable</span>
                    <h3>{statusLabels[context.opening_status] || 'Contrôle des soldes de départ'}</h3>
                    <p>{context.bank_journal} · {context.account_code} · Période {context.period}</p>
                </div>
                <span className="reco-opening-badge">{context.opening_status === 'conforme' ? 'Conforme' : context.opening_status === 'ecart' ? 'À vérifier' : 'Incomplet'}</span>
            </div>
            <div className="reco-opening-values">
                <div>
                    <span>Solde initial SAGE</span>
                    <strong>{displayBalance(context.sage_opening)}</strong>
                    <small>{context.sage_opening?.label || 'Libellé non trouvé'}</small>
                </div>
                <div>
                    <span>Solde de départ banque</span>
                    <strong>{displayBalance(context.bank_opening)}</strong>
                    <small>{context.bank_opening?.label || 'Libellé non trouvé'}</small>
                </div>
                <div>
                    <span>Écart initial</span>
                    <strong>{context.opening_difference === null || context.opening_difference === undefined ? 'Non calculable' : `${formatAmount(context.opening_difference)} TND`}</strong>
                    <small>Banque - SAGE</small>
                </div>
            </div>
            {context.opening_status === 'ecart' && (
                <p className="reco-opening-warning">L'analyse a été poursuivie, mais cet écart doit être vérifié avant la validation définitive du rapprochement.</p>
            )}
        </section>
    );
}

function RapprochementBancaire({ navigationTarget }) {
    const { has } = useAuth();
    const [workspaceView, setWorkspaceView] = useState('new');
    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [exportingPdf, setExportingPdf] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    
    // Files
    const [sageFile, setSageFile] = useState(null);
    const [bankFile, setBankFile] = useState(null);
    const [bankAccounts, setBankAccounts] = useState([]);
    const [bankJournal, setBankJournal] = useState('');
    const [period, setPeriod] = useState(getCurrentPeriod);

    // Drag active states
    const [dragActiveSage, setDragActiveSage] = useState(false);
    const [dragActiveBank, setDragActiveBank] = useState(false);

    const sageInputRef = useRef(null);
    const bankInputRef = useRef(null);

    // Reconciliation results
    const [result, setResult] = useState(null);
    const [activeTab, setActiveTab] = useState('reconciled'); // 'reconciled' | 'discrepancies' | 'bank_only' | 'sage_only'
    const [history, setHistory] = useState({ items: [], page: 1, page_size: 10, total: 0, total_pages: 0 });
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyPage, setHistoryPage] = useState(1);
    const [historyJournal, setHistoryJournal] = useState('');
    const [historyPeriod, setHistoryPeriod] = useState('');
    const [historySearch, setHistorySearch] = useState('');
    const [historyRefresh, setHistoryRefresh] = useState(0);
    const [deletingHistoryId, setDeletingHistoryId] = useState(null);
    const [pdfPreview, setPdfPreview] = useState({ open: false, url: '', blob: null, filename: '' });

    useEffect(() => {
        ApiService.getReconciliationBankAccounts()
            .then((items) => {
                const availableAccounts = Array.isArray(items) ? items : [];
                setBankAccounts(availableAccounts);
            })
            .catch((err) => setError(err.message || 'Impossible de charger les comptes bancaires.'));
    }, []);

    useEffect(() => {
        const requestedView = navigationTarget?.params?.view;
        const requestedResultId = Number(navigationTarget?.params?.result);

        if (['reconciled', 'discrepancies', 'bank_only', 'sage_only'].includes(requestedView)) {
            setActiveTab(requestedView);
        }
        if (!Number.isInteger(requestedResultId) || requestedResultId <= 0) return undefined;

        let cancelled = false;
        setLoading(true);
        setError('');
        ApiService.getReconciliationResult(requestedResultId)
            .then((data) => {
                if (cancelled) return;
                setResult(data);
                if (data.context?.bank_journal) setBankJournal(data.context.bank_journal);
                if (data.context?.period) setPeriod(data.context.period);
                setStep(2);
                setWorkspaceView('new');
                setSuccess('Le rapprochement concerné a été chargé.');
            })
            .catch((err) => {
                if (!cancelled) setError(err.message || 'Impossible de charger le rapprochement concerné.');
            })
            .finally(() => {
                if (!cancelled) setLoading(false);
            });

        return () => {
            cancelled = true;
        };
    }, [navigationTarget]);
    const [filterQuery, setFilterQuery] = useState('');

    useEffect(() => {
        if (workspaceView !== 'history') return undefined;
        let cancelled = false;
        const timer = setTimeout(async () => {
            setHistoryLoading(true);
            try {
                const data = await ApiService.getReconciliationHistory({
                    page: historyPage,
                    pageSize: 10,
                    journal: historyJournal,
                    period: historyPeriod,
                    search: historySearch,
                });
                if (!cancelled) setHistory(data);
            } catch (err) {
                if (!cancelled) setError(err.message || "Impossible de charger l'historique.");
            } finally {
                if (!cancelled) setHistoryLoading(false);
            }
        }, 250);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
    }, [workspaceView, historyPage, historyJournal, historyPeriod, historySearch, historyRefresh]);

    useEffect(() => () => {
        if (pdfPreview.url) URL.revokeObjectURL(pdfPreview.url);
    }, [pdfPreview.url]);

    // Disparaître les notifications après 2 secondes
    useEffect(() => {
        if (success) {
            const timer = setTimeout(() => setSuccess(''), 3000);
            return () => clearTimeout(timer);
        }
    }, [success]);

    useEffect(() => {
        if (error) {
            const timer = setTimeout(() => setError(''), 3000);
            return () => clearTimeout(timer);
        }
    }, [error]);

    const handleDragSage = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActiveSage(true);
        } else if (e.type === "dragleave") {
            setDragActiveSage(false);
        }
    };

    const handleDropSage = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActiveSage(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setSageFile(e.dataTransfer.files[0]);
        }
    };

    const handleDragBank = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActiveBank(true);
        } else if (e.type === "dragleave") {
            setDragActiveBank(false);
        }
    };

    const handleDropBank = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActiveBank(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setBankFile(e.dataTransfer.files[0]);
        }
    };

    const handleLaunchReconciliation = async (e) => {
        e.preventDefault();
        setError('');
        setSuccess('');
        
        if (!sageFile) {
            setError('Veuillez sélectionner le fichier Sage.');
            return;
        }
        if (!bankFile) {
            setError('Veuillez sélectionner le relevé bancaire.');
            return;
        }
        if (!bankJournal) {
            setError('Veuillez sélectionner le compte bancaire (journal).');
            return;
        }
        if (!period) {
            setError('Veuillez sélectionner la période du rapprochement.');
            return;
        }

        const formData = new FormData();
        formData.append('sage_file', sageFile);
        formData.append('bank_file', bankFile);
        formData.append('bank_journal', bankJournal);
        formData.append('period', period);
        formData.append('date_tolerance_days', 3);
        formData.append('match_on_label', 'false');
        formData.append('match_on_date', 'false');

        setLoading(true);
        try {
            const data = await ApiService.compareReconciliation(formData);
            setResult(data);
            setSuccess('Rapprochement effectué avec succès.');
            setStep(2);
            setHistoryPage(1);
        } catch (err) {
            setError(err.message || 'Une erreur est survenue lors du rapprochement.');
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setSageFile(null);
        setBankFile(null);
        setBankJournal('');
        setPeriod(getCurrentPeriod());
        setResult(null);
        setError('');
        setSuccess('');
        setFilterQuery('');
        if (sageInputRef.current) sageInputRef.current.value = '';
        if (bankInputRef.current) bankInputRef.current.value = '';
        setStep(1);
    };

    const closePdfPreview = () => {
        setPdfPreview({ open: false, url: '', blob: null, filename: '' });
    };

    const openPdfPreview = async (resultToExport = result) => {
        if (!resultToExport || exportingPdf) return;

        setError('');
        setSuccess('');
        setExportingPdf(true);
        try {
            const pdfBlob = await ApiService.exportReconciliationPdf({
                result: resultToExport,
                sage_filename: sageFile?.name || resultToExport.context?.sage_filename || null,
                bank_filename: bankFile?.name || resultToExport.context?.bank_filename || null,
            });
            const previewUrl = URL.createObjectURL(pdfBlob);
            const contextSuffix = resultToExport.context
                ? `${resultToExport.context.bank_journal}_${resultToExport.context.period}`
                : new Date().toISOString().slice(0, 10);
            setPdfPreview({
                open: true,
                url: previewUrl,
                blob: pdfBlob,
                filename: `rapprochement_bancaire_${contextSuffix}.pdf`,
            });
        } catch (err) {
            setError(err.message || 'Une erreur est survenue lors de la prévisualisation du PDF.');
        } finally {
            setExportingPdf(false);
        }
    };

    const downloadPreviewedPdf = () => {
        if (!pdfPreview.blob) return;
        const link = document.createElement('a');
        link.href = pdfPreview.url;
        link.download = pdfPreview.filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setSuccess('Le rapport PDF a été téléchargé avec succès.');
        closePdfPreview();
    };

    const openHistoryResult = async (resultId, previewPdf = false) => {
        setLoading(true);
        setError('');
        try {
            const data = await ApiService.getReconciliationResult(resultId);
            if (previewPdf) {
                await openPdfPreview(data);
                return;
            }
            setResult(data);
            setBankJournal(data.context?.bank_journal || '');
            setPeriod(data.context?.period || period);
            setActiveTab('reconciled');
            setFilterQuery('');
            setStep(2);
            setWorkspaceView('new');
        } catch (err) {
            setError(err.message || 'Impossible de charger ce rapprochement.');
        } finally {
            setLoading(false);
        }
    };

    const deleteHistoryResult = async (item) => {
        const label = `${item.bank_journal || 'Compte bancaire'} · ${item.period || 'période non renseignée'}`;
        if (!window.confirm(`Supprimer définitivement le rapprochement ${label} de l’historique ?`)) return;
        setDeletingHistoryId(item.id);
        setError('');
        try {
            const response = await ApiService.deleteReconciliationResult(item.id);
            setSuccess(response.message || 'Le rapprochement a été supprimé.');
            if (history.items.length === 1 && historyPage > 1) {
                setHistoryPage((value) => value - 1);
            } else {
                setHistoryRefresh((value) => value + 1);
            }
        } catch (err) {
            setError(err.message || 'Impossible de supprimer ce rapprochement.');
        } finally {
            setDeletingHistoryId(null);
        }
    };

    const formatAmount = (val) => {
        if (val === undefined || val === null) return '-';
        return new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(val);
    };

    const formatDate = (dateString) => {
        if (!dateString) return '-';
        const d = new Date(dateString);
        return d.toLocaleDateString('fr-FR');
    };

    const formatFileSize = (bytes) => {
        if (!bytes) return '0 B';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    const filterItems = (list, type) => {
        if (!filterQuery) return list;
        const q = filterQuery.toLowerCase();
        
        return list.filter(item => {
            if (type === 'reconciled' || type === 'discrepancies') {
                const bText = (item.bank.libelle || '').toLowerCase();
                const bAmt = String(item.bank.amount);
                const sText = (item.sage.libelle_ecriture || '').toLowerCase();
                const sAmt = String(item.sage.amount);
                return bText.includes(q) || bAmt.includes(q) || sText.includes(q) || sAmt.includes(q);
            } else if (type === 'bank_only') {
                return (item.libelle || '').toLowerCase().includes(q) || String(item.amount).includes(q);
            } else if (type === 'sage_only') {
                return (item.libelle_ecriture || '').toLowerCase().includes(q) || String(item.amount).includes(q);
            }
            return true;
        });
    };

    const renderStep1 = () => (
        <form onSubmit={handleLaunchReconciliation} className="sage-upload-section mb-4" style={{ padding: '2rem 1.5rem', background: 'var(--bg-card)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-lg)' }}>
            <div className="reco-context-grid">
                <div className="form-group">
                    <label>
                        <span className="icon bank-form-icon"><FiCreditCard /></span> Compte bancaire (journal)
                    </label>
                    <select className="form-control" value={bankJournal} onChange={(event) => setBankJournal(event.target.value)} required>
                        <option value="">Sélectionner</option>
                        {bankAccounts.map((item) => (
                            <option key={item.journal} value={item.journal}>
                                {item.journal} - {item.account_code}
                            </option>
                        ))}
                    </select>
                </div>
                <div className="form-group">
                    <label>
                        <span className="icon bank-form-icon"><FiCalendar /></span> Période (mois et année)
                    </label>
                    <input type="month" className="form-control" value={period} onChange={(event) => setPeriod(event.target.value)} required />
                </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '1.5rem' }}>
                
                {/* Sage Upload Box */}
                <div className="form-group">
                    <label style={{ fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '0.5rem' }}>
                        Fichier Grand Livre Sage (CSV ou Excel)
                    </label>
                    <div
                        className={`sage-dropzone ${dragActiveSage ? 'drag-active' : ''} ${sageFile ? 'has-file' : ''}`}
                        onDragEnter={handleDragSage}
                        onDragLeave={handleDragSage}
                        onDragOver={handleDragSage}
                        onDrop={handleDropSage}
                        onClick={() => !sageFile && sageInputRef.current?.click()}
                        style={{
                            position: 'relative',
                            border: '2px dashed var(--primary-300)',
                            borderRadius: 'var(--radius-lg)',
                            padding: '3rem 2rem',
                            textAlign: 'center',
                            cursor: sageFile ? 'default' : 'pointer',
                            background: 'linear-gradient(135deg, rgba(183, 72, 43, 0.03) 0%, rgba(47, 52, 58, 0.02) 100%)',
                            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
                        }}
                    >
                        <input
                            ref={sageInputRef}
                            type="file"
                            accept=".csv,.xlsx,.xls"
                            onChange={(e) => setSageFile(e.target.files?.[0] || null)}
                            style={{ display: 'none' }}
                        />
                        {!sageFile ? (
                            <div className="dropzone-content">
                                <div className={`dropzone-icon ${dragActiveSage ? 'bounce' : ''}`}>
                                    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '48px', height: '48px', margin: '0 auto 1rem auto' }}>
                                        <rect x="8" y="8" width="48" height="48" rx="8" strokeDasharray="6 3" />
                                        <path d="M32 22v20M22 32h20" strokeWidth="3" strokeLinecap="round" />
                                    </svg>
                                </div>
                                <h3 className="dropzone-title" style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                                    Glissez-déposez le fichier Sage ici
                                </h3>
                                <p className="dropzone-hint" style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: 0 }}>
                                    ou <span className="dropzone-link" style={{ color: 'var(--primary-500)', fontWeight: 600, textDecoration: 'underline' }}>parcourez vos fichiers</span>
                                </p>
                            </div>
                        ) : (
                            <div className="dropzone-file-preview" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1.5rem', width: '100%' }}>
                                <div className="file-preview-icon" style={{ fontSize: '2.5rem' }}>
                                    {sageFile.name.endsWith('.pdf') ? '📕' : sageFile.name.endsWith('.csv') ? '📗' : '📗'}
                                </div>
                                <div className="file-preview-info" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                                    <span className="file-preview-name" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{sageFile.name}</span>
                                    <span className="file-preview-size" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{formatFileSize(sageFile.size)}</span>
                                </div>
                                <button
                                    type="button"
                                    className="file-preview-remove"
                                    onClick={(e) => { e.stopPropagation(); setSageFile(null); if (sageInputRef.current) sageInputRef.current.value = ''; }}
                                    title="Retirer le fichier"
                                    style={{
                                        background: 'none',
                                        border: 'none',
                                        color: 'var(--text-muted)',
                                        cursor: 'pointer',
                                        padding: '0.5rem',
                                        borderRadius: '50%',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        transition: 'all 0.2s'
                                    }}
                                >
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '18px', height: '18px' }}>
                                        <line x1="18" y1="6" x2="6" y2="18"/>
                                        <line x1="6" y1="6" x2="18" y2="18"/>
                                    </svg>
                                </button>
                            </div>
                        )}
                    </div>
                </div>

                {/* Bank Statement Upload Box */}
                <div className="form-group">
                    <label style={{ fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '0.5rem' }}>
                         Relevé Bancaire (PDF, Excel, CSV)
                    </label>
                    <div
                        className={`sage-dropzone ${dragActiveBank ? 'drag-active' : ''} ${bankFile ? 'has-file' : ''}`}
                        onDragEnter={handleDragBank}
                        onDragLeave={handleDragBank}
                        onDragOver={handleDragBank}
                        onDrop={handleDropBank}
                        onClick={() => !bankFile && bankInputRef.current?.click()}
                        style={{
                            position: 'relative',
                            border: '2px dashed var(--primary-300)',
                            borderRadius: 'var(--radius-lg)',
                            padding: '3rem 2rem',
                            textAlign: 'center',
                            cursor: bankFile ? 'default' : 'pointer',
                            background: 'linear-gradient(135deg, rgba(183, 72, 43, 0.03) 0%, rgba(47, 52, 58, 0.02) 100%)',
                            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)'
                        }}
                    >
                        <input
                            ref={bankInputRef}
                            type="file"
                            accept=".pdf,.csv,.xlsx,.xls"
                            onChange={(e) => setBankFile(e.target.files?.[0] || null)}
                            style={{ display: 'none' }}
                        />
                        {!bankFile ? (
                            <div className="dropzone-content">
                                <div className={`dropzone-icon ${dragActiveBank ? 'bounce' : ''}`}>
                                    <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '48px', height: '48px', margin: '0 auto 1rem auto' }}>
                                        <rect x="8" y="8" width="48" height="48" rx="8" strokeDasharray="6 3" />
                                        <path d="M32 22v20M22 32h20" strokeWidth="3" strokeLinecap="round" />
                                    </svg>
                                </div>
                                <h3 className="dropzone-title" style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                                    Glissez-déposez votre relevé bancaire ici
                                </h3>
                                <p className="dropzone-hint" style={{ fontSize: '0.875rem', color: 'var(--text-muted)', margin: 0 }}>
                                    ou <span className="dropzone-link" style={{ color: 'var(--primary-500)', fontWeight: 600, textDecoration: 'underline' }}>parcourez vos fichiers</span>
                                </p>
                            </div>
                        ) : (
                            <div className="dropzone-file-preview" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '1.5rem', width: '100%' }}>
                                <div className="file-preview-icon" style={{ fontSize: '2.5rem' }}>
                                    {bankFile.name.endsWith('.pdf') ? '📕' : bankFile.name.endsWith('.csv') ? '📗' : '📗'}
                                </div>
                                <div className="file-preview-info" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                                    <span className="file-preview-name" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>{bankFile.name}</span>
                                    <span className="file-preview-size" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{formatFileSize(bankFile.size)}</span>
                                </div>
                                <button
                                    type="button"
                                    className="file-preview-remove"
                                    onClick={(e) => { e.stopPropagation(); setBankFile(null); if (bankInputRef.current) bankInputRef.current.value = ''; }}
                                    title="Retirer le fichier"
                                    style={{
                                        background: 'none',
                                        border: 'none',
                                        color: 'var(--text-muted)',
                                        cursor: 'pointer',
                                        padding: '0.5rem',
                                        borderRadius: '50%',
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        transition: 'all 0.2s'
                                    }}
                                >
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: '18px', height: '18px' }}>
                                        <line x1="18" y1="6" x2="6" y2="18"/>
                                        <line x1="6" y1="6" x2="18" y2="18"/>
                                    </svg>
                                </button>
                            </div>
                        )}
                    </div>
                </div>

            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
                <button type="submit" className="btn btn-primary" style={{ padding: '0.75rem 2.5rem', fontSize: '1rem' }} disabled={loading || !has('rapprochement_bancaire.run')}>
                    {loading ? (
                        <>
                            <span className="spinner" style={{ marginRight: '0.5rem' }} />
                            Rapprochement en cours...
                        </>
                    ) : (
                        <>
                             Lancer l'analyse
                        </>
                    )}
                </button>
            </div>
        </form>
    );

    const renderHistory = () => (
        <section className="reco-history" aria-labelledby="reco-history-title">
            <div className="reco-history-header">
                <div>
                    <span className="reco-opening-eyebrow">Traçabilité</span>
                    <h3 id="reco-history-title">Rapprochements réalisés</h3>
                    <p>Retrouvez, consultez et rééditez les analyses enregistrées.</p>
                </div>
                <span className="reco-history-count">{history.total} résultat{history.total > 1 ? 's' : ''}</span>
            </div>
            <div className="reco-history-filters">
                <label className="reco-search-field">
                    <FiSearch aria-hidden="true" />
                    <input
                        type="search"
                        value={historySearch}
                        onChange={(event) => { setHistorySearch(event.target.value); setHistoryPage(1); }}
                        placeholder="Fichier, compte ou utilisateur..."
                        aria-label="Rechercher dans l'historique"
                    />
                </label>
                <select value={historyJournal} onChange={(event) => { setHistoryJournal(event.target.value); setHistoryPage(1); }} aria-label="Filtrer par journal">
                    <option value="">Tous les journaux</option>
                    {bankAccounts.map((item) => <option key={item.journal} value={item.journal}>{item.journal} · {item.account_code}</option>)}
                </select>
                <input type="month" value={historyPeriod} onChange={(event) => { setHistoryPeriod(event.target.value); setHistoryPage(1); }} aria-label="Filtrer par période" />
                {(historyJournal || historyPeriod || historySearch) && (
                    <button type="button" className="btn btn-secondary" onClick={() => { setHistoryJournal(''); setHistoryPeriod(''); setHistorySearch(''); setHistoryPage(1); }}>
                        Réinitialiser
                    </button>
                )}
            </div>
            <div className="reco-history-table-wrap">
                <table className="reco-history-table">
                    <thead>
                        <tr>
                            <th>Date</th><th>Compte bancaire</th><th>Période</th><th>Fichiers analysés</th>
                            <th>Automatisation</th><th>Écarts</th><th>Contrôle initial</th><th>Réalisé par</th><th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {historyLoading && <tr><td colSpan="9" className="reco-history-empty">Chargement de l’historique…</td></tr>}
                        {!historyLoading && history.items.map((item) => (
                            <tr key={item.id}>
                                <td><strong>{new Date(item.created_at).toLocaleDateString('fr-FR')}</strong><small>{new Date(item.created_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}</small></td>
                                <td><strong>{item.bank_journal || '-'}</strong><small>{item.account_code || '-'}</small></td>
                                <td>{item.period || '-'}</td>
                                <td className="reco-history-files"><span title={item.sage_filename}>{item.sage_filename || '-'}</span><small title={item.bank_filename}>{item.bank_filename || '-'}</small></td>
                                <td><strong>{Number(item.automation_rate || 0).toFixed(2)} %</strong><small>{item.auto_reconciled_count} rapprochement(s)</small></td>
                                <td><strong className={item.discrepancies_count ? 'reco-text-warning' : 'reco-text-success'}>{item.discrepancies_count}</strong><small>{formatAmount(item.total_discrepancy_amount)} TND</small></td>
                                <td><span className={`reco-history-status ${item.opening_status || 'unverifiable'}`}>{item.opening_status === 'conforme' ? 'Conforme' : item.opening_status === 'ecart' ? 'À vérifier' : 'Incomplet'}</span></td>
                                <td>{item.created_by || '-'}</td>
                                <td>
                                    <div className="reco-history-actions">
                                        <button type="button" className="reco-icon-button" title="Consulter" aria-label="Consulter le rapprochement" onClick={() => openHistoryResult(item.id)}><FiEye /></button>
                                        {has('rapprochement_bancaire.export_pdf') && <button type="button" className="reco-icon-button" title="Prévisualiser le PDF" aria-label="Prévisualiser le PDF" onClick={() => openHistoryResult(item.id, true)}><FiFileText /></button>}
                                        <button
                                            type="button"
                                            className="reco-icon-button reco-icon-button-danger"
                                            title="Supprimer"
                                            aria-label="Supprimer le rapprochement"
                                            disabled={deletingHistoryId === item.id}
                                            onClick={() => deleteHistoryResult(item)}
                                        >
                                            {deletingHistoryId === item.id ? <span className="spinner" /> : <FiTrash2 />}
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                        {!historyLoading && history.items.length === 0 && <tr><td colSpan="9" className="reco-history-empty">Aucun rapprochement ne correspond aux critères.</td></tr>}
                    </tbody>
                </table>
            </div>
            {history.total_pages > 1 && (
                <div className="reco-history-pagination">
                    <button type="button" className="btn btn-secondary" disabled={historyPage <= 1} onClick={() => setHistoryPage((value) => value - 1)}>Précédent</button>
                    <span>Page {history.page} sur {history.total_pages}</span>
                    <button type="button" className="btn btn-secondary" disabled={historyPage >= history.total_pages} onClick={() => setHistoryPage((value) => value + 1)}>Suivant</button>
                </div>
            )}
        </section>
    );

    const renderStep2 = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="reco-result-toolbar">
                <div>
                    <span>Résultat du rapprochement</span>
                    <strong>{result.context?.bank_journal || '-'} · {result.context?.period || '-'}</strong>
                </div>
                <button type="button" className="btn btn-primary" onClick={() => openPdfPreview()} disabled={exportingPdf || !has('rapprochement_bancaire.export_pdf')}>
                    {exportingPdf ? <><span className="spinner" /> Préparation…</> : <><FiDownload aria-hidden="true" /> EXPORT PDF</>}
                </button>
            </div>
            <OpeningBalanceControl context={result.context} formatAmount={formatAmount} />

            <ReconciliationSummary stats={result.stats} formatAmount={formatAmount} />

            {/* Navigation Tabs and Search inside Results */}
            <div className="card shadow-sm" style={{ padding: '1.25rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.75rem' }}>
                    {/* Tabs */}
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                            onClick={() => setActiveTab('reconciled')}
                            className={`btn ${activeTab === 'reconciled' ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}
                        >
                            Rapprochés ({result.reconciled.length})
                        </button>
                        <button
                            onClick={() => setActiveTab('discrepancies')}
                            className={`btn ${activeTab === 'discrepancies' ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}
                        >
                            Écarts ({result.discrepancies.length})
                        </button>
                        <button
                            onClick={() => setActiveTab('bank_only')}
                            className={`btn ${activeTab === 'bank_only' ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}
                        >
                            Banque uniquement ({result.bank_only.length})
                        </button>
                        <button
                            onClick={() => setActiveTab('sage_only')}
                            className={`btn ${activeTab === 'sage_only' ? 'btn-primary' : 'btn-secondary'}`}
                            style={{ padding: '0.4rem 1rem', fontSize: '0.85rem' }}
                        >
                            Sage uniquement ({result.sage_only.length})
                        </button>
                    </div>
                    
                    {/* Search box */}
                    <div style={{ minWidth: '250px' }}>
                        <input
                            type="text"
                            placeholder="Rechercher par libellé ou montant..."
                            className="form-control form-control-sm"
                            value={filterQuery}
                            onChange={(e) => setFilterQuery(e.target.value)}
                            style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
                        />
                    </div>
                </div>

                {/* Side-by-Side split layout headers */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: '0.5rem', background: 'var(--bg-muted)', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '0.5rem' }}>
                    <div style={{ textAlign: 'left' }}> COMPTABILITÉ SAGE (Écritures)</div>
                    <div style={{ textAlign: 'center' }}>⇅</div>
                    <div style={{ textAlign: 'left' }}> EXTRACT BANCAIRE (Mouvements)</div>
                </div>

                {/* Total Summary Row showing Debit / Credit equivalences */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: '0.5rem', background: '#fafaf9', border: '1px solid var(--border-light)', padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', color: 'var(--text-primary)', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Totaux Sage :</strong></div>
                        <div>
                            <span style={{ marginRight: '1.5rem' }}>Débit: <strong style={{ color: '#1f9d55' }}>{formatAmount(result.stats.sage_total_debit)} TND</strong></span>
                            <span>Crédit: <strong style={{ color: 'var(--olea-terracotta)' }}>{formatAmount(result.stats.sage_total_credit)} TND</strong></span>
                        </div>
                    </div>
                    <div style={{ textAlign: 'center', fontWeight: 'bold', color: 'var(--text-muted)' }}>⇄</div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div><strong style={{ color: 'var(--text-muted)' }}>Totaux Banque :</strong></div>
                        <div>
                            <span style={{ marginRight: '1.5rem' }}>Débit: <strong style={{ color: 'var(--olea-terracotta)' }}>{formatAmount(result.stats.bank_total_debit)} TND</strong></span>
                            <span>Crédit: <strong style={{ color: '#1f9d55' }}>{formatAmount(result.stats.bank_total_credit)} TND</strong></span>
                        </div>
                    </div>
                </div>

                {/* Grid Columns Titles */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: '0.5rem', padding: '0 1rem', fontWeight: 600, fontSize: '0.8rem', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.5rem', marginBottom: '0.5rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem' }}>
                        <div>Date Écr.</div>
                        <div>Libellé écriture</div>
                        <div>Référence</div>
                        <div style={{ textAlign: 'right' }}>Débit</div>
                        <div style={{ textAlign: 'right' }}>Crédit</div>
                    </div>
                    <div style={{ textAlign: 'center' }}>-</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem' }}>
                        <div>Date Op.</div>
                        <div>Libellé</div>
                        <div>Référence</div>
                        <div style={{ textAlign: 'right' }}>Débit</div>
                        <div style={{ textAlign: 'right' }}>Crédit</div>
                    </div>
                </div>

                {/* List Items Container */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', maxHeight: '500px', overflowY: 'auto', paddingRight: '0.25rem' }}>
                    
                    {/* TAB: Reconciled Pairs */}
                    {activeTab === 'reconciled' && filterItems(result.reconciled, 'reconciled').map((pair, idx) => (
                        <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: '0.5rem', padding: '0.6rem 1rem', background: idx % 2 === 0 ? 'var(--bg-card)' : '#fbfbfb', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', alignItems: 'center' }}>
                            {/* Left: Sage */}
                            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem', color: 'var(--text-primary)' }}>
                                <div style={{ color: 'var(--text-secondary)' }}>{formatDate(pair.sage.date_ecriture)}</div>
                                <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={pair.sage.libelle_ecriture}>{pair.sage.libelle_ecriture}</div>
                                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-muted)' }} title={pair.sage.reference_piece || '-'}>{pair.sage.reference_piece || '-'}</div>
                                <div style={{ textAlign: 'right', fontWeight: pair.sage.debit > 0 ? 600 : 400 }}>{pair.sage.debit > 0 ? formatAmount(pair.sage.debit) : '-'}</div>
                                <div style={{ textAlign: 'right', fontWeight: pair.sage.credit > 0 ? 600 : 400 }}>{pair.sage.credit > 0 ? formatAmount(pair.sage.credit) : '-'}</div>
                            </div>
                            {/* Middle connector */}
                            <div style={{ textAlign: 'center' }}>
                                <span style={{ background: '#def7ec', color: '#1f9d55', padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: '0.7rem', fontWeight: 'bold' }}>
                                    ✓
                                </span>
                            </div>
                            {/* Right: Bank */}
                            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem', color: 'var(--text-primary)' }}>
                                <div style={{ color: 'var(--text-secondary)' }}>{formatDate(pair.bank.date_operation)}</div>
                                <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={pair.bank.libelle}>{pair.bank.libelle}</div>
                                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-muted)' }} title={pair.bank.reference || '-'}>{pair.bank.reference || '-'}</div>
                                <div style={{ textAlign: 'right', fontWeight: pair.bank.debit > 0 ? 600 : 400 }}>{pair.bank.debit > 0 ? formatAmount(pair.bank.debit) : '-'}</div>
                                <div style={{ textAlign: 'right', fontWeight: pair.bank.credit > 0 ? 600 : 400 }}>{pair.bank.credit > 0 ? formatAmount(pair.bank.credit) : '-'}</div>
                            </div>
                        </div>
                    ))}

                    {/* TAB: Discrepancies */}
                    {activeTab === 'discrepancies' && filterItems(result.discrepancies, 'discrepancies').map((pair, idx) => (
                        <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: '0.5rem', padding: '0.6rem 1rem', background: '#fff9f9', border: '1px solid #ffd8d8', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', alignItems: 'center' }}>
                            {/* Left: Sage */}
                            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem', color: 'var(--text-primary)' }}>
                                <div style={{ color: 'var(--text-secondary)' }}>{formatDate(pair.sage.date_ecriture)}</div>
                                <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={pair.sage.libelle_ecriture}>{pair.sage.libelle_ecriture}</div>
                                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-muted)' }}>{pair.sage.reference_piece || '-'}</div>
                                <div style={{ textAlign: 'right', color: 'var(--primary-600)', fontWeight: 600 }}>{pair.sage.debit > 0 ? formatAmount(pair.sage.debit) : '-'}</div>
                                <div style={{ textAlign: 'right', color: 'var(--primary-600)', fontWeight: 600 }}>{pair.sage.credit > 0 ? formatAmount(pair.sage.credit) : '-'}</div>
                            </div>
                            {/* Middle connector with discrepancy amount */}
                            <div style={{ textAlign: 'center' }}>
                                <span style={{ background: '#fde8e8', color: '#b7482b', padding: '0.2rem 0.4rem', borderRadius: '4px', fontSize: '0.65rem', fontWeight: 'bold' }}>
                                    Δ {formatAmount(pair.difference)}
                                </span>
                            </div>
                            {/* Right: Bank */}
                            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem', color: 'var(--text-primary)' }}>
                                <div style={{ color: 'var(--text-secondary)' }}>{formatDate(pair.bank.date_operation)}</div>
                                <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={pair.bank.libelle}>{pair.bank.libelle}</div>
                                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-muted)' }}>{pair.bank.reference || '-'}</div>
                                <div style={{ textAlign: 'right', color: 'var(--primary-600)', fontWeight: 600 }}>{pair.bank.debit > 0 ? formatAmount(pair.bank.debit) : '-'}</div>
                                <div style={{ textAlign: 'right', color: 'var(--primary-600)', fontWeight: 600 }}>{pair.bank.credit > 0 ? formatAmount(pair.bank.credit) : '-'}</div>
                            </div>
                        </div>
                    ))}

                    {/* TAB: Bank Only */}
                    {activeTab === 'bank_only' && filterItems(result.bank_only, 'bank_only').map((item, idx) => (
                        <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: '0.5rem', padding: '0.6rem 1rem', background: '#f7f7f9', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', alignItems: 'center' }}>
                            {/* Left Sage part is empty */}
                            <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontStyle: 'italic', textAlign: 'center', padding: '0.2rem' }}>
                                (Écriture absente de Sage - À comptabiliser)
                            </div>
                            {/* Middle connector */}
                            <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>➔</div>
                            {/* Right: Bank */}
                            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem', color: 'var(--text-primary)' }}>
                                <div style={{ color: 'var(--text-secondary)' }}>{formatDate(item.date_operation)}</div>
                                <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={item.libelle}>{item.libelle}</div>
                                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-muted)' }}>{item.reference || '-'}</div>
                                <div style={{ textAlign: 'right' }}>{item.debit > 0 ? formatAmount(item.debit) : '-'}</div>
                                <div style={{ textAlign: 'right' }}>{item.credit > 0 ? formatAmount(item.credit) : '-'}</div>
                            </div>
                        </div>
                    ))}

                    {/* TAB: Sage Only */}
                    {activeTab === 'sage_only' && filterItems(result.sage_only, 'sage_only').map((item, idx) => (
                        <div key={idx} style={{ display: 'grid', gridTemplateColumns: '1fr 40px 1fr', gap: '0.5rem', padding: '0.6rem 1rem', background: '#fdfcf9', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', alignItems: 'center' }}>
                            {/* Left: Sage */}
                            <div style={{ display: 'grid', gridTemplateColumns: '80px 1fr 100px 90px 90px', gap: '0.5rem', color: 'var(--text-primary)' }}>
                                <div style={{ color: 'var(--text-secondary)' }}>{formatDate(item.date_ecriture)}</div>
                                <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={item.libelle_ecriture}>{item.libelle_ecriture}</div>
                                <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: 'var(--text-muted)' }}>{item.reference_piece || '-'}</div>
                                <div style={{ textAlign: 'right' }}>{item.debit > 0 ? formatAmount(item.debit) : '-'}</div>
                                <div style={{ textAlign: 'right' }}>{item.credit > 0 ? formatAmount(item.credit) : '-'}</div>
                            </div>
                            {/* Middle connector */}
                            <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>⬅</div>
                            {/* Right Bank part is empty */}
                            <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', fontStyle: 'italic', textAlign: 'center', padding: '0.2rem' }}>
                                (Opération en circulation - Non débitée)
                            </div>
                        </div>
                    ))}

                    {/* Empty state within active tab */}
                    {((activeTab === 'reconciled' && filterItems(result.reconciled, 'reconciled').length === 0) ||
                      (activeTab === 'discrepancies' && filterItems(result.discrepancies, 'discrepancies').length === 0) ||
                      (activeTab === 'bank_only' && filterItems(result.bank_only, 'bank_only').length === 0) ||
                      (activeTab === 'sage_only' && filterItems(result.sage_only, 'sage_only').length === 0)) && (
                        <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', background: 'var(--bg-card)', border: '1px dashed var(--border-light)', borderRadius: 'var(--radius-md)' }}>
                            Aucune ligne ne correspond à vos critères de recherche.
                        </div>
                    )}

                </div>
            </div>
            
        </div>
    );

    return (
        <div className="olea-card fade-in">
            {loading && ReactDOM.createPortal(
                <div className="sage-close-overlay" role="status" aria-live="polite" aria-label="Rapprochement en cours">
                    <div className="sage-close-overlay-card">
                        <div className="sage-close-spinner" />
                        <h4>Rapprochement en cours...</h4>
                        <p>Vérification de la concordance et calcul des taux de confiance.</p>
                    </div>
                </div>,
                document.body
            )}
            {pdfPreview.open && ReactDOM.createPortal(
                <div className="reco-pdf-modal" role="dialog" aria-modal="true" aria-labelledby="reco-pdf-title">
                    <div className="reco-pdf-dialog">
                        <div className="reco-pdf-header">
                            <div>
                                <span className="reco-opening-eyebrow">Aperçu avant export</span>
                                <h3 id="reco-pdf-title">Rapport de rapprochement bancaire</h3>
                            </div>
                            <button type="button" className="reco-modal-close" onClick={closePdfPreview} aria-label="Fermer la prévisualisation"><FiX /></button>
                        </div>
                        <div className="reco-pdf-preview">
                            <iframe src={pdfPreview.url} title="Prévisualisation du rapport PDF" />
                        </div>
                        <div className="reco-pdf-footer">
                            <button type="button" className="btn btn-secondary" onClick={closePdfPreview}>Annuler</button>
                            <button type="button" className="btn btn-primary" onClick={downloadPreviewedPdf}><FiDownload aria-hidden="true" /> Télécharger le PDF</button>
                        </div>
                    </div>
                </div>,
                document.body
            )}
            
            <div className="card-header">
                <h2 className="card-title">
                    Rapprochement Bancaire
                </h2>
            </div>

            <nav className="reco-workspace-tabs" aria-label="Vues du rapprochement bancaire">
                <button
                    type="button"
                    className={workspaceView === 'new' ? 'active' : ''}
                    onClick={() => {
                        handleReset();
                        setWorkspaceView('new');
                    }}
                >
                    Nouveau rapprochement
                </button>
                <button type="button" className={workspaceView === 'history' ? 'active' : ''} onClick={() => setWorkspaceView('history')}>Historique</button>
            </nav>

            <div style={{ padding: '1.5rem' }}>
                {success && (
                    <div className="alert alert-success slide-down" style={{ marginBottom: '1.5rem' }}>{success}</div>
                )}
                {error && (
                    <div className="alert alert-danger slide-down" style={{ marginBottom: '1.5rem' }}>{error}</div>
                )}

                {workspaceView === 'history' && renderHistory()}
                {workspaceView === 'new' && step === 1 && renderStep1()}
                {workspaceView === 'new' && step === 2 && renderStep2()}
            </div>
        </div>
    );
}

export default RapprochementBancaire;
