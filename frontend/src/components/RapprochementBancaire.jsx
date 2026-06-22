// src/components/RapprochementBancaire.jsx
import React, { useState, useRef, useEffect } from 'react';
import ApiService from '../services/api';
import './sage-bfc/SageBfcParser.css';

function KpiCard({ icon, label, color, value, unit, sub }) {
    return (
        <div className={`gd-kpi gd-kpi-${color}`}>
            <div className="gd-kpi-top">
                <span className="gd-kpi-icon">{icon}</span>
                <span className="gd-kpi-label">{label}</span>
            </div>
            <div className="gd-kpi-mid">
                <span className="gd-kpi-value">{value}</span>
                {unit && <span className="gd-kpi-unit">{unit}</span>}
            </div>
            {sub && (
                <div className="gd-kpi-bot">
                    <span className="gd-kpi-sub">{sub}</span>
                </div>
            )}
        </div>
    );
}

function RapprochementBancaire() {
    const [step, setStep] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');
    
    // Files
    const [sageFile, setSageFile] = useState(null);
    const [bankFile, setBankFile] = useState(null);

    // Drag active states
    const [dragActiveSage, setDragActiveSage] = useState(false);
    const [dragActiveBank, setDragActiveBank] = useState(false);

    const sageInputRef = useRef(null);
    const bankInputRef = useRef(null);

    // Reconciliation results
    const [result, setResult] = useState(null);
    const [activeTab, setActiveTab] = useState('reconciled'); // 'reconciled' | 'discrepancies' | 'bank_only' | 'sage_only'
    const [filterQuery, setFilterQuery] = useState('');

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

        const formData = new FormData();
        formData.append('sage_file', sageFile);
        formData.append('bank_file', bankFile);
        formData.append('date_tolerance_days', 3);
        formData.append('match_on_label', 'false');
        formData.append('match_on_date', 'false');

        setLoading(true);
        try {
            const data = await ApiService.compareReconciliation(formData);
            setResult(data);
            setSuccess('Rapprochement effectué avec succès.');
            setStep(2);
        } catch (err) {
            setError(err.message || 'Une erreur est survenue lors du rapprochement.');
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setSageFile(null);
        setBankFile(null);
        setResult(null);
        setError('');
        setSuccess('');
        setFilterQuery('');
        if (sageInputRef.current) sageInputRef.current.value = '';
        if (bankInputRef.current) bankInputRef.current.value = '';
        setStep(1);
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
                <button type="submit" className="btn btn-primary" style={{ padding: '0.75rem 2.5rem', fontSize: '1rem' }} disabled={loading}>
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

    const renderStep2 = () => (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            
            {/* KPI CARDS */}
            <div className="gd-kpi-row">
                <KpiCard icon="" label="Total Relevé Banque" color="neutral" value={result.stats.total_bank_movements} unit="mvmts" />
                <KpiCard icon="" label="Total Écritures Sage" color="neutral" value={result.stats.total_sage_movements} unit="lignes" />
                <KpiCard icon="" label="Rapprochées Auto" color="success" value={result.stats.auto_reconciled_count} />
                <KpiCard icon="" label="Écarts de Montant" color="danger" value={result.stats.discrepancies_count} />
                <KpiCard icon="" label="Montant des Écarts" color="primary" value={formatAmount(result.stats.total_discrepancy_amount)} unit="DT" />
                <KpiCard icon="" label="Taux d'Automatisation" color="purple" value={`${result.stats.automation_rate}%`} />
            </div>

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
            
            {/* Step 2 Back Actions */}
            <div className="form-actions" style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'flex-start' }}>
                <button className="btn btn-secondary" onClick={handleReset}>
                    Retour à l’import
                </button>
            </div>
        </div>
    );

    return (
        <div className="olea-card fade-in">
            {loading && (
                <div className="sage-close-overlay" role="status" aria-live="polite" aria-label="Rapprochement en cours">
                    <div className="sage-close-overlay-card">
                        <div className="sage-close-spinner" />
                        <h4>Rapprochement en cours...</h4>
                        <p>Vérification de la concordance et calcul des taux de confiance.</p>
                    </div>
                </div>
            )}
            
            <div className="card-header">
                <h2 className="card-title">
                    <span className="icon">⚖️</span>
                    Rapprochement Bancaire
                </h2>
            </div>

            <div style={{ padding: '1.5rem' }}>
                {success && (
                    <div className="alert alert-success slide-down" style={{ marginBottom: '1.5rem' }}>{success}</div>
                )}
                {error && (
                    <div className="alert alert-danger slide-down" style={{ marginBottom: '1.5rem' }}>{error}</div>
                )}

                {step === 1 && renderStep1()}
                {step === 2 && renderStep2()}
            </div>
        </div>
    );
}

export default RapprochementBancaire;
