/**
 * API-Client für den Sensor Logger API Server
 * Diese Datei kann von allen HTML-Seiten verwendet werden
 */

const API = {
    BASE_URL: "/api",

    /**
     * Reports aktualisieren
     * @returns {Promise<Object>} Response vom Server
     */
    async updateReports() {
        try {
            const response = await fetch(this.BASE_URL + "/update", {
                method: "POST"
            });
            return await response.json();
        } catch (error) {
            console.error("API Error:", error);
            throw error;
        }
    },

    /**
     * Generischer GET-Request
     * @param {string} endpoint - z.B. "/status"
     * @returns {Promise<Object>} Response vom Server
     */
    async get(endpoint) {
        try {
            const response = await fetch(this.BASE_URL + endpoint);
            return await response.json();
        } catch (error) {
            console.error("API Error:", error);
            throw error;
        }
    },

    /**
     * Generischer POST-Request
     * @param {string} endpoint - z.B. "/action"
     * @param {Object} data - Zu sendende Daten
     * @returns {Promise<Object>} Response vom Server
     */
    async post(endpoint, data = {}) {
        try {
            const response = await fetch(this.BASE_URL + endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(data)
            });
            return await response.json();
        } catch (error) {
            console.error("API Error:", error);
            throw error;
        }
    }
};
