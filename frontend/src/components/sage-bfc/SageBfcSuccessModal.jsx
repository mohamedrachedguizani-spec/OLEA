import React, { useEffect } from 'react';
import ReactDOM from 'react-dom';

const formatPeriod = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value || '—';
    return date.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
};

function SageBfcSuccessModal({ details, onDismiss, onViewResults, onNewUpload }) {
    useEffect(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';

        const handleKeyDown = (event) => {
            if (event.key === 'Escape') onDismiss();
        };
        const timer = window.setTimeout(onDismiss, 12000);
        document.addEventListener('keydown', handleKeyDown);

        return () => {
            window.clearTimeout(timer);
            document.body.style.overflow = previousOverflow;
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [onDismiss]);

    return ReactDOM.createPortal(
        <div className="import-success-overlay" role="presentation">
            <section
                className="import-success-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="import-success-title"
                aria-describedby="import-success-description"
            >
                <header className="import-success-header">
                    <div className="import-success-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                            <circle cx="12" cy="12" r="9" />
                            <polyline points="8 12 11 15 16 9" />
                        </svg>
                    </div>
                    <div className="import-success-title-group">
                        <span>Import terminé</span>
                        <h3 id="import-success-title">Balance importée avec succès</h3>
                        <p id="import-success-description">
                            La balance de <strong>{formatPeriod(details?.periode)}</strong> a été traitée et enregistrée.
                        </p>
                    </div>
                    <button type="button" className="import-success-close" onClick={onDismiss} aria-label="Fermer la fenêtre">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    </button>
                </header>

                <div className="import-success-body">
                    <div className="import-success-file">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                            <polyline points="14 2 14 8 20 8" />
                        </svg>
                        <div>
                            <span>Fichier importé</span>
                            <strong title={details?.fileName}>{details?.fileName || '—'}</strong>
                        </div>
                    </div>

                    <div className="import-success-stats">
                        <div className="import-success-stat">
                            <span>Comptes mappés</span>
                            <strong>{details?.mappedAccounts ?? 0}</strong>
                        </div>
                        <div className="import-success-stat">
                            <span>Lignes importées</span>
                            <strong>{details?.linesCount ?? 0}</strong>
                        </div>
                    </div>

                    <div className="import-success-mapping-check">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M20 6L9 17l-5-5" />
                        </svg>
                        <span>Tous les comptes de classes 6 et 7 sont correctement mappés.</span>
                    </div>
                </div>

                <footer className="import-success-footer">
                    <button type="button" className="import-success-secondary" onClick={onNewUpload}>
                        Importer une autre balance
                    </button>
                    <button type="button" className="import-success-primary" onClick={onViewResults}>
                        Voir l'analyse BFC
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="5" y1="12" x2="19" y2="12" />
                            <polyline points="12 5 19 12 12 19" />
                        </svg>
                    </button>
                </footer>
                <div className="import-success-timer" aria-hidden="true" />
            </section>
        </div>,
        document.body
    );
}

export default SageBfcSuccessModal;
