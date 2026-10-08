// src/components/BalanceHistorique.jsx
// Liste des balances âgées déjà générées (plus récentes d'abord) : un clic ouvre l'analyse complète.
import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom';
import { FiEye, FiTrash2 } from 'react-icons/fi';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';

const PAGE = 20;
const jour = (iso) => (iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('fr-FR') : '—');
const heure = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso.replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' });
};

const LIBELLES = {
  clients: { tiers: 'Clients', vide: 'Aucune balance âgée clients générée pour le moment.' },
  fournisseurs: { tiers: 'Fournisseurs', vide: 'Aucune balance âgée fournisseurs générée pour le moment.' },
};

const BalanceHistorique = ({ kind = 'clients', onOpen, onImport, onTotal }) => {
  const L = LIBELLES[kind];
  const { has } = useAuth();
  const canDelete = has(`${kind === 'fournisseurs' ? 'balance_fournisseur' : 'balance_agee'}.delete`);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [openingId, setOpeningId] = useState(null);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [toDelete, setToDelete] = useState(null);   // balance en attente de confirmation
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let annule = false;
    setLoading(true);
    setError('');
    ApiService.getBalanceAgeeHistorique(kind, PAGE, page * PAGE)
      .then((res) => { if (!annule) { setItems(res.items || []); setTotal(res.total || 0); if (onTotal) onTotal(res.total || 0); } })
      .catch((e) => { if (!annule) setError(e.message || "Erreur lors du chargement de l'historique"); })
      .finally(() => { if (!annule) setLoading(false); });
    return () => { annule = true; };
  }, [kind, page, reloadKey]);

  const ouvrir = async (id) => {
    setOpeningId(id);
    setError('');
    try { await onOpen(id); }
    catch (e) { setError(e.message || 'Erreur lors du chargement de la balance'); setOpeningId(null); }
  };

  const confirmerSuppression = async () => {
    if (!toDelete) return;
    setDeleting(true);
    setError('');
    try {
      await ApiService.deleteBalanceAgeeRapport(kind, toDelete.id);
      const derniereDeLaPage = items.length === 1 && page > 0;
      setToDelete(null);
      if (derniereDeLaPage) setPage(page - 1); else setReloadKey((k) => k + 1);
    } catch (e) {
      setError(e.message || 'Erreur lors de la suppression');
      setToDelete(null);
    } finally {
      setDeleting(false);
    }
  };

  const nbPages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="ba-card ba-hist">
      <div className="ba-toolbar">
        <strong className="ba-hist-title">Balances générées</strong>
        <span className="ba-count">{total} balance(s) · de la plus récente à la plus ancienne</span>
        <span className="ba-spacer" />
        {onImport && <button type="button" className="btn btn-primary btn-sm" onClick={onImport}>Nouvelle balance</button>}
      </div>

      {error && <div className="dropzone-error" style={{ margin: '1rem' }}><span>{error}</span></div>}

      {loading ? (
        <div className="ba-hist-empty"><span className="spinner" /> Chargement de l'historique…</div>
      ) : items.length === 0 ? (
        <div className="ba-hist-empty">
          <p>{L.vide}</p>
          {onImport && <button type="button" className="btn btn-secondary btn-sm" onClick={onImport}>Importer un grand livre</button>}
        </div>
      ) : (
        <div className="ba-tablewrap">
          <table className="ba-table ba-hist-table">
            <thead>
              <tr>
                <th>Situation au</th>
                <th>Fichier</th>
                <th>Généré le</th>
                <th>Par</th>
                <th>{L.tiers}</th>
                <th>Contrôle</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="ba-row" onClick={() => !openingId && ouvrir(r.id)}>
                  <td><strong>{jour(r.date_reference)}</strong></td>
                  <td className="ba-hist-file" title={r.fichier || ''}>{r.fichier || '—'}</td>
                  <td>{heure(r.genere_le)}</td>
                  <td>{r.genere_par || '—'}</td>
                  <td>{r.nb_tiers}</td>
                  <td>
                    <span className={`ba-hist-pill ${r.controle_statut === 'OK' ? 'ok' : r.controle_statut ? 'ko' : ''}`}>
                      {r.controle_statut === 'OK' ? '✓ Conforme' : r.controle_statut ? '! Anomalies' : '—'}
                    </span>
                  </td>
                  <td>
                    <div className="reco-history-actions">
                      <button type="button" className="reco-icon-button" title="Consulter" aria-label="Consulter la balance"
                        disabled={Boolean(openingId)} onClick={(e) => { e.stopPropagation(); ouvrir(r.id); }}>
                        {openingId === r.id ? <span className="spinner" /> : <FiEye />}
                      </button>
                      {canDelete && (
                        <button type="button" className="reco-icon-button reco-icon-button-danger" title="Supprimer" aria-label="Supprimer la balance"
                          disabled={Boolean(openingId)} onClick={(e) => { e.stopPropagation(); setToDelete(r); }}>
                          <FiTrash2 />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE && (
        <div className="ba-hist-pager">
          <button type="button" className="btn btn-secondary btn-sm" disabled={page === 0 || loading} onClick={() => setPage(page - 1)}>Précédent</button>
          <span>Page {page + 1} / {nbPages}</span>
          <button type="button" className="btn btn-secondary btn-sm" disabled={page + 1 >= nbPages || loading} onClick={() => setPage(page + 1)}>Suivant</button>
        </div>
      )}

      {toDelete && ReactDOM.createPortal(
        <div className="sage-close-overlay" role="alertdialog" aria-modal="true" onClick={() => !deleting && setToDelete(null)}>
          <div className="sage-close-overlay-card ba-confirm" onClick={(e) => e.stopPropagation()}>
            <h4>Supprimer cette balance ?</h4>
            <p>
              Balance au <strong>{jour(toDelete.date_reference)}</strong>{toDelete.fichier ? ` · ${toDelete.fichier}` : ''}
              <br />générée le {heure(toDelete.genere_le)}{toDelete.genere_par ? ` par ${toDelete.genere_par}` : ''}.
            </p>
            <p className="ba-confirm-warn">Cette action est définitive.</p>
            <div className="ba-confirm-actions">
              <button type="button" className="btn btn-secondary" onClick={() => setToDelete(null)} disabled={deleting}>Annuler</button>
              <button type="button" className="btn btn-primary" onClick={confirmerSuppression} disabled={deleting}>
                {deleting ? 'Suppression…' : 'Supprimer'}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default BalanceHistorique;
