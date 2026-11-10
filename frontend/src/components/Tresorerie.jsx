// src/components/Tresorerie.jsx
// Module Trésorerie : import des extraits bancaires quotidiens, classement des
// mouvements (exploitation / hors exploitation / commission) et reporting par banque.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactDOM from 'react-dom';
import {
    FiAlertTriangle,
    FiCheck,
    FiCheckCircle,
    FiChevronLeft,
    FiChevronRight,
    FiCreditCard,
    FiDownload,
    FiFile,
    FiFileText,
    FiPercent,
    FiPlay,
    FiTrash2,
    FiUploadCloud,
    FiX,
} from 'react-icons/fi';
import ApiService from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import ExtractionControlModal from './ExtractionControlModal';
import './Tresorerie.css';

const MAX_SIZE = 25 * 1024 * 1024;

const NATURES = {
    exploitation: { label: 'Exploitation', sigle: 'E', tag: 'exp', cls: 'on-exp', aide: 'Recette ou dépense courante de l’entreprise' },
    hors_exploitation: { label: 'Hors exploitation', sigle: 'H', tag: 'hors', cls: 'on-hors', aide: 'Opération financière ou exceptionnelle' },
    commission: { label: 'Commission', sigle: 'C', tag: 'comm', cls: 'on-comm', aide: 'Frais bancaires, comptés dans l’exploitation du reporting' },
};

const fmt = (n) => new Intl.NumberFormat('fr-TN', { minimumFractionDigits: 3, maximumFractionDigits: 3 }).format(Number(n) || 0);
const fmtCourt = (n) => new Intl.NumberFormat('fr-TN', { minimumFractionDigits: 0, maximumFractionDigits: 3 }).format(Number(n) || 0);
const jour = (v) => (v ? new Date(v).toLocaleDateString('fr-FR') : '—');
// Date « AAAA-MM-JJ » d'une valeur renvoyée par l'API (date ou datetime ISO),
// pour comparaison lexicographique avec la valeur d'un <input type="date">.
const longDate = (v) => (v ? String(v).slice(0, 10) : '');
const montant = (n) => (Math.abs(Number(n) || 0) > 0.0005 ? fmt(n) : <span className="tr-nil">–</span>);

const Svg = ({ children }) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">{children}</svg>
);

const IconTresorerie = () => (
    <Svg>
        <rect x="2" y="6" width="20" height="12" rx="2" />
        <circle cx="12" cy="12" r="2.5" />
        <path d="M6 12h.01M18 12h.01" />
    </Svg>
);

const formatTaille = (n) => (n < 1024 * 1024 ? `${Math.round(n / 1024)} Ko` : `${(n / 1024 / 1024).toFixed(2)} Mo`);

/* ───────── En-tête du module ───────── */
const Entete = ({ resume, onglet, setOnglet, peut, nbImports, nbMouvements }) => (
    <>
        <div className="tr-header">
            <span className="tr-header-icon"><IconTresorerie /></span>
            <div className="tr-header-main">
                <h2 className="tr-title">Trésorerie</h2>
                <p className="tr-subtitle">Suivi quotidien des extraits bancaires, classement et ratios d’exploitation</p>
            </div>
            <div className="tr-header-stats">
                <span className="tr-chip">Imports <strong>{resume?.imports_count ?? nbImports ?? 0}</strong></span>
                <span className="tr-chip">Mouvements <strong>{resume?.mouvements_count ?? nbMouvements ?? 0}</strong></span>
                <span className="tr-chip">Banques <strong>{resume?.banques_count ?? 0}</strong></span>
                {Number(resume?.non_classes_count || 0) > 0
                    ? <span className="tr-chip warn">À classer <strong>{resume.non_classes_count}</strong></span>
                    : <span className="tr-chip ok"><FiCheckCircle /> Tout est classé</span>}
            </div>
        </div>

        <nav className="tr-nav" aria-label="Sections de la trésorerie">
            <button type="button" className={`tr-nav-btn ${onglet === 'import' ? 'active' : ''}`} onClick={() => setOnglet('import')}>
                <FiUploadCloud /> Import des extraits
            </button>
            {peut.lire && (
                <button type="button" className={`tr-nav-btn ${onglet === 'mouvements' ? 'active' : ''}`} onClick={() => setOnglet('mouvements')}>
                    <FiCreditCard /> Mouvements
                    {Number(resume?.non_classes_count || 0) > 0 && (
                        <span className="tr-count" title="Mouvements non classés">{resume.non_classes_count}</span>
                    )}
                </button>
            )}
            {peut.rapport && (
                <button type="button" className={`tr-nav-btn ${onglet === 'reporting' ? 'active' : ''}`} onClick={() => setOnglet('reporting')}>
                    <FiPercent /> Reporting
                </button>
            )}
        </nav>
    </>
);

/* Bloc : solde de départ, affiché dans la modale de contrôle d'extraction.
   L'import est déjà enregistré ; ce bloc valide ou corrige l'ancre de la banque. */
const BlocSoldeDepart = ({ lecture, onValider }) => {
    const [solde, setSolde] = useState(
        lecture.solde_ouverture_lu != null ? String(lecture.solde_ouverture_lu) : '',
    );
    const [dateSolde, setDateSolde] = useState(
        longDate(lecture.solde_ouverture_date_lue) || longDate(lecture.periode_debut),
    );
    const [erreur, setErreur] = useState('');
    const [charge, setCharge] = useState(false);
    const [enregistre, setEnregistre] = useState(false);

    const valider = async () => {
        if (solde === '' || !dateSolde) {
            return setErreur('Renseignez le montant et la date du solde de départ.');
        }
        setCharge(true);
        setErreur('');
        try {
            await onValider(lecture.compte_banque, Number(solde), dateSolde);
            setEnregistre(true);
        } catch (err) {
            setErreur(err.message || 'Erreur lors de l’enregistrement du solde.');
        } finally {
            setCharge(false);
        }
    };

    return (
        <article className="ba-extraction-control tr-solde-bloc">
            <div className="ba-extraction-control-header">
                <div>
                    <span className="ba-extraction-control-label">
                        {lecture.deja_fige ? 'Solde figé' : 'Premier import'} · {lecture.compte_banque}
                    </span>
                    <strong>Solde de départ du compte</strong>
                    <small>
                        {lecture.deja_fige
                            ? 'Valeur actuellement figée pour cette banque. Corrigez-la si l’extraction s’est trompée.'
                            : 'Montant imprimé sur le relevé, figé ensuite pour cette banque.'}
                    </small>
                </div>
                <span className={`ba-extraction-status ${enregistre ? '' : 'tr-status-pending'}`}>
                    {enregistre ? 'Enregistré' : lecture.deja_fige ? 'Figé' : 'À valider'}
                </span>
            </div>

            <div className="tr-form" style={{ gridTemplateColumns: '1fr 1fr', marginTop: '.9rem' }}>
                <div className="tr-field">
                    <label htmlFor="tr-solde-montant">Montant</label>
                    <input
                        id="tr-solde-montant" type="number" step="0.001"
                        value={solde}
                        onChange={(e) => { setSolde(e.target.value); setEnregistre(false); }}
                        placeholder="Solde non détecté : saisissez-le"
                        disabled={enregistre}
                    />
                </div>
                <div className="tr-field">
                    <label htmlFor="tr-solde-date">Arrêté au</label>
                    <input
                        id="tr-solde-date" type="date"
                        value={dateSolde}
                        onChange={(e) => { setDateSolde(e.target.value); setEnregistre(false); }}
                        disabled={enregistre}
                    />
                </div>
            </div>

            {lecture.solde_ouverture_lu == null && !enregistre && (
                <div className="tr-alert" style={{ marginTop: '.7rem' }}>
                    <FiAlertTriangle />
                    <span>Aucun solde de départ n’a pu être lu sur ce relevé. Saisissez-le pour que le solde du reporting soit calculable.</span>
                </div>
            )}
            {erreur && <div className="tr-alert" style={{ marginTop: '.7rem' }}><FiAlertTriangle /><span>{erreur}</span></div>}

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '.8rem' }}>
                <button type="button" className="btn btn-primary btn-sm" disabled={charge || enregistre} onClick={valider}>
                    {enregistre ? '✓ Solde validé' : charge ? 'Enregistrement…' : 'Valider le solde'}
                </button>
            </div>
        </article>
    );
};

