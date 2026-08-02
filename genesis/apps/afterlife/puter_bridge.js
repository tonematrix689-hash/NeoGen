/* NeoGen governed Puter.js integration.
 *
 * Requires Puter.js v2 in the page:
 *   <script src="https://js.puter.com/v2/"></script>
 *
 * The bridge deliberately exposes an allowlisted surface. Destructive and
 * publishing operations require an explicit approval callback.
 */

(function attachNeoGenPuter(global) {
  "use strict";

  class PuterBridgeError extends Error {}

  const HIGH_RISK = new Set([
    "fs.delete",
    "apps.create",
    "apps.update",
    "apps.delete",
    "hosting.create",
    "hosting.update",
    "hosting.delete",
  ]);

  const ALLOWED = new Set([
    "auth.signIn",
    "auth.signOut",
    "auth.isSignedIn",
    "auth.getUser",
    "ai.chat",
    "ai.listModels",
    "ai.listModelProviders",
    "ai.txt2img",
    "ai.img2txt",
    "ai.txt2speech",
    "ai.txt2vid",
    "ai.speech2txt",
    "fs.write",
    "fs.read",
    "fs.mkdir",
    "fs.readdir",
    "fs.rename",
    "fs.copy",
    "fs.move",
    "fs.stat",
    "fs.delete",
    "fs.upload",
    "kv.set",
    "kv.get",
    "kv.del",
    "kv.list",
    "kv.incr",
    "kv.decr",
    "apps.create",
    "apps.list",
    "apps.get",
    "apps.update",
    "apps.delete",
    "hosting.create",
    "hosting.list",
    "hosting.get",
    "hosting.update",
    "hosting.delete",
  ]);

  function resolveMethod(root, path) {
    const parts = path.split(".");
    const methodName = parts.pop();
    let owner = root;
    for (const part of parts) {
      owner = owner && owner[part];
    }
    const method = owner && owner[methodName];
    if (typeof method !== "function") {
      throw new PuterBridgeError(`Puter capability is unavailable: ${path}`);
    }
    return method.bind(owner);
  }

  function normalizeChatResponse(response) {
    if (typeof response === "string") return response;
    if (response && typeof response.message?.content === "string") {
      return response.message.content;
    }
    if (response && typeof response.content === "string") return response.content;
    return JSON.stringify(response);
  }

  class NeoGenPuterBridge {
    constructor(options = {}) {
      this.approve = options.approve || (async () => false);
      this.onEvent = options.onEvent || (() => {});
      this.defaultModel = options.defaultModel || null;
      this.ready = false;
    }

    initialize() {
      if (!global.puter) {
        throw new PuterBridgeError(
          "Puter.js is not loaded. Include https://js.puter.com/v2/ before puter_bridge.js."
        );
      }
      this.ready = true;
      this.emit("PuterBridgeReady", { capabilities: [...ALLOWED] });
      return this;
    }

    emit(type, payload = {}) {
      this.onEvent({ type, source: "neogen.puter", payload, timestamp: new Date().toISOString() });
    }

    async ensureSignedIn({ interactive = false } = {}) {
      this.assertReady();
      const signedIn = await global.puter.auth.isSignedIn();
      if (signedIn) return global.puter.auth.getUser();
      if (!interactive) return null;
      // Puter requires signIn() to originate from a user action in websites.
      const result = await global.puter.auth.signIn();
      this.emit("PuterSignedIn", {});
      return result;
    }

    async invoke(path, args = [], context = {}) {
      this.assertReady();
      if (!ALLOWED.has(path)) {
        throw new PuterBridgeError(`Capability is not allowlisted: ${path}`);
      }

      if (HIGH_RISK.has(path)) {
        const approved = await this.approve({
          provider: "puter",
          capability: path,
          args,
          reason: context.reason || "NeoGen requested a high-impact Puter operation",
        });
        if (!approved) {
          this.emit("PuterOperationDenied", { capability: path });
          throw new PuterBridgeError(`User approval denied for ${path}`);
        }
      }

      this.emit("PuterOperationStarted", { capability: path });
      try {
        const result = await resolveMethod(global.puter, path)(...args);
        this.emit("PuterOperationCompleted", { capability: path });
        return result;
      } catch (error) {
        this.emit("PuterOperationFailed", {
          capability: path,
          error: String(error?.message || error),
        });
        throw error;
      }
    }

    async chat(prompt, options = {}) {
      const modelOptions = { ...options };
      if (!modelOptions.model && this.defaultModel) modelOptions.model = this.defaultModel;
      const response = await this.invoke("ai.chat", [prompt, modelOptions]);
      return normalizeChatResponse(response);
    }

    async listModels() {
      return this.invoke("ai.listModels");
    }

    async saveJson(path, value) {
      return this.invoke("fs.write", [path, JSON.stringify(value, null, 2), { createMissingParents: true }]);
    }

    async loadJson(path, fallback = null) {
      try {
        const blob = await this.invoke("fs.read", [path]);
        return JSON.parse(await blob.text());
      } catch (error) {
        this.emit("PuterJsonReadFallback", { path, error: String(error?.message || error) });
        return fallback;
      }
    }

    async saveMemory(memory) {
      const id = memory.id || (global.crypto?.randomUUID?.() || String(Date.now()));
      const record = { ...memory, id, updated_at: new Date().toISOString() };
      await this.saveJson(`NeoGen/memory/${id}.json`, record);
      return record;
    }

    async storeSetting(key, value) {
      await this.invoke("kv.set", [`neogen:${key}`, value]);
      return value;
    }

    async getSetting(key, fallback = null) {
      const value = await this.invoke("kv.get", [`neogen:${key}`]);
      return value ?? fallback;
    }

    async publishStaticSite(subdomain, directory) {
      return this.invoke(
        "hosting.create",
        [subdomain, directory],
        { reason: `Publish ${directory} as ${subdomain}` }
      );
    }

    assertReady() {
      if (!this.ready || !global.puter) {
        throw new PuterBridgeError("NeoGenPuterBridge.initialize() must be called first");
      }
    }

    capabilities() {
      return Object.freeze([...ALLOWED]);
    }
  }

  global.NeoGenPuterBridge = NeoGenPuterBridge;
  global.PuterBridgeError = PuterBridgeError;
})(globalThis);
