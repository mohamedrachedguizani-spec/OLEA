// src/components/sage-bfc/SageBfcUpload.js
import React, { useState, useRef, useCallback } from 'react';

const ACCEPTED_EXTENSIONS = ['.xlsx', '.xls', '.csv'];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

function SageBfcUpload({ onFileParse, loading, mappingStats }) {
    const [dragActive, setDragActive] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const [periode, setPeriode] = useState('');
    const [fileError, setFileError] = useState(null);
    const inputRef = useRef(null);

    const validateFile = useCallback((file) => {
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (!ACCEPTED_EXTENSIONS.includes(ext)) {
            return `Format non supporté (${ext}). Formats acceptés: ${ACCEPTED_EXTENSIONS.join(', ')}`;
        }
        if (file.size > MAX_FILE_SIZE) {
            return `Fichier trop volumineux (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum: 10 MB`;
        }
        return null;
    }, []);

    const handleFile = useCallback((file) => {
        setFileError(null);
        const error = validateFile(file);
        if (error) {
            setFileError(error);
            setSelectedFile(null);
            return;
        }
        setSelectedFile(file);
    }, [validateFile]);

    // Drag & Drop handlers
    const handleDrag = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === 'dragenter' || e.type === 'dragover') {
            setDragActive(true);
        } else if (e.type === 'dragleave') {
            setDragActive(false);
        }
    }, []);

    const handleDrop = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleFile(e.dataTransfer.files[0]);
        }
    }, [handleFile]);

    const handleChange = useCallback((e) => {
        if (e.target.files && e.target.files[0]) {
            handleFile(e.target.files[0]);
        }
    }, [handleFile]);

    const handleSubmit = useCallback(() => {
        if (!selectedFile || !periode) return;
        onFileParse(selectedFile, periode);
    }, [selectedFile, periode, onFileParse]);

    const handleRemoveFile = useCallback(() => {
        setSelectedFile(null);
        setFileError(null);
        if (inputRef.current) inputRef.current.value = '';
    }, []);

    const getFileIcon = (filename) => {
        const ext = filename.split('.').pop().toLowerCase();
        if (ext === 'csv') return '📊';
        return '📗';
    };

    const formatFileSize = (bytes) => {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    };

    return (
        <div className="sage-upload-section">
            {/* Zone de drop */}
            <div
                className={`sage-dropzone ${dragActive ? 'drag-active' : ''} ${selectedFile ? 'has-file' : ''} ${fileError ? 'has-error' : ''}`}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                onClick={() => !selectedFile && inputRef.current?.click()}
            >
                <input
                    ref={inputRef}
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    onChange={handleChange}
                    className="sage-file-input"
                />

                {!selectedFile ? (
                    <div className="dropzone-content">
                        <div className={`dropzone-icon ${dragActive ? 'bounce' : ''}`}>
                            <svg viewBox="0 0 64 64" fill="none" stroke="currentColor" strokeWidth="2">
                                <rect x="8" y="8" width="48" height="48" rx="8" strokeDasharray="6 3" />
                                <path d="M32 22v20M22 32h20" strokeWidth="3" strokeLinecap="round" />
                            </svg>
                        </div>
                        <h3 className="dropzone-title">
                            {dragActive ? 'Déposez le fichier ici' : 'Glissez-déposez votre balance SAGE'}
                        </h3>
                        <p className="dropzone-hint">
                            ou <span className="dropzone-link">parcourez vos fichiers</span>
                        </p>
                        <div className="dropzone-formats">
                            <span className="format-tag">.xlsx</span>
                            <span className="format-tag">.xls</span>
                            <span className="format-tag">.csv</span>
                            <span className="format-size">Max. 10 MB</span>
                        </div>
                    </div>
                ) : (
                    <div className="dropzone-file-preview">
                        <div className="file-preview-icon">{getFileIcon(selectedFile.name)}</div>
                        <div className="file-preview-info">
                            <span className="file-preview-name">{selectedFile.name}</span>
                            <span className="file-preview-size">{formatFileSize(selectedFile.size)}</span>
                        </div>
                        <button
                            className="file-preview-remove"
                            onClick={(e) => { e.stopPropagation(); handleRemoveFile(); }}
                            title="Retirer le fichier"
                        >
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <line x1="18" y1="6" x2="6" y2="18"/>
                                <line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                        </button>
                    </div>
                )}

                {fileError && (
                    <div className="dropzone-error">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/>
                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                        </svg>
                        <span>{fileError}</span>
                    </div>
                )}
            </div>

            {/* Période comptable (obligatoire) */}
            <div className="sage-upload-periode">
                <div className="periode-group">
                    <label className="periode-label">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                            <line x1="16" y1="2" x2="16" y2="6"/>
                            <line x1="8" y1="2" x2="8" y2="6"/>
                            <line x1="3" y1="10" x2="21" y2="10"/>
                        </svg>
                        <span>Période comptable <span className="required-star">*</span></span>
                    </label>
                    <input
                        type="month"
                        value={periode}
                        onChange={(e) => setPeriode(e.target.value)}
                        className={`periode-input ${!periode && selectedFile ? 'periode-missing' : ''}`}
                        placeholder="AAAA-MM"
                        required
                    />
                    {!periode && selectedFile && (
                        <span className="periode-hint-required">
                            Veuillez sélectionner la période avant de lancer le parsing
                        </span>
                    )}
                </div>
            </div>

            {/* Bouton de parsing */}
            <button
                className={`btn-sage-parse ${loading ? 'loading' : ''}`}
                onClick={handleSubmit}
                disabled={!selectedFile || !periode || loading}
            >
                {loading ? (
                    <>
                        <span className="spinner" />
                        Analyse en cours...
                    </>
                ) : (
                    <>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <polygon points="5,3 19,12 5,21 5,3"/>
                        </svg>
                        Lancer le parsing
                    </>
                )}
            </button>

        </div>
    );
}

export default SageBfcUpload;