/* ───────── Onglet Import ───────── */
const OngletImport = ({ banques, peut, onImporte, imports, onOuvrirImport, onSupprimerImport, onSoldeAValider }) => {
    const [form, setForm] = useState({ compte_banque: '', periode_debut: '', periode_fin: '', taux_conversion: '', file: null });
    const [drag, setDrag] = useState(false);
    const [erreur, setErreur] = useState('');
    const [charge, setCharge] = useState(false);
    const inputRef = useRef(null);

    const banque = banques.find((b) => b.code === form.compte_banque);
    const requiertTaux = Boolean(banque?.requiert_taux);

    const choisir = (fichier) => {
        if (!fichier) return;
        const ext = (fichier.name.split('.').pop() || '').toLowerCase();
        if (!['pdf', 'csv', 'txt', 'xlsx', 'xls'].includes(ext)) return setErreur('Formats acceptés : PDF, CSV ou Excel.');
        if (fichier.size > MAX_SIZE) return setErreur('Fichier trop volumineux (max 25 Mo).');
        setErreur('');
        setForm((p) => ({ ...p, file: fichier }));
    };

    const changer = (e) => {
        const { name, value } = e.target;
        setForm((p) => {
            const suivant = { ...p, [name]: value };
            if (name === 'compte_banque' && !banques.find((b) => b.code === value)?.requiert_taux) {
                suivant.taux_conversion = '';
            }
            return suivant;
        });
    };

    const soumettre = async (e) => {
        e.preventDefault();
        setErreur('');
        if (!form.file) return setErreur('Veuillez sélectionner un extrait bancaire.');
        if (!form.compte_banque) return setErreur('Veuillez choisir la banque.');
        if (!form.periode_debut || !form.periode_fin) {
            return setErreur('Les périodes de début et de fin sont obligatoires.');
        }
        if (form.periode_debut > form.periode_fin) {
            return setErreur('La période de début doit précéder la période de fin.');
        }
        if (requiertTaux && (!form.taux_conversion || Number(form.taux_conversion) <= 0)) {
            return setErreur(`Le compte ${form.compte_banque} est en ${banque?.devise}. Saisissez un taux de conversion valide.`);
        }
        // Période déjà utilisée pour cette banque : inutile d'envoyer le fichier,
        // le backend répondrait 409. On prévient tout de suite.
        const chevauche = imports.find((imp) => (
            imp.compte_banque === form.compte_banque
            && imp.periode_debut && imp.periode_fin
            && form.periode_debut <= longDate(imp.periode_fin)
            && longDate(imp.periode_debut) <= form.periode_fin
        ));
        if (chevauche) {
            return setErreur(
                `La période chevauche un import existant pour ${form.compte_banque} : `
                + `${jour(chevauche.periode_debut)} → ${jour(chevauche.periode_fin)} `
                + `(${chevauche.file_name}). Choisissez une autre période ou supprimez cet import.`,
            );
        }
        const payload = new FormData();
        payload.append('file', form.file);
        payload.append('compte_banque', form.compte_banque);
        payload.append('periode_debut', form.periode_debut);
        payload.append('periode_fin', form.periode_fin);
        if (requiertTaux) payload.append('taux_conversion', form.taux_conversion);

        setCharge(true);
        try {
            const resultat = await onImporte(payload);
            setForm({ compte_banque: '', periode_debut: '', periode_fin: '', taux_conversion: '', file: null });
            if (inputRef.current) inputRef.current.value = '';
            // La modale de contrôle propose toujours le solde de départ de la
            // banque : valeur lue sur ce relevé si présente, sinon valeur déjà
            // figée. L'utilisateur valide ou corrige.
            onSoldeAValider({
                compte_banque: resultat.import_batch?.compte_banque,
                periode_debut: resultat.import_batch?.periode_debut,
                solde_ouverture_lu: resultat.solde_ouverture_lu ?? resultat.solde_ouverture_actuel,
                solde_ouverture_date_lue: resultat.solde_ouverture_date_lue ?? resultat.solde_ouverture_date_actuelle,
                deja_fige: Boolean(resultat.a_un_solde),
            });
            return resultat;
        } catch (err) {
            setErreur(err.message || 'Erreur lors de l’import.');
        } finally {
            setCharge(false);
        }
        return null;
    };

    if (!peut.importer) {
        return (
            <div className="tr-card">
                <div className="tr-alert"><FiAlertTriangle /><span>Consultation uniquement : vous n’avez pas l’autorisation d’importer un extrait bancaire.</span></div>
                {peut.supprimer && <p className="tr-hint">Vous pouvez consulter les mouvements et le reporting depuis les onglets correspondants.</p>}
            </div>
        );
    }

    return (
        <>
            <form className="tr-card" onSubmit={soumettre}>
                <h3 className="tr-card-title">
                    Nouvel import d’extrait bancaire
                    <small>Le travail d’extraction est le même que celui de la saisie caisse</small>
                </h3>

                <div className="tr-form">
                    <div className="tr-field">
                        <label htmlFor="tr-banque">Banque</label>
                        <select id="tr-banque" name="compte_banque" value={form.compte_banque} onChange={changer}>
                            <option value="">Sélectionner</option>
                            {banques.map((b) => (
                                <option key={b.code} value={b.code}>{b.code} — {b.libelle}</option>
                            ))}
                        </select>
                        {banque && <div className="tr-hint">Compte comptable : {banque.compte_comptable}</div>}
                    </div>
                    <div className="tr-field">
                        <label htmlFor="tr-debut">Période début *</label>
                        <input
                            id="tr-debut" type="date" name="periode_debut" required
                            value={form.periode_debut} onChange={changer}
                            max={form.periode_fin || undefined}
                        />
                    </div>
                    <div className="tr-field">
                        <label htmlFor="tr-fin">Période fin *</label>
                        <input
                            id="tr-fin" type="date" name="periode_fin" required
                            value={form.periode_fin} onChange={changer}
                            min={form.periode_debut || undefined}
                        />
                        <div className="tr-hint">Seuls les mouvements de cette période seront extraits</div>
                    </div>
                    <div className="tr-field">
                        <label htmlFor="tr-taux">Taux de conversion</label>
                        <input
                            id="tr-taux" type="number" step="0.001" min="0.001" name="taux_conversion"
                            value={form.taux_conversion} onChange={changer}
                            placeholder={requiertTaux ? `1 ${banque.devise} = ? TND` : 'Compte en TND'}
                            disabled={!requiertTaux}
                        />
                        <div className={`tr-hint ${requiertTaux ? 'warn' : ''}`}>
                            {requiertTaux ? `Obligatoire : compte en ${banque.devise}` : 'Sans objet pour les comptes en dinars'}
                        </div>
                    </div>
                </div>

                <div
                    className={`tr-drop ${drag ? 'drag' : ''} ${form.file ? 'has-file' : ''}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => !form.file && inputRef.current && inputRef.current.click()}
                    onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !form.file) { e.preventDefault(); inputRef.current?.click(); } }}
                    onDragEnter={(e) => { e.preventDefault(); setDrag(true); }}
                    onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
                    onDragLeave={(e) => { e.preventDefault(); setDrag(false); }}
                    onDrop={(e) => { e.preventDefault(); setDrag(false); choisir(e.dataTransfer.files?.[0]); }}
                >
                    <input ref={inputRef} type="file" accept=".pdf,.csv,.txt,.xlsx,.xls" onChange={(e) => choisir(e.target.files?.[0])} />
                    {form.file ? (
                        <>
                            <span className="tr-drop-icon"><FiFile /></span>
                            <div className="tr-drop-body tr-drop-file">
                                <div style={{ minWidth: 0 }}>
                                    <div className="tr-drop-file-name" title={form.file.name}>{form.file.name}</div>
                                    <div className="tr-drop-file-size">{formatTaille(form.file.size)}</div>
                                </div>
                            </div>
                            <button
                                type="button" className="tr-drop-remove" title="Retirer le fichier" aria-label="Retirer le fichier"
                                onClick={(e) => { e.stopPropagation(); setForm((p) => ({ ...p, file: null })); if (inputRef.current) inputRef.current.value = ''; }}
                            >
                                <FiX />
                            </button>
                        </>
                    ) : (
                        <>
                            <span className="tr-drop-icon"><FiUploadCloud /></span>
                            <div className="tr-drop-body">
                                <p className="tr-drop-title">Glissez-déposez l’extrait bancaire du jour</p>
                                <p className="tr-drop-hint">ou cliquez pour parcourir vos fichiers</p>
                                <div className="tr-formats">
                                    <span className="tr-format">.PDF</span>
                                    <span className="tr-format">.CSV</span>
                                    <span className="tr-format">.XLSX</span>
                                    <span className="tr-format">Max 25 Mo</span>
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {erreur && <div className="tr-alert"><FiAlertTriangle /><span>{erreur}</span></div>}

                <div className="tr-actions">
                    <button
                        type="submit"
                        className="btn btn-primary"
                        disabled={charge || !form.file || !form.periode_debut || !form.periode_fin}
                        title={!form.periode_debut || !form.periode_fin ? 'Renseignez la période de début et de fin' : undefined}
                    >
                        {charge ? (<><span className="tr-spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,.35)' }} /> Extraction en cours…</>) : (<><FiPlay /> Importer et extraire</>)}
                    </button>
                </div>
            </form>

            <ListeImports
                imports={imports}
                peutSupprimer={peut.supprimer}
                onOuvrir={onOuvrirImport}
                onSupprimer={onSupprimerImport}
            />
        </>
    );
};

/* ───────── Historique des imports ───────── */
const ListeImports = ({ imports, peutSupprimer, onOuvrir, onSupprimer }) => {
    const [aSupprimer, setASupprimer] = useState(null);
    return (
        <div className="tr-card">
            <h3 className="tr-card-title">
                Extraits importés
                <small>{imports.length} import(s)</small>
            </h3>
            {imports.length === 0 ? (
                <p className="tr-empty">Aucun extrait importé pour le moment.</p>
            ) : (
                <div className="tr-tablewrap">
                    <table className="tr-table">
                        <thead>
                            <tr>
                                <th>Banque</th>
                                <th>Période</th>
                                <th>Fichier</th>
                                <th>Mouvements</th>
                                <th>Débit</th>
                                <th>Crédit</th>
                                <th>Classement</th>
                                <th>Importé le</th>
                                <th />
                            </tr>
                        </thead>
                        <tbody>
                            {imports.map((imp) => (
                                <tr key={imp.id}>
                                    <td>
                                        <div className="tr-bank-name">{imp.compte_banque}</div>
                                        {imp.devise_source && (
                                            <div className="tr-ref">Taux {fmt(imp.taux_conversion)} ({imp.devise_source})</div>
                                        )}
                                    </td>
                                    <td className="tr-date">
                                        {imp.periode_debut || imp.periode_fin
                                            ? `${jour(imp.periode_debut)} → ${jour(imp.periode_fin)}`
                                            : jour(imp.created_at)}
                                    </td>
                                    <td className="tr-libelle" title={imp.file_name}>{imp.file_name}</td>
                                    <td>{imp.total_mouvements}</td>
                                    <td className="tr-num-debit">{montant(imp.total_debit)}</td>
                                    <td className="tr-num-credit">{montant(imp.total_credit)}</td>
                                    <td>
                                        {imp.non_classe_count > 0
                                            ? <span className="tr-tag non">{imp.non_classe_count} à classer</span>
                                            : <span className="tr-tag exp"><FiCheck /> Complet</span>}
                                    </td>
                                    <td className="tr-date">{imp.created_by_username ? `${imp.created_by_username} · ` : ''}{jour(imp.created_at)}</td>
                                    <td>
                                        <div className="tr-row-actions">
                                            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onOuvrir(imp)}>Ouvrir</button>
                                            {peutSupprimer && (
                                                <button type="button" className="btn btn-danger btn-sm" title="Supprimer cet import" onClick={() => setASupprimer(imp)}>
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

            {aSupprimer && (
                <div className="tr-modal-overlay" onClick={() => setASupprimer(null)}>
                    <div className="tr-modal" role="dialog" aria-modal="true" aria-labelledby="tr-confirm-title" onClick={(e) => e.stopPropagation()}>
                        <div className="tr-modal-head">
                            <div>
                                <span className="tr-modal-kicker">Suppression</span>
                                <h3 id="tr-confirm-title">Supprimer cet import ?</h3>
                                <p>{aSupprimer.compte_banque} · {aSupprimer.file_name}</p>
                            </div>
                            <button type="button" className="tr-modal-close" onClick={() => setASupprimer(null)} aria-label="Fermer">×</button>
                        </div>
                        <p className="tr-modal-body">
                            Les {aSupprimer.total_mouvements} mouvements de cet extrait seront supprimés et sortiront du reporting.
                            Cette action est définitive.
                        </p>
                        <div className="tr-modal-foot">
                            <button type="button" className="btn btn-secondary" onClick={() => setASupprimer(null)}>Annuler</button>
                            <button
                                type="button" className="btn btn-danger"
                                onClick={async () => { const cible = aSupprimer; setASupprimer(null); await onSupprimer(cible); }}
                            >
                                <FiTrash2 /> Supprimer
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

/* ───────── Onglet Mouvements ───────── */
const OngletMouvements = ({ banques, peut, importOuvert, onImportConsomme, refreshSignal }) => {
    const [filtres, setFiltres] = useState({ nature: '', search: '', compte_banque: '', date_debut: '', date_fin: '', page: 1 });
    const [donnees, setDonnees] = useState({ items: [], total: 0, page: 1, pages: 1, compteurs: {} });
    const [charge, setCharge] = useState(false);
    const [erreur, setErreur] = useState('');
    const [selection, setSelection] = useState([]);
    const [enCours, setEnCours] = useState({});

    const charger = useCallback(async () => {
        setCharge(true);
        setErreur('');
        try {
            const params = { page: filtres.page, page_size: 50, order: 'desc' };
            if (importOuvert) params.import_id = importOuvert.id;
            if (filtres.nature) params.nature = filtres.nature;
            if (filtres.search.trim()) params.search = filtres.search.trim();
            if (filtres.compte_banque) params.compte_banque = filtres.compte_banque;
            if (filtres.date_debut) params.date_debut = filtres.date_debut;
            if (filtres.date_fin) params.date_fin = filtres.date_fin;
            setDonnees(await ApiService.getTresorerieMovements(params));
        } catch (err) {
            setErreur(err.message || 'Erreur lors du chargement des mouvements.');
        } finally {
            setCharge(false);
        }
    }, [filtres, importOuvert, refreshSignal]);

    useEffect(() => { charger(); }, [charger]);

    // Nouveau filtre ou nouvelle page : la sélection de lot repart de zéro.
    // (Elle survit à un classement unitaire, qui ne change pas les filtres.)
    useEffect(() => { setSelection([]); }, [filtres, importOuvert]);

    const classifier = async (mouvement, nature) => {
        const natureCible = mouvement.nature === nature ? null : nature;
        setEnCours((p) => ({ ...p, [mouvement.id]: true }));
        setErreur('');
        try {
            await ApiService.classerTresorerieMouvement(mouvement.id, natureCible);
            setDonnees((p) => ({
                ...p,
                items: p.items.map((m) => (m.id === mouvement.id ? { ...m, nature: natureCible } : m)),
            }));
        } catch (err) {
            setErreur(err.message || 'Erreur lors du classement.');
        } finally {
            setEnCours((p) => { const s = { ...p }; delete s[mouvement.id]; return s; });
        }
    };

    const classifierLot = async (nature) => {
        if (!selection.length) return;
        const ids = [...selection];
        setEnCours((p) => ({ ...p, lot: true }));
        setErreur('');
        try {
            await ApiService.classerTresorerieMouvements(ids, nature);
            setDonnees((p) => ({ ...p, items: p.items.map((m) => (ids.includes(m.id) ? { ...m, nature } : m)) }));
            setSelection([]);
        } catch (err) {
            setErreur(err.message || 'Erreur lors du classement en lot.');
        } finally {
            setEnCours((p) => { const s = { ...p }; delete s.lot; return s; });
        }
    };

    const basculer = (id) => setSelection((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
    const tousVisibles = donnees.items.length > 0 && donnees.items.every((m) => selection.includes(m.id));
    const basculerTout = () => setSelection(tousVisibles ? [] : donnees.items.map((m) => m.id));

    const majFiltre = (cle, valeur) => setFiltres((p) => ({ ...p, [cle]: valeur, page: cle === 'page' ? valeur : 1 }));

    const compteurs = donnees.compteurs || {};

    return (
        <div className="tr-card">
            <h3 className="tr-card-title">
                Mouvements bancaires
                {importOuvert && (
                    <small>
                        Import {importOuvert.compte_banque} · {importOuvert.file_name}
                        <button type="button" className="btn btn-secondary btn-sm" style={{ marginLeft: '.6rem' }} onClick={onImportConsomme}>
                            Voir tous les imports
                        </button>
                    </small>
                )}
            </h3>

            <div className="tr-toolbar">
                <div className="tr-seg" role="group" aria-label="Filtrer par nature">
                    <button type="button" className={!filtres.nature ? 'on' : ''} onClick={() => majFiltre('nature', '')}>
                        Tous <span className="tr-mini">{Object.values(compteurs).reduce((s, n) => s + Number(n || 0), 0)}</span>
                    </button>
                    <button type="button" className={filtres.nature === 'non_classe' ? 'on' : ''} onClick={() => majFiltre('nature', 'non_classe')}>
                        À classer <span className="tr-mini">{compteurs.non_classe || 0}</span>
                    </button>
                    {Object.entries(NATURES).map(([cle, cfg]) => (
                        <button key={cle} type="button" className={filtres.nature === cle ? 'on' : ''} onClick={() => majFiltre('nature', cle)}>
                            {cfg.label} <span className="tr-mini">{compteurs[cle] || 0}</span>
                        </button>
                    ))}
                </div>
                <input
                    className="tr-input search" placeholder="Rechercher un libellé ou une référence…"
                    value={filtres.search} onChange={(e) => majFiltre('search', e.target.value)}
                />
                <select className="tr-input" value={filtres.compte_banque} onChange={(e) => majFiltre('compte_banque', e.target.value)}>
                    <option value="">Toutes les banques</option>
                    {banques.map((b) => <option key={b.code} value={b.code}>{b.code}</option>)}
                </select>
                <div className="tr-daterange" role="group" aria-label="Filtrer par période">
                    <label htmlFor="tr-date-debut">Du</label>
                    <input
                        id="tr-date-debut" className="tr-input" type="date"
                        value={filtres.date_debut} onChange={(e) => majFiltre('date_debut', e.target.value)}
                    />
                    <label htmlFor="tr-date-fin">Au</label>
                    <input
                        id="tr-date-fin" className="tr-input" type="date"
                        value={filtres.date_fin} onChange={(e) => majFiltre('date_fin', e.target.value)}
                    />
                </div>
            </div>

            {peut.classer && selection.length > 0 && (
                <div className="tr-bulk">
                    <strong>{selection.length}</strong> mouvement(s) sélectionné(s) :
                    {Object.entries(NATURES).map(([cle, cfg]) => (
                        <button key={cle} type="button" className="btn btn-secondary btn-sm" disabled={enCours.lot} onClick={() => classifierLot(cle)}>
                            <span className={`tr-sigle ${cfg.cls}`} aria-hidden="true">{cfg.sigle}</span> {cfg.label}
                        </button>
                    ))}
                    <button type="button" className="btn btn-secondary btn-sm" disabled={enCours.lot} onClick={() => classifierLot(null)}>
                        <FiX /> Déclasser
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelection([])}>Vider</button>
                </div>
            )}

            {erreur && <div className="tr-alert"><FiAlertTriangle /><span>{erreur}</span></div>}

            {charge && donnees.items.length === 0 ? (
                <p className="tr-empty"><span className="tr-loading"><span className="tr-spinner" /> Chargement des mouvements…</span></p>
            ) : donnees.items.length === 0 ? (
                <p className="tr-empty">Aucun mouvement ne correspond à ces filtres.</p>
            ) : (
                <>
                    <div className="tr-tablewrap">
                        <table className="tr-table">
                            <thead>
                                <tr>
                                    {peut.classer && (
                                        <th style={{ width: 34 }}>
                                            <input className="tr-check" type="checkbox" checked={tousVisibles} onChange={basculerTout} aria-label="Tout sélectionner" />
                                        </th>
                                    )}
                                    <th>Date</th>
                                    <th>Banque</th>
                                    <th>Libellé</th>
                                    <th>Débit</th>
                                    <th>Crédit</th>
                                    <th style={{ textAlign: 'center' }}>Classement</th>
                                </tr>
                            </thead>
                            <tbody>
                                {donnees.items.map((m) => (
                                    <tr key={m.id} className={selection.includes(m.id) ? 'selected' : ''}>
                                        {peut.classer && (
                                            <td>
                                                <input
                                                    className="tr-check" type="checkbox" checked={selection.includes(m.id)}
                                                    onChange={() => basculer(m.id)} aria-label={`Sélectionner ${m.libelle}`}
                                                />
                                            </td>
                                        )}
                                        <td className="tr-date">{jour(m.date_operation)}</td>
                                        <td><span className="tr-tag" style={{ background: 'var(--bg-muted)', color: 'var(--text-secondary)' }}>{m.compte_banque}</span></td>
                                        <td className="tr-libelle" title={m.libelle}>
                                            {m.libelle}
                                            {m.reference && <div className="tr-ref">{m.reference}</div>}
                                        </td>
                                        <td className="tr-num-debit">{montant(m.debit)}</td>
                                        <td className="tr-num-credit">{montant(m.credit)}</td>
                                        <td>
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '.5rem', flexWrap: 'wrap' }}>
                                                <div className="tr-class" role="group" aria-label="Classer le mouvement">
                                                    {Object.entries(NATURES).map(([cle, cfg]) => (
                                                        <button
                                                            key={cle}
                                                            type="button"
                                                            className={`tr-class-btn ${m.nature === cle ? cfg.cls : ''}`}
                                                            title={m.nature === cle ? `${cfg.label} (cliquer pour déclasser)` : `Classer en ${cfg.label.toLowerCase()} — ${cfg.aide}`}
                                                            aria-label={`${cfg.label} (${cfg.sigle})`}
                                                            aria-pressed={m.nature === cle}
                                                            disabled={!peut.classer || enCours[m.id]}
                                                            onClick={() => classifier(m, cle)}
                                                        >
                                                            {cfg.sigle}
                                                        </button>
                                                    ))}
                                                </div>
                                                {!m.nature && m.nature_suggeree && peut.classer && (
                                                    <span className="tr-suggest">
                                                        Suggestion : {NATURES[m.nature_suggeree]?.label}
                                                        <button type="button" onClick={() => classifier({ ...m, nature: null }, m.nature_suggeree)} title="Appliquer la suggestion">Appliquer</button>
                                                    </span>
                                                )}
                                                {m.nature && m.classified_by_username && (
                                                    <span className="tr-ref" title={`Classé le ${jour(m.classified_at)}`}>{m.classified_by_username}</span>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <div className="tr-pager">
                        <span>{donnees.total} mouvement(s) · page {donnees.page} / {donnees.pages}</span>
                        <button type="button" disabled={donnees.page <= 1} onClick={() => majFiltre('page', donnees.page - 1)}>
                            <FiChevronLeft /> Précédent
                        </button>
                        <button type="button" disabled={donnees.page >= donnees.pages} onClick={() => majFiltre('page', donnees.page + 1)}>
                            Suivant <FiChevronRight />
                        </button>
                    </div>
                </>
            )}
        </div>
    );
};

/* ───────── Onglet Reporting ───────── */
const OngletReporting = ({ banques, peut }) => {
    const [plage, setPlage] = useState({ date_debut: '', date_fin: '' });
    const [rapport, setRapport] = useState(null);
    const [charge, setCharge] = useState(false);
    const [erreur, setErreur] = useState('');
    const [exportingPdf, setExportingPdf] = useState(false);
    const [pdfPreview, setPdfPreview] = useState({ open: false, url: '', blob: null, filename: '' });

    // Libérer l'URL objet quand la modale se ferme
    useEffect(() => {
        if (!pdfPreview.url) return undefined;
        return () => { if (pdfPreview.url) URL.revokeObjectURL(pdfPreview.url); };
    }, [pdfPreview.url]);

    const charger = useCallback(async () => {
        setCharge(true);
        setErreur('');
        try {
            const params = {};
            if (plage.date_debut) params.date_debut = plage.date_debut;
            if (plage.date_fin) params.date_fin = plage.date_fin;
            setRapport(await ApiService.getTresorerieReporting(params));
        } catch (err) {
            setErreur(err.message || 'Erreur lors du chargement du reporting.');
        } finally {
            setCharge(false);
        }
    }, [plage]);

    useEffect(() => { charger(); }, [charger]);

    const lignes = useMemo(
        () => (rapport?.banques || []).filter((b) => b.nb_mouvements > 0 || b.compte_banque !== 'Autre'),
        [rapport],
    );
    const totaux = rapport?.totaux;
    const controle = rapport?.controle || {};
    // Situation arrêtée : date à laquelle les soldes sont arrêtés, calculée par
    // le backend (borne « Au » si saisie, sinon dernière date de mouvement).
    const dateArret = rapport?.date_arret ?? null;

    // Solde actuel de l'ensemble des banques : repris du total du tableau
    // « Ratios par banque », qui ne somme que les banques dont le solde est
    // calculable. Les banques sans solde sont signalées pour ne pas laisser
    // croire que le montant couvre tout le référentiel.
    const soldeTotal = totaux?.solde ?? null;
    const banquesAvecSolde = lignes.filter((b) => b.solde != null).length;
    const banquesSansSolde = lignes.length - banquesAvecSolde;

    const exporter = () => {
        if (!rapport) return;
        const entetes = [
            'Banque', 'Recette exploitation', 'Dont commissions (recette)', 'Dépense exploitation',
            'Dont commissions (dépense)', 'Trésorerie nette exploitation',
            'Recette hors exploitation', 'Dépense hors exploitation', 'Trésorerie nette hors exploitation',
            'Non classés', 'Débit total', 'Crédit total',
            'Solde de départ', 'Date du solde de départ', 'Solde',
        ];
        const ligne = (b) => [
            b.compte_banque, b.recette_exploitation, b.dont_recette_commission, b.depense_exploitation,
            b.dont_depense_commission, b.tresorerie_nette_exploitation,
            b.recette_hors_exploitation, b.depense_hors_exploitation, b.tresorerie_nette_hors_exploitation,
            b.non_classe_count, b.total_debit, b.total_credit,
            b.solde_ouverture ?? '', b.solde_ouverture_date ?? '', b.solde ?? '',
        ];
        const csv = [entetes, ...lignes.map(ligne), ...(totaux ? [ligne(totaux)] : [])]
            .map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""').replace('.', ',')}"`).join(';'))
            .join('\n');
        const suffixe = plage.date_debut && plage.date_fin ? `${plage.date_debut}_${plage.date_fin}` : 'global';
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' }));
        a.download = `reporting_tresorerie_${suffixe}.csv`;
        a.click();
        URL.revokeObjectURL(a.href);
    };

    const ouvrirPdfPreview = async () => {
        if (!rapport || exportingPdf) return;
        setErreur('');
        setExportingPdf(true);
        try {
            const params = {};
            if (plage.date_debut) params.date_debut = plage.date_debut;
            if (plage.date_fin) params.date_fin = plage.date_fin;
            const blob = await ApiService.exportTresorerieReportingPdf(params);
            const url = URL.createObjectURL(blob);
            const suffixe = plage.date_debut && plage.date_fin
                ? `${plage.date_debut}_${plage.date_fin}`
                : 'global';
            setPdfPreview({ open: true, url, blob, filename: `reporting_tresorerie_${suffixe}.pdf` });
        } catch (err) {
            setErreur(err.message || 'Erreur lors de la génération du PDF.');
        } finally {
            setExportingPdf(false);
        }
    };

    const fermerPdfPreview = () => {
        if (pdfPreview.url) URL.revokeObjectURL(pdfPreview.url);
        setPdfPreview({ open: false, url: '', blob: null, filename: '' });
    };

    const telechargerPdf = () => {
        if (!pdfPreview.blob) return;
        const link = document.createElement('a');
        link.href = pdfPreview.url;
        link.download = pdfPreview.filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        fermerPdfPreview();
    };

    const nomBanque = (code) => banques.find((b) => b.code === code)?.libelle || code;

    return (
        <>
            <div className="tr-card">
                <div className="tr-toolbar" style={{ marginBottom: 0 }}>
                    <div className="tr-field" style={{ minWidth: 170 }}>
                        <label htmlFor="tr-rep-debut">Du</label>
                        <input id="tr-rep-debut" className="tr-input" type="date" value={plage.date_debut}
                            onChange={(e) => setPlage((p) => ({ ...p, date_debut: e.target.value }))} />
                    </div>
                    <div className="tr-field" style={{ minWidth: 170 }}>
                        <label htmlFor="tr-rep-fin">Au</label>
                        <input id="tr-rep-fin" className="tr-input" type="date" value={plage.date_fin}
                            onChange={(e) => setPlage((p) => ({ ...p, date_fin: e.target.value }))} />
                    </div>
                    <button
                        type="button"
                        className="btn btn-secondary btn-sm tr-toolbar-btn"
                        onClick={() => setPlage({ date_debut: '', date_fin: '' })}
                    >
                        Réinitialiser
                    </button>
                    <div className="tr-spacer" />
                    {controle.statut === 'OK' && <span className="tr-chip ok"><FiCheckCircle /> Reporting complet</span>}
                    {controle.statut === 'INCOMPLET' && <span className="tr-chip warn"><FiAlertTriangle /> {controle.non_classes} mouvement(s) non classé(s)</span>}
                    {controle.statut === 'ERREUR' && <span className="tr-chip warn"><FiAlertTriangle /> Écart de contrôle détecté</span>}
                    {peut && (
                        <>
                            <button type="button" className="btn btn-secondary btn-sm" onClick={exporter} disabled={!rapport}>
                                <FiDownload /> Exporter CSV
                            </button>
                            <button
                                type="button"
                                className="btn btn-primary btn-sm"
                                onClick={ouvrirPdfPreview}
                                disabled={!rapport || exportingPdf}
                                title="Prévisualiser et télécharger le rapport PDF"
                            >
                                {exportingPdf
                                    ? <><span className="tr-spinner" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,.35)' }} /> Préparation…</>
                                    : <><FiFileText /> Export PDF</>}
                            </button>
                        </>
                    )}
                </div>
                {erreur && <div className="tr-alert"><FiAlertTriangle /><span>{erreur}</span></div>}
            </div>

            {/* ── Modale de prévisualisation PDF (identique au style RapprochementBancaire) ── */}
            {pdfPreview.open && ReactDOM.createPortal(
                <div className="reco-pdf-modal" role="dialog" aria-modal="true" aria-labelledby="tr-pdf-title">
                    <div className="reco-pdf-dialog">
                        <div className="reco-pdf-header">
                            <div>
                                <span className="reco-opening-eyebrow">Aperçu avant export</span>
                                <h3 id="tr-pdf-title">Rapport de trésorerie</h3>
                            </div>
                            <button type="button" className="reco-modal-close" onClick={fermerPdfPreview} aria-label="Fermer la prévisualisation"><FiX /></button>
                        </div>
                        <div className="reco-pdf-preview">
                            <iframe src={pdfPreview.url} title="Prévisualisation du rapport PDF de trésorerie" />
                        </div>
                        <div className="reco-pdf-footer">
                            <button type="button" className="btn btn-secondary" onClick={fermerPdfPreview}>Annuler</button>
                            <button type="button" className="btn btn-primary" onClick={telechargerPdf}><FiDownload aria-hidden="true" /> Télécharger le PDF</button>
                        </div>
                    </div>
                </div>,
                document.body,
            )}

            {charge && !rapport ? (
                <div className="tr-card"><p className="tr-empty"><span className="tr-loading"><span className="tr-spinner" /> Calcul des ratios…</span></p></div>
            ) : totaux && (
                <>
                    <div className="tr-arret" role="status">
                        <span className="tr-arret-label">Situation arrêtée au</span>
                        <span className="tr-arret-date">{dateArret ? jour(dateArret) : '—'}</span>
                        <span className="tr-arret-note">
                            {dateArret
                                ? (rapport.date_fin
                                    ? 'Borne « Au » du filtre de période'
                                    : 'Dernier mouvement importé')
                                : 'Aucun mouvement sur la période'}
                        </span>
                    </div>

                    <div className="tr-kpis">
                        <div
                            className="tr-kpi tr-kpi-solde"
                            style={{ '--k': soldeTotal != null && soldeTotal < 0 ? 'var(--tr-non)' : 'var(--primary-500)' }}
                            title={
                                soldeTotal == null
                                    ? 'Aucune banque n’a de solde calculable sur cette période'
                                    : `Solde figé + mouvements jusqu’au ${rapport.date_fin ? jour(rapport.date_fin) : 'jour'} · ${banquesAvecSolde} banque(s)`
                            }
                        >
                            <div className="tr-kpi-label">Solde des banques</div>
                            {soldeTotal != null ? (
                                <div className={`tr-kpi-value ${soldeTotal < 0 ? 'neg' : ''}`}>{fmt(soldeTotal)}</div>
                            ) : (
                                <div className="tr-kpi-value tr-nil">n.d.</div>
                            )}
                            <div className="tr-kpi-sub">
                                {soldeTotal == null
                                    ? 'Aucun solde de départ figé'
                                    : banquesSansSolde > 0
                                        ? `Toutes banques · ${banquesSansSolde} banque(s) sans solde`
                                        : 'Toutes banques · au ' + jour(rapport.date_fin)}
                            </div>
                        </div>
                        <div className="tr-kpi" style={{ '--k': 'var(--tr-exp)' }}>
                            <div className="tr-kpi-label">Recette exploitation</div>
                            <div className="tr-kpi-value">{fmt(totaux.recette_exploitation)}</div>
                            <div className="tr-kpi-sub">Exploitation + commissions · toutes banques</div>
                        </div>
                        <div className="tr-kpi" style={{ '--k': 'var(--tr-non)' }}>
                            <div className="tr-kpi-label">Dépense exploitation</div>
                            <div className="tr-kpi-value">{fmt(totaux.depense_exploitation)}</div>
                            <div className="tr-kpi-sub">Exploitation + commissions · toutes banques</div>
                        </div>
                        <div className="tr-kpi" style={{ '--k': totaux.tresorerie_nette_exploitation >= 0 ? 'var(--tr-exp)' : 'var(--tr-non)' }}>
                            <div className="tr-kpi-label">Trésorerie nette exploitation</div>
                            <div className={`tr-kpi-value ${totaux.tresorerie_nette_exploitation < 0 ? 'neg' : ''}`}>
                                {fmt(totaux.tresorerie_nette_exploitation)}
                            </div>
                            <div className="tr-kpi-sub">Recette − dépense d’exploitation</div>
                        </div>
                        <div className="tr-kpi" style={{ '--k': 'var(--tr-hors)' }}>
                            <div className="tr-kpi-label">Recette hors exploitation</div>
                            <div className="tr-kpi-value">{fmt(totaux.recette_hors_exploitation)}</div>
                            <div className="tr-kpi-sub">Toutes banques</div>
                        </div>
                        <div className="tr-kpi" style={{ '--k': 'var(--tr-hors)' }}>
                            <div className="tr-kpi-label">Dépense hors exploitation</div>
                            <div className="tr-kpi-value">{fmt(totaux.depense_hors_exploitation)}</div>
                            <div className="tr-kpi-sub">Toutes banques</div>
                        </div>
                        <div className="tr-kpi" style={{ '--k': totaux.tresorerie_nette_hors_exploitation >= 0 ? 'var(--tr-hors)' : 'var(--tr-non)' }}>
                            <div className="tr-kpi-label">Trésorerie nette hors exploitation</div>
                            <div className={`tr-kpi-value ${totaux.tresorerie_nette_hors_exploitation < 0 ? 'neg' : ''}`}>
                                {fmt(totaux.tresorerie_nette_hors_exploitation)}
                            </div>
                            <div className="tr-kpi-sub">Recette − dépense hors exploitation</div>
                        </div>
                    </div>

                    <div className="tr-card">
                        <h3 className="tr-card-title">
                            Ratios par banque
                            <small>
                                {rapport.date_debut || rapport.date_fin
                                    ? `Du ${jour(rapport.date_debut)} au ${jour(rapport.date_fin)}`
                                    : 'Toutes périodes'}
                            </small>
                        </h3>

                        <div className="tr-tablewrap">
                            <table className="tr-table tr-report">
                                <thead>
                                    <tr>
                                        <th rowSpan="2">Banque</th>
                                        <th colSpan="5" className="tr-grp-exp">Exploitation (commissions incluses)</th>
                                        <th colSpan="3" className="tr-grp-hors">Hors exploitation</th>
                                        <th colSpan="2" className="tr-grp-solde">Solde du compte</th>
                                        <th rowSpan="2">Non classés</th>
                                    </tr>
                                    <tr>
                                        <th>Recette</th>
                                        <th>dont comm.</th>
                                        <th>Dépense</th>
                                        <th>dont comm.</th>
                                        <th>Trésorerie nette</th>
                                        <th>Recette</th>
                                        <th>Dépense</th>
                                        <th>Trésorerie nette</th>
                                        <th>Solde de départ</th>
                                        <th>Solde</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {lignes.map((b) => (
                                        <tr key={b.compte_banque}>
                                            <td>
                                                <div className="tr-bank-name">{b.compte_banque}</div>
                                                <div className="tr-bank-code">{nomBanque(b.compte_banque)}</div>
                                            </td>
                                            <td className="tr-col-exp">{montant(b.recette_exploitation)}</td>
                                            <td className="tr-col-exp">{montant(b.dont_recette_commission)}</td>
                                            <td className="tr-col-exp">{montant(b.depense_exploitation)}</td>
                                            <td className="tr-col-exp">{montant(b.dont_depense_commission)}</td>
                                            <td className={`tr-col-exp tr-strong ${b.tresorerie_nette_exploitation < 0 ? 'tr-num-debit' : ''}`}>
                                                {montant(b.tresorerie_nette_exploitation)}
                                            </td>
                                            <td className="tr-col-hors">{montant(b.recette_hors_exploitation)}</td>
                                            <td className="tr-col-hors">{montant(b.depense_hors_exploitation)}</td>
                                            <td className={`tr-col-hors tr-strong ${b.tresorerie_nette_hors_exploitation < 0 ? 'tr-num-debit' : ''}`}>
                                                {montant(b.tresorerie_nette_hors_exploitation)}
                                            </td>
                                            <td className="tr-col-solde tr-nil" title={b.solde_ouverture_date ? `Solde au ${jour(b.solde_ouverture_date)} (veille de la période)` : 'Solde de départ non calculable pour cette période'}>
                                                {b.solde_ouverture != null ? (
                                                    <>
                                                        {fmt(b.solde_ouverture)}
                                                        {b.solde_ouverture_date && (
                                                            <div className="tr-solde-date">{jour(b.solde_ouverture_date)}</div>
                                                        )}
                                                    </>
                                                ) : 'n.d.'}
                                            </td>
                                            <td className={`tr-col-solde tr-strong ${b.solde != null && b.solde < 0 ? 'tr-num-debit' : ''}`}>
                                                {b.solde != null ? fmt(b.solde) : <span className="tr-nil">n.d.</span>}
                                            </td>
                                            <td>{b.non_classe_count > 0 ? <span className="tr-tag non">{b.non_classe_count}</span> : <span className="tr-nil">–</span>}</td>
                                        </tr>
                                    ))}
                                </tbody>
                                <tfoot>
                                    <tr>
                                        <td>Total toutes banques</td>
                                        <td className="tr-col-exp">{fmt(totaux.recette_exploitation)}</td>
                                        <td className="tr-col-exp">{fmt(totaux.dont_recette_commission)}</td>
                                        <td className="tr-col-exp">{fmt(totaux.depense_exploitation)}</td>
                                        <td className="tr-col-exp">{fmt(totaux.dont_depense_commission)}</td>
                                        <td className="tr-col-exp">{fmt(totaux.tresorerie_nette_exploitation)}</td>
                                        <td className="tr-col-hors">{fmt(totaux.recette_hors_exploitation)}</td>
                                        <td className="tr-col-hors">{fmt(totaux.depense_hors_exploitation)}</td>
                                        <td className="tr-col-hors">{fmt(totaux.tresorerie_nette_hors_exploitation)}</td>
                                        <td className="tr-col-solde">{totaux.solde_ouverture != null ? fmt(totaux.solde_ouverture) : <span className="tr-nil">n.d.</span>}</td>
                                        <td className="tr-col-solde">{totaux.solde != null ? fmt(totaux.solde) : <span className="tr-nil">n.d.</span>}</td>
                                        <td>{totaux.non_classe_count > 0 ? <span className="tr-tag non">{totaux.non_classe_count}</span> : '–'}</td>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>

                        <p className="tr-formula" style={{ marginTop: '.9rem' }}>
                            Recette exploitation = crédits d’exploitation + commissions · Dépense exploitation = débits d’exploitation + commissions ·
                            Trésorerie nette = recette − dépense
                        </p>
                        {controle.statut !== 'OK' && controle.statut !== undefined && (
                            <div className="tr-alert" style={{ marginTop: '.9rem' }}>
                                <FiAlertTriangle />
                                <span>
                                    {controle.statut === 'INCOMPLET'
                                        ? `${controle.non_classes} mouvement(s) ne sont pas encore classés et n’entrent dans aucun ratio. Ouvrez l’onglet Mouvements pour les classer.`
                                        : `Contrôle de cohérence en échec (écart débit ${fmtCourt(controle.ecart_debit)}, écart crédit ${fmtCourt(controle.ecart_credit)}).`}
                                </span>
                            </div>
                        )}

                        <p className="tr-formula" style={{ marginTop: '.6rem' }}>
                            Solde de départ = solde figé projeté à la veille du {rapport.date_debut ? jour(rapport.date_debut) : 'début de période'} ·
                            Solde = solde figé + mouvements jusqu’au {rapport.date_fin ? jour(rapport.date_fin) : 'jour'}
                        </p>
                    </div>

                </>
            )}
        </>
    );
};

