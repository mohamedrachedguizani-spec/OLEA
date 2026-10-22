import React, { useEffect, useMemo, useState } from 'react';
import ReactDOM from 'react-dom';

const fmt = (value) => value === null || value === undefined
  ? '—'
  : new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(Number(value) || 0);

const ExtractionControlModal = ({ controls, title = 'Contrôle d’extraction', onClose }) => {
  const normalized = useMemo(() => (Array.isArray(controls) ? controls : controls ? [controls] : []), [controls]);
  const [openDetails, setOpenDetails] = useState({});
  const hasWarning = normalized.some((control) => control.statut !== 'OK');

  useEffect(() => {
    if (!normalized.length) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event) => event.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [normalized.length, onClose]);

  if (!normalized.length) return null;

  return ReactDOM.createPortal(
    <div className="ba-extraction-modal-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="ba-extraction-modal" role="dialog" aria-modal="true" aria-labelledby="ba-extraction-title">
        <header className="ba-extraction-modal-header">
          <div className={`ba-extraction-modal-icon ${hasWarning ? 'warning' : 'ok'}`} aria-hidden="true">{hasWarning ? '!' : '✓'}</div>
          <div className="ba-extraction-modal-heading">
            <span>Analyse terminée</span>
            <h2 id="ba-extraction-title">{title}</h2>
            <p>Vérifiez les données extraites avant de poursuivre.</p>
          </div>
          <button type="button" className="ba-extraction-modal-close" onClick={onClose} aria-label="Fermer">×</button>
        </header>
        <div className="ba-extraction-modal-body">
          {normalized.map((control, index) => {
            const detailOpen = Boolean(openDetails[index]);
            const status = control.statut || 'OK';
            return (
              <article className={`ba-extraction-control ${status.toLowerCase()}`} key={`${control.fichier || 'fichier'}-${index}`}>
                <div className="ba-extraction-control-header">
                  <div>
                    <span className="ba-extraction-control-label">{control.libelle || control.type || `Fichier ${index + 1}`}</span>
                    <strong>{control.fichier || 'Fichier importé'}</strong>
                    <small>{control.format_detecte || 'Format non précisé'} · {control.lignes_extraites ?? 0} ligne(s) extraite(s)</small>
                  </div>
                  <span className="ba-extraction-status">{status === 'OK' ? 'Conforme' : status === 'WARNING' ? 'À vérifier' : 'Erreur'}</span>
                </div>
                <div className="ba-extraction-metrics">
                  <div><span>Lignes source</span><strong>{control.lignes_source ?? 0}</strong></div>
                  <div><span>Lignes ignorées</span><strong>{control.lignes_ignorees ?? 0}</strong></div>
                  <div><span>Total débit</span><strong>{fmt(control.total_debit)}</strong></div>
                  <div><span>Total crédit</span><strong>{fmt(control.total_credit)}</strong></div>
                  <div><span>Écart</span><strong>{fmt(control.ecart)}</strong></div>
                </div>
                {(control.messages?.length || control.details?.length) > 0 && (
                  <>
                    <button type="button" className="ba-extraction-details-toggle" onClick={() => setOpenDetails((previous) => ({ ...previous, [index]: !detailOpen }))}>
                      {detailOpen ? 'Masquer les détails' : 'Afficher les détails'}
                    </button>
                    {detailOpen && <div className="ba-extraction-details">
                      {control.messages?.map((message, messageIndex) => <p key={messageIndex}>{message}</p>)}
                      {control.details?.map((detail, detailIndex) => <pre key={detailIndex}>{JSON.stringify(detail, null, 2)}</pre>)}
                    </div>}
                  </>
                )}
              </article>
            );
          })}
        </div>
        <footer className="ba-extraction-modal-footer">
          <button type="button" className="ba-extraction-modal-primary" onClick={onClose}>Poursuivre</button>
        </footer>
      </section>
    </div>,
    document.body,
  );
};

export default ExtractionControlModal;
