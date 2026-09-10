import React, { useEffect } from 'react';
import ReactDOM from 'react-dom';

const formatAmount = (value) => new Intl.NumberFormat('fr-FR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
}).format(Number(value || 0));

function SageBfcMappingAlert({ details, onDismiss, onOpenConfiguration }) {
    const accounts = details?.comptes_non_mappes || [];

    useEffect(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';

        const handleKeyDown = (event) => {
            if (event.key === 'Escape') onDismiss();
        };
        document.addEventListener('keydown', handleKeyDown);

        return () => {
            document.body.style.overflow = previousOverflow;
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [onDismiss]);

    return ReactDOM.createPortal(
        <div className="mapping-modal-overlay" role="presentation">
            <section
                className="mapping-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="mapping-modal-title"
                aria-describedby="mapping-modal-description"
            >
                <header className="mapping-modal-header">
                    <div className="mapping-modal-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                            <line x1="12" y1="9" x2="12" y2="13" />
                            <line x1="12" y1="17" x2="12.01" y2="17" />
                        </svg>
                    </div>
                    <div className="mapping-modal-title-group">
                        <span className="mapping-modal-eyebrow">Contrôle de l'import</span>
                        <h3 id="mapping-modal-title">Mappings comptables introuvables</h3>
                        <p id="mapping-modal-description">{details?.message}</p>
                    </div>
                    <button type="button" onClick={onDismiss} className="mapping-modal-close" aria-label="Fermer la fenêtre">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <line x1="18" y1="6" x2="6" y2="18" />
                            <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                    </button>
                </header>

                <div className="mapping-modal-body">
                    <div className="mapping-modal-summary">
                        <div className="mapping-modal-stat">
                            <div className="mapping-modal-stat-icon" aria-hidden="true">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <rect x="3" y="4" width="18" height="16" rx="2" />
                                    <line x1="7" y1="9" x2="17" y2="9" />
                                    <line x1="7" y1="14" x2="12" y2="14" />
                                </svg>
                            </div>
                            <div className="mapping-modal-stat-content">
                                <span className="mapping-modal-stat-label">Comptes concernés</span>
                                <strong>{details?.nombre_comptes ?? accounts.length}</strong>
                                <small>Codes sans correspondance BFC</small>
                            </div>
                        </div>
                        <div className="mapping-modal-stat">
                            <div className="mapping-modal-stat-icon" aria-hidden="true">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <circle cx="12" cy="12" r="9" />
                                    <line x1="8" y1="12" x2="16" y2="12" />
                                    <line x1="12" y1="8" x2="12" y2="16" />
                                </svg>
                            </div>
                            <div className="mapping-modal-stat-content">
                                <span className="mapping-modal-stat-label">Solde cumulé</span>
                                <strong>{formatAmount(details?.solde_total)}</strong>
                                <small>Total des comptes non mappés</small>
                            </div>
                        </div>
                        <div className="mapping-modal-status">
                            <span className="mapping-modal-status-dot" />
                            Import suspendu
                        </div>
                    </div>

                    <div className="mapping-modal-instruction">
                        Complétez les mappings ci-dessous, puis relancez l'import de la balance.
                    </div>

                    <div className="mapping-modal-table-wrapper">
                        <table className="mapping-modal-table">
                            <colgroup>
                                <col className="mapping-col-code" />
                                <col className="mapping-col-label" />
                                <col className="mapping-col-count" />
                                <col className="mapping-col-amount" />
                                <col className="mapping-col-amount" />
                                <col className="mapping-col-balance" />
                            </colgroup>
                            <thead>
                                <tr>
                                    <th>Code comptable</th>
                                    <th>Libellé</th>
                                    <th className="mapping-modal-count">Nb. lignes</th>
                                    <th className="mapping-modal-amount">Débit</th>
                                    <th className="mapping-modal-amount">Crédit</th>
                                    <th className="mapping-modal-amount">Solde</th>
                                </tr>
                            </thead>
                            <tbody>
                                {accounts.map((account) => (
                                    <tr key={account.code_compte}>
                                        <td><span className="mapping-modal-code">{account.code_compte}</span></td>
                                        <td>{account.libelle || '—'}</td>
                                        <td className="mapping-modal-count">{account.nombre_lignes}</td>
                                        <td className="mapping-modal-amount">{formatAmount(account.debit)}</td>
                                        <td className="mapping-modal-amount">{formatAmount(account.credit)}</td>
                                        <td className="mapping-modal-amount mapping-modal-balance">{formatAmount(account.solde)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <footer className="mapping-modal-footer">
                    <button type="button" className="mapping-modal-secondary" onClick={onDismiss}>
                        Fermer
                    </button>
                    {onOpenConfiguration && (
                        <button type="button" className="mapping-modal-primary" onClick={onOpenConfiguration}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <circle cx="12" cy="12" r="3" />
                                <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 .6 1.7 1.7 0 0 0-.4 1.1V21h-4v-.09A1.7 1.7 0 0 0 8.6 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-.6-1 1.7 1.7 0 0 0-1.1-.4H3v-4h.09A1.7 1.7 0 0 0 4.6 8.6a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-.6 1.7 1.7 0 0 0 .4-1.1V3h4v.09A1.7 1.7 0 0 0 15.4 4.6a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.4 9c.14.37.35.7.6 1 .28.3.65.46 1.1.49H21v4h-.09A1.7 1.7 0 0 0 19.4 15z" />
                            </svg>
                            Ouvrir le module de configuration
                        </button>
                    )}
                </footer>
            </section>
        </div>,
        document.body
    );
}

export default SageBfcMappingAlert;
