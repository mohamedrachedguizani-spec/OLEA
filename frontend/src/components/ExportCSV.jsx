// src/components/ExportCSV.jsx
import React, { useState } from 'react';
import ReactDOM from 'react-dom';
import ApiService from '../services/api';

function ExportCSV() {
    // État pour Export Sage
    const [dateDebut, setDateDebut] = useState('');
    const [dateFin, setDateFin] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');
    const [previewData, setPreviewData] = useState(null);
    const [showPreview, setShowPreview] = useState(false);

    // État pour Brouillard de Caisse
    const [brouillardDateDebut, setBrouillardDateDebut] = useState('');
    const [brouillardDateFin, setBrouillardDateFin] = useState('');
    const [brouillardLoading, setBrouillardLoading] = useState(false);
    const [brouillardPreviewData, setBrouillardPreviewData] = useState(null);
    const [showBrouillardPreview, setShowBrouillardPreview] = useState(false);

    // Fonctions pour Export Sage
    const handlePreview = async () => {
        setLoading(true);
        setMessage('');

        try {
            const data = await ApiService.exportCSV(dateDebut || null, dateFin || null);
            setPreviewData(data);
            setShowPreview(true);
        } catch (error) {
            setMessage('Erreur lors de la prévisualisation: ' + error.message);
        } finally {
            setLoading(false);
        }
    };

    const handleConfirmExport = () => {
        if (!previewData) return;

        try {
            const blob = new Blob([previewData.content], { type: 'text/csv;charset=utf-8-bom;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            
            link.setAttribute('href', url);
            link.setAttribute('download', previewData.filename);
            link.style.visibility = 'hidden';
            
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            setMessage('Export Sage réalisé avec succès!');
            setShowPreview(false);
            setPreviewData(null);
        } catch (error) {
            setMessage('Erreur lors de l\'export: ' + error.message);
        }
    };

    const handleCancelPreview = () => {
        setShowPreview(false);
        setPreviewData(null);
    };

    // Fonctions pour Brouillard de Caisse
    const handleBrouillardPreview = async () => {
        setBrouillardLoading(true);
        setMessage('');

        try {
            const data = await ApiService.exportBrouillardCaisse(brouillardDateDebut || null, brouillardDateFin || null);
            setBrouillardPreviewData(data);
            setShowBrouillardPreview(true);
        } catch (error) {
            setMessage('Erreur lors de la prévisualisation: ' + error.message);
        } finally {
            setBrouillardLoading(false);
        }
    };

    const handleConfirmBrouillardExport = () => {
        if (!brouillardPreviewData) return;

        try {
            const blob = new Blob([brouillardPreviewData.content], { type: 'text/csv;charset=utf-8-bom;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            
            link.setAttribute('href', url);
            link.setAttribute('download', brouillardPreviewData.filename);
            link.style.visibility = 'hidden';
            
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            setMessage('Brouillard de caisse exporté avec succès!');
            setShowBrouillardPreview(false);
            setBrouillardPreviewData(null);
        } catch (error) {
            setMessage('Erreur lors de l\'export: ' + error.message);
        }
    };

    const handleCancelBrouillardPreview = () => {
        setShowBrouillardPreview(false);
        setBrouillardPreviewData(null);
    };

    const parseCSVForPreview = (csvContent) => {
        if (!csvContent) return { headers: [], rows: [] };
        
        const lines = csvContent.trim().split('\n');
        if (lines.length === 0) return { headers: [], rows: [] };
        
        const headers = lines[0].split(';');
        const rows = lines.slice(1).map(line => line.split(';'));
        
        return { headers, rows };
    };

    const { headers, rows } = previewData ? parseCSVForPreview(previewData.content) : { headers: [], rows: [] };
    const brouillardParsed = brouillardPreviewData ? parseCSVForPreview(brouillardPreviewData.content) : { headers: [], rows: [] };

    // Composant Modal avec Portal
    const PreviewModal = () => {
        if (!showPreview || !previewData) return null;

        return ReactDOM.createPortal(
            <div className="csv-preview-modal">
                <div className="csv-preview-backdrop" onClick={handleCancelPreview}></div>
                <div className="csv-preview-container">
                    <div className="csv-preview-header">
                        <div className="csv-preview-title">
                            <span>📄</span>
                            <h3>Prévisualisation Export Sage</h3>
                        </div>
                        <div className="csv-preview-meta">
                            <span className="csv-filename">{previewData.filename}</span>
                            <span className="csv-count">{rows.length} lignes</span>
                        </div>
                        <button className="csv-preview-close" onClick={handleCancelPreview}>✕</button>
                    </div>
                    
                    <div className="csv-preview-body">
                        <table className="csv-preview-table">
                            <thead>
                                <tr>
                                    {headers.map((header, index) => (
                                        <th key={index}>{header}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={headers.length} className="csv-preview-empty">
                                            Aucune donnée à exporter pour cette période
                                        </td>
                                    </tr>
                                ) : (
                                    rows.map((row, rowIndex) => (
                                        <tr key={rowIndex}>
                                            {row.map((cell, cellIndex) => (
                                                <td key={cellIndex}>{cell}</td>
                                            ))}
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                    
                    <div className="csv-preview-footer">
                        <button className="btn btn-secondary" onClick={handleCancelPreview}>
                            ✕ Annuler
                        </button>
                        <button 
                            className="btn btn-success btn-lg"
                            onClick={handleConfirmExport}
                            disabled={rows.length === 0}
                        >
                            ⬇️ Confirmer et Télécharger
                        </button>
                    </div>
                </div>
            </div>,
            document.body
        );
    };

    // Modal pour Brouillard de Caisse
    const BrouillardPreviewModal = () => {
        if (!showBrouillardPreview || !brouillardPreviewData) return null;

        return ReactDOM.createPortal(
            <div className="csv-preview-modal">
                <div className="csv-preview-backdrop" onClick={handleCancelBrouillardPreview}></div>
                <div className="csv-preview-container">
                    <div className="csv-preview-header brouillard">
                        <div className="csv-preview-title">
                            <span>📒</span>
                            <h3>Brouillard de Caisse</h3>
                        </div>
                        <div className="csv-preview-meta">
                            <span className="csv-filename">{brouillardPreviewData.filename}</span>
                            <span className="csv-count">{brouillardPreviewData.stats?.nb_ecritures || 0} écritures</span>
                        </div>
                        <button className="csv-preview-close" onClick={handleCancelBrouillardPreview}>✕</button>
                    </div>
                    
                    {/* Stats résumé */}
                    {brouillardPreviewData.stats && (
                        <div className="brouillard-stats">
                            <div className="stat-item">
                                <span className="stat-label">Solde Initial</span>
                                <span className="stat-value">{brouillardPreviewData.stats.solde_initial.toFixed(3)} TND</span>
                            </div>
                            <div className="stat-item debit">
                                <span className="stat-label">Total Débit</span>
                                <span className="stat-value">{brouillardPreviewData.stats.total_debit.toFixed(3)} TND</span>
                            </div>
                            <div className="stat-item credit">
                                <span className="stat-label">Total Crédit</span>
                                <span className="stat-value">{brouillardPreviewData.stats.total_credit.toFixed(3)} TND</span>
                            </div>
                            <div className="stat-item solde">
                                <span className="stat-label">Solde Final</span>
                                <span className="stat-value">{brouillardPreviewData.stats.solde_final.toFixed(3)} TND</span>
                            </div>
                        </div>
                    )}
                    
                    <div className="csv-preview-body">
                        <table className="csv-preview-table">
                            <thead>
                                <tr>
                                    {brouillardParsed.headers.map((header, index) => (
                                        <th key={index}>{header}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {brouillardParsed.rows.length === 0 ? (
                                    <tr>
                                        <td colSpan={brouillardParsed.headers.length} className="csv-preview-empty">
                                            Aucune écriture de caisse pour cette période
                                        </td>
                                    </tr>
                                ) : (
                                    brouillardParsed.rows.map((row, rowIndex) => (
                                        <tr key={rowIndex} className={row[1]?.includes('***') ? 'row-summary' : ''}>
                                            {row.map((cell, cellIndex) => (
                                                <td key={cellIndex}>{cell}</td>
                                            ))}
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                    
                    <div className="csv-preview-footer">
                        <button className="btn btn-secondary" onClick={handleCancelBrouillardPreview}>
                            ✕ Annuler
                        </button>
                        <button 
                            className="btn btn-success btn-lg"
                            onClick={handleConfirmBrouillardExport}
                            disabled={brouillardParsed.rows.length === 0}
                        >
                            ⬇️ Télécharger Brouillard
                        </button>
                    </div>
                </div>
            </div>,
            document.body
        );
    };

    return (
        <div className="export-page">
            {message && (
                <div className={`alert ${message.includes('Erreur') ? 'alert-danger' : 'alert-success'} slide-down`}>
                    {message}
                </div>
            )}

            {/* Section 1: Export Sage */}
            <div className="olea-card fade-in">
                <div className="card-header">
                    <h2 className="card-title">
                        <span className="icon">📊</span>
                        Export CSV pour Sage
                    </h2>
                </div>

            <div className="export-card">
                <div className="form-row">
                    <div className="form-col">
                        <div className="form-group">
                            <label>
                                <span className="icon">📅</span>
                                Date début
                            </label>
                            <input
                                type="date"
                                className="form-control"
                                value={dateDebut}
                                onChange={(e) => setDateDebut(e.target.value)}
                            />
                        </div>
                    </div>
                    
                    <div className="form-col">
                        <div className="form-group">
                            <label>
                                <span className="icon">📅</span>
                                Date fin
                            </label>
                            <input
                                type="date"
                                className="form-control"
                                value={dateFin}
                                onChange={(e) => setDateFin(e.target.value)}
                            />
                        </div>
                    </div>
                    
                    <div className="form-col form-col-btn">
                        <button
                            className="btn btn-primary btn-lg"
                            onClick={handlePreview}
                            disabled={loading}
                        >
                            {loading ? (
                                <>
                                    <span className="spinner"></span>
                                    Chargement...
                                </>
                            ) : (
                                <>
                                    <span className="icon">👁️</span>
                                    Prévisualiser CSV
                                </>
                            )}
                        </button>
                    </div>
                </div>
                
                <div className="info-box">
                    <span className="icon">ℹ️</span>
                    <div>
                        <strong>Format d'export Sage</strong>
                        <p>Exporte les écritures migrées au format compatible Sage avec séparateur point-virgule.</p>
                    </div>
                </div>
            </div>
            </div>

            {/* Section 2: Brouillard de Caisse */}
            <div className="olea-card fade-in" style={{ marginTop: '20px' }}>
                <div className="card-header">
                    <h2 className="card-title">
                        <span className="icon">📒</span>
                        Brouillard de Caisse
                    </h2>
                </div>

                <div className="export-card">
                    <div className="form-row">
                        <div className="form-col">
                            <div className="form-group">
                                <label>
                                    <span className="icon">📅</span>
                                    Date début
                                </label>
                                <input
                                    type="date"
                                    className="form-control"
                                    value={brouillardDateDebut}
                                    onChange={(e) => setBrouillardDateDebut(e.target.value)}
                                />
                            </div>
                        </div>
                        
                        <div className="form-col">
                            <div className="form-group">
                                <label>
                                    <span className="icon">📅</span>
                                    Date fin
                                </label>
                                <input
                                    type="date"
                                    className="form-control"
                                    value={brouillardDateFin}
                                    onChange={(e) => setBrouillardDateFin(e.target.value)}
                                />
                            </div>
                        </div>
                        
                        <div className="form-col form-col-btn">
                            <button
                                className="btn btn-secondary btn-lg"
                                onClick={handleBrouillardPreview}
                                disabled={brouillardLoading}
                            >
                                {brouillardLoading ? (
                                    <>
                                        <span className="spinner"></span>
                                        Chargement...
                                    </>
                                ) : (
                                    <>
                                        <span className="icon">📒</span>
                                        Prévisualiser Brouillard
                                    </>
                                )}
                            </button>
                        </div>
                    </div>
                    
                    <div className="info-box">
                        <span className="icon">ℹ️</span>
                        <div>
                            <strong>Brouillard de Caisse</strong>
                            <p>Exporte toutes les écritures de caisse avec le solde calculé pour la période sélectionnée. Inclut le solde initial et final.</p>
                        </div>
                    </div>
                </div>
            </div>

            <PreviewModal />
            <BrouillardPreviewModal />
        </div>
    );
}

export default ExportCSV;