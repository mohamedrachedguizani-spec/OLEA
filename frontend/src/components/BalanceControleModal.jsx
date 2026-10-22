import React, { useEffect } from 'react';
import ReactDOM from 'react-dom';
import BalanceControle from './BalanceControle';

const BalanceControleModal = ({ controle, tiers = 'clients', onClose }) => {
  useEffect(() => {
    if (!controle) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [controle, onClose]);

  if (!controle) return null;

  return ReactDOM.createPortal(
    <div className="ba-control-modal-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="ba-control-modal" role="dialog" aria-modal="true" aria-labelledby="ba-control-modal-title">
        <header className="ba-control-modal-header">
          <div className={`ba-control-modal-icon ${controle.statut === 'OK' ? 'ok' : 'ko'}`} aria-hidden="true">
            {controle.statut === 'OK' ? '✓' : '!'}
          </div>
          <div className="ba-control-modal-heading">
            <span>Génération terminée</span>
            <h2 id="ba-control-modal-title">Contrôle d’extraction</h2>
            <p>Vérifiez la correspondance entre les écritures extraites et les totaux du PDF Sage.</p>
          </div>
          <button type="button" className="ba-control-modal-close" onClick={onClose} aria-label="Fermer le contrôle">×</button>
        </header>
        <div className="ba-control-modal-body">
          <BalanceControle controle={controle} tiers={tiers} initialOpen />
        </div>
        <footer className="ba-control-modal-footer">
          <button type="button" className="ba-control-modal-primary" onClick={onClose}>Voir la balance générée</button>
        </footer>
      </section>
    </div>,
    document.body,
  );
};

export default BalanceControleModal;
