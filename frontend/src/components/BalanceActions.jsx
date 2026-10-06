// src/components/BalanceActions.jsx
// « Exporter PDF » / « Imprimer » de la balance âgée : le clic ouvre d'abord la prévisualisation du document,
// puis l'action n'est lancée qu'après confirmation (même parcours que le Reporting).
import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom';
import { FiFileText, FiPrinter, FiX } from 'react-icons/fi';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import oleaLogo from '../assets/olea-logo.svg';
import '../styles/Reporting.css';   // classes csv-preview-* / reporting-preview-* partagées avec le Reporting

const BalanceActions = ({ kind = 'clients', data, fichier, onBack }) => {
  const { has } = useAuth();
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewAction, setPreviewAction] = useState(null);     // 'pdf' | 'print'
  const [previewSections, setPreviewSections] = useState(null);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [printLoading, setPrintLoading] = useState(false);
  const [error, setError] = useState('');
  const module = kind === 'fournisseurs' ? 'balance_fournisseur' : 'balance_agee';
  const canPdf = has(`${module}.export_pdf`);
  const canPrint = has(`${module}.print`);
  const busy = previewLoading || pdfLoading || printLoading;

  const handleCancelPreview = () => {
    setShowPreviewModal(false);
    setPreviewSections(null);
    setPreviewAction(null);
  };

  useEffect(() => {
    if (!showPreviewModal) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') handleCancelPreview(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [showPreviewModal]);

  if (!data || (!onBack && !canPdf && !canPrint)) return null;

  const openPreview = async (action) => {
    setPreviewLoading(true);
    setPreviewAction(action);
    setError('');
    try {
      setPreviewSections(await ApiService.getBalanceAgeePreview(kind, data, fichier || null));
      setShowPreviewModal(true);
    } catch (e) {
      setError(e.message || 'Erreur chargement prévisualisation');
    } finally {
      setPreviewLoading(false);
    }
  };

  const handlePdf = async () => {
    setPdfLoading(true);
    setError('');
    try { await ApiService.exportBalanceAgeePdf(kind, data, fichier || null); }
    catch (e) { setError(e.message || 'Erreur export PDF'); }
    finally { setPdfLoading(false); }
  };

  const handlePrint = async () => {
    setPrintLoading(true);
    setError('');
    try { await ApiService.printBalanceAgee(kind, data, fichier || null); }
    catch (e) { setError(e.message || 'Erreur impression'); }
    finally { setPrintLoading(false); }
  };

  const handleConfirmPreview = async () => {
    const action = previewAction;
    handleCancelPreview();
    if (action === 'pdf') await handlePdf();
    else if (action === 'print') await handlePrint();
  };

  const p = previewSections;

  return (
    <>
      <div className="ba-actions">
        {onBack ? (
          <button type="button" className="btn btn-secondary btn-sm" onClick={onBack} disabled={busy}>← Retour à la liste</button>
        ) : <span />}
        <div className="ba-actions-right">
        {canPrint && (
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => openPreview('print')} disabled={busy}>
            {previewLoading && previewAction === 'print' ? 'Chargement...' : printLoading ? 'Impression...' : 'Imprimer'}
          </button>
        )}
        {canPdf && (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => openPreview('pdf')} disabled={busy}>
            {previewLoading && previewAction === 'pdf' ? 'Chargement...' : pdfLoading ? 'Génération...' : 'Exporter PDF'}
          </button>
        )}
        </div>
      </div>
      {error && <div className="dropzone-error" style={{ marginBottom: '1rem' }}><span>{error}</span></div>}

      {showPreviewModal && p && ReactDOM.createPortal(
        <div className="csv-preview-modal reporting-preview-modal">
          <div className="csv-preview-backdrop" onClick={handleCancelPreview}></div>
          <div className="csv-preview-container reporting-preview-container">
            <div className="csv-preview-header">
              <div className="csv-preview-title">
                <span><FiFileText /></span>
                <h3>Prévisualisation {p.titre}</h3>
              </div>
              <div className="csv-preview-meta">
                <span className="csv-filename">Situation au {p.date_reference}</span>
                <span className="csv-count">{p.sections?.length || 0} sections</span>
              </div>
              <button className="csv-preview-close" onClick={handleCancelPreview}><FiX /></button>
            </div>

            <div className="csv-preview-body reporting-preview-body">
              <article className="reporting-preview-document">
                <header className="reporting-document-header">
                  <img src={oleaLogo} alt="OLEA" />
                  <strong>{p.entete}</strong>
                </header>

                <div className="reporting-document-heading">
                  <div>
                    <span>RAPPORT DE PILOTAGE</span>
                    <h2>{p.titre}</h2>
                  </div>
                  <div className="reporting-document-meta">
                    <div><small>SITUATION AU</small><strong>{p.date_reference}</strong></div>
                    <div><small>SOURCE</small><strong>{p.fichier || '—'}</strong></div>
                    <div><small>DATE D'ÉDITION</small><strong>{p.generated_at || '—'}</strong></div>
                    <div><small>{(p.tiers_pl || '').toUpperCase()}</small><strong>{p.nb}</strong></div>
                  </div>
                </div>

                {(p.sections || []).map((section, sIdx) => (
                  <section key={sIdx} className="reporting-preview-section">
                    <h4 className="reporting-preview-section-title">{section.title}</h4>
                    {section.note && <p className="ba-preview-note">{section.note}</p>}
                    {section.headers.length === 0 || section.rows.length === 0 ? (
                      <div className="csv-preview-empty">Aucune donnée</div>
                    ) : (
                      <div className="reporting-preview-table-wrap">
                        <table className="csv-preview-table">
                          <thead>
                            <tr>
                              {section.headers.map((h, hIdx) => (
                                <th key={hIdx} style={section.align?.[hIdx] === 'r' ? { textAlign: 'right' } : undefined}>{h}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {section.rows.map((row, rIdx) => (
                              <tr key={rIdx} className={section.row_classes?.[rIdx] || ''}>
                                {section.spans?.includes(rIdx) ? (
                                  <td colSpan={section.headers.length}><strong>{row[0]}</strong></td>
                                ) : row.map((cell, cIdx) => (
                                  <td key={cIdx}
                                    className={section.cell_classes?.[rIdx]?.[cIdx] || ''}
                                    style={section.align?.[cIdx] === 'r' ? { textAlign: 'right', whiteSpace: 'nowrap' } : undefined}>
                                    {cell}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                ))}

                <footer className="reporting-document-footer">
                  <span>Document généré par OLEA Finance</span>
                  <span>{p.titre} · {p.date_reference}</span>
                </footer>
              </article>
            </div>

            <div className="csv-preview-footer">
              <button className="btn btn-secondary" onClick={handleCancelPreview}>
                <FiX /> Annuler
              </button>
              <button className="btn btn-primary" onClick={handleConfirmPreview} disabled={busy}>
                {previewAction === 'print'
                  ? <><FiPrinter /> Confirmer et Imprimer</>
                  : <><FiFileText /> Confirmer et télécharger le PDF</>}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
};

export default BalanceActions;
