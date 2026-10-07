import React, { useState, useMemo, useEffect } from 'react';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import BalanceUpload, { BalanceHeader } from './BalanceUpload';
import BalanceControle from './BalanceControle';
import BalanceActions from './BalanceActions';
import BalanceHistorique from './BalanceHistorique'; // Ajustez le chemin
import './BalanceAgee.css';

const BUCKETS = [
  { key: 'non_echu', field: 'non_echu',  label: 'Non échu', c: 'var(--b0)' },
  { key: '1-30',     field: 'echu_30',   label: '1-30 j',   c: 'var(--b1)' },
  { key: '31-60',    field: 'echu_60',   label: '31-60 j',  c: 'var(--b2)' },
  { key: '61-90',    field: 'echu_90',   label: '61-90 j',  c: 'var(--b3)' },
  { key: '+90',      field: 'echu_plus', label: '+90 j',    c: 'var(--b4)' },
];
const ECHUS = BUCKETS.slice(1);

const fmt = (n) => new Intl.NumberFormat('fr-TN', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(n || 0);
const cell = (n) => (n > 0.0005 ? fmt(n) : <span className="nil">–</span>);
// Montant d'un client dans une tranche : créance échue (débiteur) ou avance par ancienneté (créditeur)
const val = (c, b) => (c.total_solde < 0 ? (c.avance_buckets?.[b.key] || 0) : (c[b.field] || 0));
const num = (c, key) => { const b = BUCKETS.find((x) => x.field === key); return b ? val(c, b) : c[key]; };
const echuOf = (c) => ECHUS.reduce((s, b) => s + (c[b.field] || 0), 0);

const BalanceAgee = () => {
  const { has } = useAuth();
  const canGenerate = has('balance_agee.generate');   // importer un PDF Sage et générer la balance
  const canRead = has('balance_agee.read');           // consulter les balances déjà générées
  const [nbBalances, setNbBalances] = useState(null);
  const [file, setFile] = useState(null);
  const [dateReference, setDateReference] = useState(''); // vide = fin de période du PDF
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [vue, setVue] = useState('debiteurs');
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(null);
  const [showWarn, setShowWarn] = useState(false);
  const [sort, setSort] = useState({ key: 'total_solde', dir: -1 });
  const [step, setStep] = useState(canGenerate ? 'upload' : 'list'); // upload | list | detail (consultation seule : on arrive sur la liste)

  const refreshCount = () => {
    if (!canRead) return;
    ApiService.getBalanceAgeeHistorique('clients', 1, 0).then((r) => setNbBalances(r.total)).catch(() => {});
  };
  useEffect(() => { refreshCount(); }, []);

  // Ouvre une balance enregistrée (depuis l'historique) : même écran d'analyse que juste après la génération
  const openRapport = async (id) => {
    const res = await ApiService.getBalanceAgeeRapport('clients', id);
    setData(res); setOpen(null); setSearch(''); setVue('debiteurs'); setShowWarn(false);
    setStep('detail');
  };

  const submit = async (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (!file) return setError('Veuillez sélectionner un fichier PDF.');
    setLoading(true); setError(''); setData(null); setOpen(null);
    try {
      setData(await ApiService.parseBalanceAgee(file, dateReference || null));
      setStep('detail');   // la balance vient d'être enregistrée : on affiche son analyse
      refreshCount();
    } catch (err) {
      setError(err.message || 'Erreur lors du traitement.');
    } finally {
      setLoading(false);
    }
  };

  const clients = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    const rows = data.clients.filter((c) =>
      (vue === 'tous' || (vue === 'debiteurs' ? c.total_solde > 0 : c.total_solde < 0)) &&
      (!q || c.nom.toLowerCase().includes(q) || c.code.toLowerCase().includes(q)));
    return rows.sort((a, b) => {
      const x = num(a, sort.key), y = num(b, sort.key);
      return (typeof x === 'string' ? x.localeCompare(y) : x - y) * sort.dir;
    });
  }, [data, vue, search, sort]);

  const isCred = vue === 'crediteurs';
  const topRisques = useMemo(() => (data
    ? (isCred
        ? data.clients.filter((c) => c.total_solde < 0).map((c) => ({ c, v: -c.total_solde }))
        : data.clients.filter((c) => c.total_solde > 0).map((c) => ({ c, v: echuOf(c) })))
        .filter((r) => r.v > 0).sort((a, b) => b.v - a.v).slice(0, 5)
    : []), [data, isCred]);

  const totals = useMemo(() => {
    const t = { total_solde: 0 };
    BUCKETS.forEach((b) => { t[b.field] = 0; });
    clients.forEach((c) => { t.total_solde += c.total_solde; BUCKETS.forEach((b) => { t[b.field] += val(c, b); }); });
    return t;
  }, [clients]);

  const creances = data?.total_debiteur || 0;
  const agData = isCred ? data?.totaux_avances : data?.totaux_buckets;
  const agTotal = isCred ? -(data?.total_crediteur || 0) : creances;
  const totalEchu = data ? ECHUS.reduce((s, b) => s + (data.totaux_buckets?.[b.key] || 0), 0) : 0;
  const pct = (v) => (agTotal > 0 ? ((v / agTotal) * 100).toFixed(0) : 0);
  const kpiPct = (v) => (creances > 0 ? ((v / creances) * 100).toFixed(0) : 0);

  const toggleSort = (key) => setSort((s) => (s.key === key ? { key, dir: -s.dir } : { key, dir: key === 'nom' ? 1 : -1 }));
  const arrow = (key) => (sort.key === key ? (sort.dir > 0 ? ' ▲' : ' ▼') : '');

  const exportCsv = () => {
    const head = ['Code', 'Client', 'Solde', ...BUCKETS.map((b) => b.label)];
    const rows = clients.map((c) => [c.code, c.nom, c.total_solde, ...BUCKETS.map((b) => val(c, b))]);
    const csv = [head, ...rows].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(';')).join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' }));
    a.download = `balance_agee_${data.date_reference}.csv`;
    a.click();
  };

  const focusClient = (c) => { setVue(c.total_solde < 0 ? 'crediteurs' : 'debiteurs'); setSearch(''); setOpen(c.code); };

  return (
    <div className="sage-bfc-container ba">
      <BalanceHeader variant="clients" step={step} setStep={setStep} count={nbBalances} canList={canRead} hasData={Boolean(data)} />

      {step === 'upload' && (
        <BalanceUpload
          variant="clients"
          file={file} setFile={setFile}
          dateReference={dateReference} setDateReference={setDateReference}
          loading={loading} error={error} setError={setError} onSubmit={submit}
          onShowHistory={canRead ? () => setStep('list') : undefined}
          canGenerate={canGenerate}
        />
      )}

      {step === 'list' && canRead && (
        <BalanceHistorique kind="clients" onOpen={openRapport} onTotal={setNbBalances}
          onImport={canGenerate ? () => setStep('upload') : undefined} />
      )}

      {step === 'detail' && data && (
        <>
          <BalanceActions kind="clients" data={data} fichier={data.fichier || (file ? file.name : null)} onBack={canRead ? () => setStep('list') : undefined} />
          <BalanceControle controle={data.controle} tiers="clients" />

          {data.avertissements?.length > 0 && (
            <div className="ba-warn">
              <button type="button" onClick={() => setShowWarn(!showWarn)}>
                <span>⚠ {data.avertissements.length} point(s) d'attention</span><span>{showWarn ? '▲' : '▼'}</span>
              </button>
              {showWarn && <ul>{data.avertissements.map((a, i) => <li key={i}>{a}</li>)}</ul>}
            </div>
          )}

          {/* ── 2. Synthèse ── */}
          <div className="ba-kpis">
            <div className="ba-kpi" style={{ '--k': 'var(--primary-500)' }}>
              <div className="ba-kpi-label">Créances clients</div>
              <div className="ba-kpi-value">{fmt(creances)}</div>
              <div className="ba-kpi-sub">Au {new Date(data.date_reference).toLocaleDateString('fr-FR')} · {data.clients.filter((c) => c.total_solde > 0).length} débiteurs</div>
            </div>
            <div className="ba-kpi" style={{ '--k': 'var(--b4)' }}>
              <div className="ba-kpi-label">Dont échu</div>
              <div className="ba-kpi-value">{fmt(totalEchu)}</div>
              <div className="ba-kpi-sub">{kpiPct(totalEchu)} % des créances</div>
            </div>
            <div className="ba-kpi" style={{ '--k': 'var(--adv)' }}>
              <div className="ba-kpi-label">Avances / avoirs</div>
              <div className="ba-kpi-value">{fmt(data.total_crediteur)}</div>
              <div className="ba-kpi-sub">{data.clients.filter((c) => c.total_solde < 0).length} clients créditeurs</div>
            </div>
            <div className="ba-kpi" style={{ '--k': 'var(--olea-anthracite)' }}>
              <div className="ba-kpi-label">Solde net Sage</div>
              <div className="ba-kpi-value">{fmt(data.total_general)}</div>
              <div className="ba-kpi-sub">{data.nb_clients} clients non soldés</div>
            </div>
          </div>

          {/* ── 3. Ancienneté + top risques ── */}
          <div className="ba-grid">
            <div className="ba-card">
              <h2 className="ba-card-title">{isCred ? 'Ancienneté des avances / avoirs' : 'Ancienneté des créances'} <small>{fmt(agTotal)} TND{isCred ? ' · depuis l\'encaissement' : ''}</small></h2>
              {agTotal > 0 ? (
                <>
                  <div className="ba-bar">
                    {BUCKETS.map((b) => {
                      const v = agData?.[b.key] || 0;
                      return v > 0 ? <div key={b.key} style={{ '--c': b.c, width: `${(v / agTotal) * 100}%` }} title={`${b.label} : ${fmt(v)}`} /> : null;
                    })}
                  </div>
                  <div className="ba-legend">
                    {BUCKETS.map((b) => {
                      const v = agData?.[b.key] || 0;
                      return (
                        <div className="ba-leg" key={b.key}>
                          <span className="ba-dot" style={{ '--c': b.c }} />
                          <div>
                            <div className="ba-leg-l">{b.label}</div>
                            <div className="ba-leg-v">{fmt(v)}</div>
                            <div className="ba-leg-p">{pct(v)} %</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : <p className="ba-empty">{isCred ? 'Aucune avance.' : 'Aucune créance ouverte.'}</p>}
            </div>

            <div className="ba-card">
              <h2 className="ba-card-title">{isCred ? 'Top 5 avances à régulariser' : 'Top 5 impayés échus'}</h2>
              {topRisques.length ? (
                <ul className="ba-top">
                  {topRisques.map(({ c, v }) => (
                    <li key={c.code} onClick={() => focusClient(c)}>
                      <div className="ba-top-row"><span>{c.nom}</span><span>{fmt(v)}</span></div>
                      <div className="ba-top-track"><div style={{ width: `${(v / topRisques[0].v) * 100}%` }} /></div>
                    </li>
                  ))}
                </ul>
              ) : <p className="ba-empty">{isCred ? 'Aucune avance.' : 'Aucun impayé échu.'}</p>}
            </div>
          </div>

          {/* ── 4. Détail par client ── */}
          <div className="ba-card">
            <div className="ba-toolbar">
              <div className="ba-seg">
                {[['debiteurs', 'Débiteurs'], ['crediteurs', 'Créditeurs'], ['tous', 'Tous']].map(([k, l]) => (
                  <button key={k} type="button" className={vue === k ? 'on' : ''} onClick={() => setVue(k)}>{l}</button>
                ))}
              </div>
              <input className="ba-search" placeholder="Rechercher un client ou un code…" value={search} onChange={(e) => setSearch(e.target.value)} />
              <div>
                <span className="ba-count">{clients.length} client(s)</span>
                <button type="button" className="btn btn-secondary btn-sm" onClick={exportCsv}>Exporter CSV</button>
              </div>
            </div>

            <div className="ba-tablewrap">
              <table className="ba-table">
                <thead>
                  <tr>
                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('nom')}>Client{arrow('nom')}</th>
                    <th style={{ cursor: 'pointer' }} onClick={() => toggleSort('total_solde')}>Solde{arrow('total_solde')}</th>
                    {BUCKETS.map((b) => (
                      <th key={b.key} className="th-c" style={{ '--c': b.c, cursor: 'pointer' }} onClick={() => toggleSort(b.field)}>{b.label}{arrow(b.field)}</th>
                    ))}
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {clients.map((c) => (
                    <React.Fragment key={c.code}>
                      <tr className={`ba-row ${open === c.code ? 'open' : ''}`} onClick={() => setOpen(open === c.code ? null : c.code)}>
                        <td><div className="ba-name">{c.nom}</div><div className="ba-code">{c.code}</div></td>
                        <td className={c.total_solde < 0 ? 'ba-neg' : ''}><strong>{fmt(c.total_solde)}</strong></td>
                        {BUCKETS.map((b) => <td key={b.key} className="td-c" style={{ '--c': b.c }}>{cell(val(c, b))}</td>)}
                        <td className="ba-chev">{open === c.code ? '▲' : '▼'}</td>
                      </tr>
                      {open === c.code && (
                        <tr>
                          <td className="ba-detail-cell" colSpan={BUCKETS.length + 3}>
                            <div className="ba-detail">
                              <table className="ba-table">
                                <thead>
                                  <tr>
                                    <th>Date</th><th>Libellé</th><th>Débit</th><th>Crédit</th><th>Solde</th><th>{c.total_solde < 0 ? 'Reste à affecter' : 'Reste dû'}</th><th>{c.total_solde < 0 ? 'Ancienneté' : 'Retard'}</th><th>Tranche</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {c.lignes.map((l, i) => {
                                    const b = BUCKETS.find((x) => x.key === l.bucket);
                                    return (
                                      <tr key={i} className={l.reste_du > 0 ? (l.sens === 'C' ? 'adv' : (l.jours_retard > 0 ? 'late' : '')) : ''}>
                                        <td>{l.date}</td>
                                        <td className="ba-lib" title={l.libelle}>
                                          {l.libelle}{l.libelle.startsWith('Report') && <span className="ba-report">âge estimé</span>}
                                        </td>
                                        <td>{cell(l.debit)}</td>
                                        <td>{cell(l.credit)}</td>
                                        <td>{fmt(l.solde)}</td>
                                        <td><strong>{cell(l.reste_du)}</strong></td>
                                        <td>{l.reste_du > 0 ? (l.sens === 'C' ? `${Math.max(l.jours_retard, 0)} j` : (l.jours_retard > 0 ? `+${l.jours_retard} j` : 'À jour')) : ''}</td>
                                        <td>{b && <span className="ba-tag" style={{ '--c': b.c }}>{b.label}</span>}</td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                  {clients.length === 0 && (
                    <tr><td colSpan={BUCKETS.length + 3} style={{ textAlign: 'center', padding: '2rem' }} className="ba-empty">Aucun client.</td></tr>
                  )}
                </tbody>
                {clients.length > 0 && (
                  <tfoot>
                    <tr>
                      <td>Total ({clients.length})</td>
                      <td>{fmt(totals.total_solde)}</td>
                      {BUCKETS.map((b) => <td key={b.key}>{vue === 'tous' ? '' : fmt(totals[b.field])}</td>)}
                      <td />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default BalanceAgee;
