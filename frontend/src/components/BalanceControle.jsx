// src/components/BalanceControle.jsx
// Rapport de contrôle d'extraction : rapproche les écritures lues du PDF des totaux imprimés par Sage.
import React, { useState } from 'react';

const fmt = (n) => new Intl.NumberFormat('fr-TN', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(n || 0);

const BalanceControle = ({ controle, tiers = 'clients' }) => {
  const [open, setOpen] = useState(false);
  const [seulementEcarts, setSeulementEcarts] = useState(false);
  if (!controle) return null;

  const ok = controle.statut === 'OK';
  const nbAnomalies = (controle.nb_ecarts || 0) + (controle.non_reconnus?.length || 0) + (controle.nb_ignorees || 0);
  const lignes = (controle.detail || []).filter((d) => !seulementEcarts || !d.ok);

  return (
    <div className={`ba-ctrl ${ok ? 'ok' : 'ko'}`}>
      <button type="button" className="ba-ctrl-head" onClick={() => setOpen(!open)}>
        <span className="ba-ctrl-icon">{ok ? '✓' : '!'}</span>
        <span className="ba-ctrl-title">
          {ok ? "Contrôle d'extraction : conforme au PDF" : `Contrôle d'extraction : ${nbAnomalies} anomalie(s) à vérifier`}
          <small>
            {controle.nb_tiers_pdf} {tiers} dans le PDF · {controle.nb_lignes} écritures extraites · {controle.nb_affiches} affichés
            {controle.exclus?.length > 0 && ` · ${controle.exclus.length} sans solde`}
          </small>
        </span>
        <span className="ba-ctrl-toggle">{open ? '▲' : '▼ Détails'}</span>
      </button>

      {open && (
        <div className="ba-ctrl-body">
          {controle.totaux_pdf && (
            <div className="ba-ctrl-totaux">
              {['debit', 'credit', 'solde'].map((k) => (
                <div key={k}>
                  <span>{k === 'debit' ? 'Débit' : k === 'credit' ? 'Crédit' : 'Solde'}</span>
                  <strong>{fmt(controle.totaux_lus[k])}</strong>
                  <small>PDF : {fmt(controle.totaux_pdf[k])} {Math.abs(controle.totaux_lus[k] - controle.totaux_pdf[k]) < 0.5 ? '✓' : '✗'}</small>
                </div>
              ))}
            </div>
          )}

          {controle.ecarts?.length > 0 && (
            <section>
              <h4>Écarts avec les totaux du PDF ({controle.nb_ecarts})</h4>
              <ul>{controle.ecarts.map((e, i) => (
                <li key={i}><b>{e.code}</b> {e.nom} {e.compte && `(${e.compte})`} — {e.champ}{e.date ? ` le ${e.date}` : ''} : lu {fmt(e.calcule)} ≠ PDF {fmt(e.pdf)} (écart {fmt(e.ecart)})</li>
              ))}</ul>
            </section>
          )}
          {controle.non_reconnus?.length > 0 && (
            <section>
              <h4>Tiers imprimés dans le PDF mais non reconnus ({controle.non_reconnus.length})</h4>
              <ul>{controle.non_reconnus.map((n, i) => (
                <li key={i}><b>{n.code}</b> ({n.compte}) — débit {fmt(n.debit)} · crédit {fmt(n.credit)}</li>
              ))}</ul>
            </section>
          )}
          {controle.ignorees?.length > 0 && (
            <section>
              <h4>Lignes ignorées ({controle.nb_ignorees})</h4>
              <ul>{controle.ignorees.map((l, i) => (<li key={i}><b>{l.code}</b> [{l.raison}] <code>{l.ligne}</code></li>))}</ul>
            </section>
          )}

          {controle.exclus?.length > 0 && (
            <section>
              <h4>Extraits mais non affichés dans la balance ({controle.exclus.length})</h4>
              <p className="ba-ctrl-note">Ces {tiers} figurent bien dans le PDF et ont été lus ; ils n'ont aucun solde à analyser.</p>
              <div className="ba-ctrl-scroll short">
                <table className="ba-table">
                  <thead><tr><th>Code</th><th>Nom</th><th>Solde</th><th>Motif</th></tr></thead>
                  <tbody>{controle.exclus.map((e) => (
                    <tr key={e.code}><td>{e.code}</td><td>{e.nom}</td><td>{fmt(e.solde)}</td><td>{e.raison}</td></tr>
                  ))}</tbody>
                </table>
              </div>
            </section>
          )}

          <section>
            <h4>
              Rapprochement par {tiers === 'clients' ? 'client' : 'fournisseur'}
              <label className="ba-ctrl-filter">
                <input type="checkbox" checked={seulementEcarts} onChange={(e) => setSeulementEcarts(e.target.checked)} /> Écarts seulement
              </label>
            </h4>
            <div className="ba-ctrl-scroll">
              <table className="ba-table">
                <thead><tr><th>Tiers</th><th>Cpt</th><th>Écritures</th><th>Débit lu</th><th>Crédit lu</th><th>Solde lu</th><th>Solde PDF</th><th /></tr></thead>
                <tbody>{lignes.map((d, i) => (
                  <tr key={`${d.code}-${d.compte}-${i}`}>
                    <td><div className="ba-name">{d.nom}</div><div className="ba-code">{d.code}</div></td>
                    <td>{d.compte}</td><td>{d.nb_lignes}</td>
                    <td>{fmt(d.debit)}</td><td>{fmt(d.credit)}</td><td>{fmt(d.solde)}</td><td>{d.pdf_solde == null ? '—' : fmt(d.pdf_solde)}</td>
                    <td className={d.ok ? 'ba-ctrl-yes' : 'ba-ctrl-no'}>{d.ok ? '✓' : '✗'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </div>
  );
};

export default BalanceControle;
