// src/hooks/useLiveUpdates.js
//
// Hook React qui maintient une connexion WebSocket persistante vers le backend.
// Quand un autre utilisateur effectue une opération (ajout, modification,
// suppression, migration), le hook déclenche les callbacks enregistrés
// pour que les composants rafraîchissent automatiquement leurs données.
//
// Usage :
//   useLiveUpdates({
//       caisse:    () => loadEcritures(),
//       migration: () => loadEcrituresAMigrer(),
//   });

import { useEffect, useRef, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';

const WS_URL = API_BASE_URL.replace(/^http/i, 'ws') + '/ws/live';
const RECONNECT_DELAY = 3000; // ms avant reconnexion

export default function useLiveUpdates(handlers = {}, options = {}) {
    const { enabled = true } = options;
    const wsRef = useRef(null);
    const handlersRef = useRef(handlers);
    const reconnectTimer = useRef(null);

    // Toujours pointer vers la dernière version des handlers
    useEffect(() => {
        handlersRef.current = handlers;
    }, [handlers]);

    const connect = useCallback(() => {
        // Éviter les connexions multiples
        if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) {
            return;
        }

        const ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            console.log('[OLEA Live] ✅ Connecté');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                const { channel, action, payload } = data;

                console.log(`[OLEA Live] 📡 ${channel}/${action}`, payload);

                // Appeler le handler correspondant au channel
                const handler = handlersRef.current[channel];
                if (typeof handler === 'function') {
                    handler(action, payload);
                }
            } catch (err) {
                console.warn('[OLEA Live] Message invalide:', err);
            }
        };

        ws.onclose = (event) => {
            console.log('[OLEA Live] 🔌 Déconnecté — reconnexion dans 3s…');
            wsRef.current = null;
            if (event?.code === 1008) {
                // Rejet explicite côté backend (auth/session invalide)
                window.dispatchEvent(new CustomEvent('auth:session-expired'));
                return;
            }
            // Auto-reconnexion
            if (enabled) {
                reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
            }
        };

        ws.onerror = () => {
            // onclose sera appelé juste après
        };

        wsRef.current = ws;
    }, [enabled]);

    useEffect(() => {
        if (!enabled) {
            clearTimeout(reconnectTimer.current);
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
            return;
        }

        connect();

        return () => {
            // Nettoyage à la destruction du composant
            clearTimeout(reconnectTimer.current);
            if (wsRef.current) {
                wsRef.current.close();
                wsRef.current = null;
            }
        };
    }, [connect, enabled]);
}
