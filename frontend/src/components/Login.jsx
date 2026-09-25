// src/components/Login.js
import React, { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import oleaLogo from '../assets/olea-logo.svg';

function Login() {
    const { login } = useAuth();
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setLoading(true);
        try {
            await login(username, password);
        } catch (err) {
            setError(err.message || 'Identifiants incorrects');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="login-page">
            <div className="login-container">
                {/* Left: branding */}
                <div className="login-brand-panel">
                    <div className="login-brand-content">
                        <div className="login-logo">
                            <img
                                src={oleaLogo}
                                alt="OLEA Insurance Solutions Africa"
                                className="login-logo-image"
                            />
                        </div>
                        <div className="login-brand-copy">
                            <span className="login-brand-eyebrow">OLEA Finance</span>
                            <h1 className="login-brand-heading">Votre pilotage financier, réuni en un seul espace.</h1>
                            <p className="login-brand-description">
                                Suivez vos opérations, analysez vos résultats et prenez des décisions éclairées.
                            </p>
                        </div>
                        {/* <div className="login-brand-features" aria-label="Fonctionnalités principales">
                            <div className="login-feature">
                                <span className="login-feature-icon">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m5 12 4 4L19 6"/></svg>
                                </span>
                                <div><strong>Suivi centralisé</strong><small>Une vue claire de vos activités financières</small></div>
                            </div>
                            <div className="login-feature">
                                <span className="login-feature-icon">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19V9m5 10V5m5 14v-7m5 7V3"/></svg>
                                </span>
                                <div><strong>Analyse décisionnelle</strong><small>Des indicateurs utiles pour piloter l’activité</small></div>
                            </div>
                            <div className="login-feature">
                                <span className="login-feature-icon">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg>
                                </span>
                                <div><strong>Accès sécurisé</strong><small>Des droits adaptés à chaque profil</small></div>
                            </div>
                        </div> */}
                        {/* <div className="login-brand-status"><span /> Plateforme de gestion OLEA</div> */}
                    </div>
                </div>

                {/* Right: form */}
                <div className="login-form-panel">
                    <div className="login-form-content">
                        <div className="login-form-header">
                            {/* <span className="login-badge">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></svg>
                                Espace sécurisé
                            </span> */}
                            <h2 className="login-title">Bienvenue</h2>
                            <p className="login-subtitle">Connectez-vous pour accéder à votre espace de gestion.</p>
                        </div>

                        {error && (
                            <div className="login-error" role="alert">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <circle cx="12" cy="12" r="10"/>
                                    <line x1="15" y1="9" x2="9" y2="15"/>
                                    <line x1="9" y1="9" x2="15" y2="15"/>
                                </svg>
                                <span>{error}</span>
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="login-form">
                            <div className="login-field">
                                <label htmlFor="username">Nom d'utilisateur</label>
                                <div className="login-input-wrapper">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                                        <circle cx="12" cy="7" r="4"/>
                                    </svg>
                                    <input
                                        id="username"
                                        type="text"
                                        value={username}
                                        onChange={(e) => {
                                            setUsername(e.target.value);
                                            if (error) setError('');
                                        }}
                                        placeholder="Entrez votre identifiant"
                                        required
                                        autoComplete="username"
                                        autoFocus
                                        disabled={loading}
                                        aria-invalid={Boolean(error)}
                                    />
                                </div>
                            </div>

                            <div className="login-field">
                                <label htmlFor="password">Mot de passe</label>
                                <div className="login-input-wrapper">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                                        <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                                    </svg>
                                    <input
                                        id="password"
                                        type={showPassword ? 'text' : 'password'}
                                        value={password}
                                        onChange={(e) => {
                                            setPassword(e.target.value);
                                            if (error) setError('');
                                        }}
                                        placeholder="Entrez votre mot de passe"
                                        required
                                        autoComplete="current-password"
                                        disabled={loading}
                                        aria-invalid={Boolean(error)}
                                    />
                                    <button
                                        type="button"
                                        className="login-toggle-password"
                                        onClick={() => setShowPassword(!showPassword)}
                                        disabled={loading}
                                        aria-label={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
                                        title={showPassword ? 'Masquer le mot de passe' : 'Afficher le mot de passe'}
                                    >
                                        {showPassword ? (
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/>
                                                <line x1="1" y1="1" x2="23" y2="23"/>
                                            </svg>
                                        ) : (
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                                                <circle cx="12" cy="12" r="3"/>
                                            </svg>
                                        )}
                                    </button>
                                </div>
                            </div>

                            <button
                                type="submit"
                                className="login-submit-btn"
                                disabled={loading || !username || !password}
                            >
                                {loading ? (
                                    <>
                                        <span className="login-spinner"></span>
                                        Connexion en cours…
                                    </>
                                ) : (
                                    <>
                                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/>
                                            <polyline points="10 17 15 12 10 7"/>
                                            <line x1="15" y1="12" x2="3" y2="12"/>
                                        </svg>
                                        Se connecter
                                    </>
                                )}
                            </button>
                        </form>

                        <div className="login-footer-text">
                            <span className="login-footer-help">Besoin d’accès ? Contactez votre administrateur.</span>
                            <span>© {new Date().getFullYear()} OLEA Tunisie · Tous droits réservés</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default Login;