/* ───────── Composant principal ───────── */
const Tresorerie = ({ refreshTrigger = 0 }) => {
    const { has } = useAuth();
    const peut = {
        lire: has('tresorerie.read'),
        importer: has('tresorerie.import'),
        classer: has('tresorerie.classify'),
        supprimer: has('tresorerie.delete'),
        rapport: has('tresorerie.report'),
    };
    const ongletParDefaut = peut.importer ? 'import' : peut.lire ? 'mouvements' : 'reporting';
    const [onglet, setOnglet] = useState(ongletParDefaut);
    const [banques, setBanques] = useState([]);
    const [resume, setResume] = useState(null);
    const [imports, setImports] = useState([]);
    const [importOuvert, setImportOuvert] = useState(null);
    const [soldeAValider, setSoldeAValider] = useState(null);
    const [controleExtraction, setControleExtraction] = useState(null);
    const [message, setMessage] = useState('');
    const [erreur, setErreur] = useState('');

    const chargerContexte = useCallback(async () => {
        try {
            const [listeBanques, synthese, historique] = await Promise.all([
                ApiService.getTresorerieBanques(),
                ApiService.getTresorerieSummary(),
                ApiService.getTresorerieImports({ page: 1, page_size: 50 }),
            ]);
            setBanques(Array.isArray(listeBanques) ? listeBanques : []);
            setResume(synthese);
            setImports(Array.isArray(historique.items) ? historique.items : []);
        } catch (err) {
            setErreur(err.message || 'Erreur lors du chargement du module.');
        }
    }, []);

    const enregistrerSolde = async (compteBanque, solde, dateSolde) => {
        await ApiService.setTresorerieSoldeOuverture(compteBanque, solde, dateSolde);
        setMessage(`Solde de départ de ${compteBanque} enregistré.`);
        await chargerContexte();
    };

    useEffect(() => { chargerContexte(); }, [chargerContexte]);
    // Un autre poste a importé ou classé des mouvements : on réactualise les entêtes.
    useEffect(() => { if (refreshTrigger) chargerContexte(); }, [refreshTrigger]);
    useEffect(() => {
        if (!message) return undefined;
        const t = setTimeout(() => setMessage(''), 4000);
        return () => clearTimeout(t);
    }, [message]);

    const importer = async (payload) => {
        const resultat = await ApiService.uploadTresorerieExtrait(payload);
        setControleExtraction(resultat?.controle_extraction || null);
        const figement = resultat?.solde_ouverture_fige
            ? ' Solde de départ de la banque figé à partir de ce relevé.'
            : '';
        setMessage(`${resultat.total_mouvements} mouvement(s) extraits pour ${resultat.import_batch.compte_banque}.${figement}`);
        await chargerContexte();
        if (peut.lire) {
            setImportOuvert(resultat.import_batch);
            setOnglet('mouvements');
        }
        return resultat;
    };

    const ouvrirImport = (imp) => {
        setImportOuvert(imp);
        setOnglet('mouvements');
    };

    const supprimerImport = async (imp) => {
        try {
            await ApiService.deleteTresorerieImport(imp.id);
            if (importOuvert?.id === imp.id) setImportOuvert(null);
            setMessage(`Import ${imp.compte_banque} supprimé.`);
            await chargerContexte();
        } catch (err) {
            setErreur(err.message || 'Erreur lors de la suppression.');
        }
    };

    return (
        <div className="tr">
            <Entete resume={resume} onglet={onglet} setOnglet={setOnglet} peut={peut} nbImports={imports.length} />

            {erreur && <div className="tr-alert"><FiAlertTriangle /><span>{erreur}</span></div>}
            {message && <div className="tr-alert ok"><FiCheckCircle /><span>{message}</span></div>}

            {onglet === 'import' && (
                <OngletImport
                    banques={banques}
                    peut={peut}
                    onImporte={importer}
                    imports={imports}
                    onOuvrirImport={ouvrirImport}
                    onSupprimerImport={supprimerImport}
                    onSoldeAValider={setSoldeAValider}
                />
            )}
            {onglet === 'mouvements' && peut.lire && (
                <OngletMouvements
                    banques={banques}
                    peut={peut}
                    importOuvert={importOuvert}
                    onImportConsomme={() => setImportOuvert(null)}
                    refreshSignal={refreshTrigger}
                />
            )}
            {onglet === 'reporting' && peut.rapport && (
                <OngletReporting banques={banques} peut={peut.rapport} />
            )}

            {controleExtraction && (
                <ExtractionControlModal
                    controls={controleExtraction}
                    title="Contrôle de l’extraction de l’extrait bancaire"
                    onClose={() => { setControleExtraction(null); setSoldeAValider(null); }}
                    primaryLabel="Poursuivre"
                >
                    {soldeAValider && (
                        <BlocSoldeDepart
                            lecture={soldeAValider}
                            onValider={enregistrerSolde}
                        />
                    )}
                </ExtractionControlModal>
            )}
        </div>
    );
};

export default Tresorerie;
