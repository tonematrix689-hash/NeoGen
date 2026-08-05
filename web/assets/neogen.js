/* Puter-first browser services for NeoGen.
 *
 * Puter owns browser identity, AI inference, and cloud persistence. Local
 * repository and terminal mutations remain behind NeoGen's guarded API.
 */
(function attachNeoGenPuter(global) {
  "use strict";

  const ROOT = "NeoGen";

  function requirePuter() {
    if (!global.puter) {
      throw new Error("Puter.js is unavailable. Serve NeoGen over HTTP and reload the page.");
    }
    return global.puter;
  }

  function normalizeChatResponse(response) {
    if (typeof response === "string") return response;
    if (typeof response?.message?.content === "string") return response.message.content;
    if (typeof response?.content === "string") return response.content;
    return JSON.stringify(response);
  }

  class NeoGenPuterClient {
    constructor() {
      this.user = null;
    }

    async restoreSession() {
      const puter = requirePuter();
      if (!puter.auth.isSignedIn()) return null;
      this.user = await puter.auth.getUser();
      return this.user;
    }

    async signIn() {
      const puter = requirePuter();
      await puter.auth.signIn();
      this.user = await puter.auth.getUser();
      return this.user;
    }

    async signOut() {
      const puter = requirePuter();
      await puter.auth.signOut();
      this.user = null;
    }

    async chat(messages, options = {}) {
      const puter = requirePuter();
      const response = await puter.ai.chat(messages, options);
      return normalizeChatResponse(response);
    }

    async saveJson(path, value) {
      const puter = requirePuter();
      return puter.fs.write(
        `${ROOT}/${path}`,
        JSON.stringify(value, null, 2),
        { createMissingParents: true, overwrite: true }
      );
    }

    async loadJson(path, fallback = null) {
      try {
        const blob = await requirePuter().fs.read(`${ROOT}/${path}`);
        return JSON.parse(await blob.text());
      } catch {
        return fallback;
      }
    }

    async backupConversation(conversationId, messages) {
      if (!this.user) return null;
      return this.saveJson(`conversations/${conversationId}.json`, {
        id: conversationId,
        messages,
        updated_at: new Date().toISOString(),
      });
    }

    async saveSetting(key, value) {
      return requirePuter().kv.set(`neogen:${key}`, value);
    }

    async loadSetting(key, fallback = null) {
      const value = await requirePuter().kv.get(`neogen:${key}`);
      return value ?? fallback;
    }

    async publish(subdomain, directory = ROOT) {
      const approved = global.confirm(
        `Publish the Puter directory ${directory} at ${subdomain}.puter.site?`
      );
      if (!approved) throw new Error("Puter publication denied");
      return requirePuter().hosting.create(subdomain, directory);
    }
  }

  global.neogenPuter = new NeoGenPuterClient();
})(globalThis);
