/* NeoGen browser client.
 *
 * Puter handles browser identity, user-paid AI, and user-scoped cloud data.
 * The Genesis runtime handles local conversations, source, Git, terminal,
 * verification, and exact single-use approvals.
 */
(function bootNeoGen(global) {
  "use strict";

  const ROOT = "NeoGen";
  const $ = (id) => document.getElementById(id);
  const all = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = {
    token: localStorage.getItem("neogenToken") || "",
    localUser: null,
    puterUser: null,
    cloudOnly: false,
    conversations: [],
    conversation: null,
    messages: [],
    selectedFile: null,
    selectedPath: "",
    sha: null,
    mode: "chat",
    model: localStorage.getItem("neogenModel") || "",
    busy: false,
    recorder: null,
    recordingChunks: [],
    repository: null,
    editor: null,
    pendingApproval: null,
    activeAction: null,
    trainingLibrary: [],
    councilAgents: [],
    councilTranscript: [],
    councilRepository: null,
    councilEvidence: "",
    selectedPlan: localStorage.getItem("neogenSelectedPlan") || "level-1",
    subscription: null,
    abilities: new Set(),
  };

  const LEGAL_VERSION = "2026-08-05.1";
  const MANDATORY_LEGAL_DOCUMENTS = {
    terms: LEGAL_VERSION,
    privacy: LEGAL_VERSION,
    "acceptable-use": LEGAL_VERSION,
    "ai-transparency": LEGAL_VERSION,
  };

  const PLAN_LABELS = {
    "level-1": "Level 1 · Spark",
    "level-2": "Level 2 · Signal",
    "level-3": "Level 3 · Prism",
    "level-4": "Level 4 · Resonance",
    "level-5": "Level 5 · Studio",
    "level-6": "Level 6 · Operator",
    "level-7": "Level 7 · Builder",
    "level-8": "Level 8 · Scholar",
    "level-9": "Level 9 · Council",
    "level-10": "Level 10 · Genesis",
    admin: "Level 11 · Admin",
    owner: "Level 12 · Owner",
    business: "NeoGen Business",
    enterprise: "NeoGen Enterprise",
  };

  const ABILITY_CATALOG = [
    { id: "neo_chat", label: "Neo AI chat", detail: "Puter-powered reasoning and task planning.", plan: "level-1", connection: "puter" },
    { id: "conversation_memory", label: "Conversation memory", detail: "Persistent local and cloud-backed history.", plan: "level-1", connection: "puter" },
    { id: "file_attachments", label: "File attachments", detail: "Bring documents, images, audio, video, and code into chat.", plan: "level-2", connection: "puter" },
    { id: "neo_canvas", label: "Neo Canvas", detail: "Edit and save durable assistant outcomes.", plan: "level-2", connection: "puter" },
    { id: "image_creation", label: "Image creation", detail: "Generate and transform visual assets.", plan: "level-3", connection: "puter" },
    { id: "video_creation", label: "Video creation", detail: "Generate short cinematic clips from prompts.", plan: "level-3", connection: "puter" },
    { id: "vision_and_ocr", label: "Vision + OCR", detail: "Understand images and extract text.", plan: "level-3", connection: "puter" },
    { id: "voice_suite", label: "Voice suite", detail: "Speech generation, transcription, and voice transformation.", plan: "level-4", connection: "puter" },
    { id: "workspace_read", label: "Workspace reading", detail: "Browse and inspect an authorized project.", plan: "level-5", connection: "local" },
    { id: "monaco_editor", label: "Monaco editor", detail: "Open source in the integrated code editor.", plan: "level-5", connection: "local" },
    { id: "workspace_write", label: "Governed file writes", detail: "Apply exact, approval-bound source changes.", plan: "level-6", connection: "local" },
    { id: "governed_terminal", label: "Governed terminal", detail: "Run exact approved argument lists without a shell bridge.", plan: "level-6", connection: "local" },
    { id: "governed_git", label: "Governed Git", detail: "Branch, commit, push, merge, and recover with approval.", plan: "level-7", connection: "local" },
    { id: "verification_runs", label: "Verification runs", detail: "Test changes and preserve an auditable result trail.", plan: "level-7", connection: "local" },
    { id: "static_publish", label: "Static publishing", detail: "Publish a selected Puter directory after confirmation.", plan: "level-7", connection: "puter" },
    { id: "training_lab", label: "Training Lab", detail: "Research focused software domains with attribution.", plan: "level-8", connection: "puter" },
    { id: "knowledge_library", label: "Knowledge library", detail: "Save reusable, source-backed training notes.", plan: "level-8", connection: "puter" },
    { id: "agent_council", label: "Ten-agent council", detail: "Allocate work across ten named specialists.", plan: "level-9", connection: "puter" },
    { id: "multi_agent_analysis", label: "Collaborative synthesis", detail: "Share context, challenge findings, and synthesize decisions.", plan: "level-9", connection: "puter" },
    { id: "afterlife_forge", label: "Afterlife Forge", detail: "Create persistent regions and legacy consequences.", plan: "level-10", connection: "local" },
    { id: "full_individual_suite", label: "Full individual suite", detail: "Use every individual NeoGen ability.", plan: "level-10", connection: "hybrid" },
    { id: "team_workspaces", label: "Team workspaces", detail: "Coordinate shared organizational projects.", plan: "business", connection: "provider" },
    { id: "shared_admin", label: "Shared administration", detail: "Manage team roles and governed access.", plan: "business", connection: "provider" },
    { id: "audit_exports", label: "Audit exports", detail: "Export activity, approval, and verification trails.", plan: "business", connection: "provider" },
    { id: "sso_and_scim", label: "SSO + SCIM", detail: "Connect enterprise identity and user provisioning.", plan: "enterprise", connection: "provider" },
    { id: "private_deployment", label: "Private deployment", detail: "Operate NeoGen within private infrastructure.", plan: "enterprise", connection: "provider" },
    { id: "compliance_controls", label: "Compliance controls", detail: "Apply organization policy and retention boundaries.", plan: "enterprise", connection: "provider" },
    { id: "priority_governance", label: "Priority governance", detail: "Dedicated rollout and control-plane support.", plan: "enterprise", connection: "provider" },
    { id: "subscription_admin", label: "Subscription administration", detail: "Activate governed plans and review pending subscription requests.", plan: "admin", connection: "provider" },
    { id: "user_administration", label: "User administration", detail: "Manage user access and administrative responsibilities.", plan: "admin", connection: "provider" },
    { id: "policy_configuration", label: "Policy configuration", detail: "Configure platform-wide consent and execution policies.", plan: "admin", connection: "provider" },
    { id: "connector_governance", label: "Connector governance", detail: "Approve and control connected service capabilities.", plan: "admin", connection: "provider" },
    { id: "platform_ownership", label: "Platform ownership", detail: "Exercise the highest self-hosted NeoGen authority.", plan: "owner", connection: "provider" },
    { id: "billing_configuration", label: "Billing configuration", detail: "Connect and govern the external subscription provider.", plan: "owner", connection: "provider" },
    { id: "deployment_authority", label: "Deployment authority", detail: "Approve governed production releases and infrastructure changes.", plan: "owner", connection: "provider" },
    { id: "emergency_recovery", label: "Emergency recovery", detail: "Recover the platform from verified checkpoints and protected backups.", plan: "owner", connection: "provider" },
  ];

  const COUNCIL_ROLES = [
    { id: "atlas", name: "Atlas", role: "Software Architecture", focus: "System boundaries, dependencies, tradeoffs, and evolution" },
    { id: "oracle", name: "Oracle", role: "Research & Sources", focus: "Official documentation, standards, evidence, and version caveats" },
    { id: "pixel", name: "Pixel", role: "Product & UX", focus: "User flow, accessibility, clarity, and human control" },
    { id: "forge", name: "Forge", role: "Backend & APIs", focus: "Services, interfaces, data flow, and integration" },
    { id: "aegis", name: "Aegis", role: "Security & Permissions", focus: "Threats, consent, least privilege, and auditability" },
    { id: "proof", name: "Proof", role: "Testing & Verification", focus: "Acceptance criteria, test coverage, and failure modes" },
    { id: "relay", name: "Relay", role: "DevOps & CI", focus: "Delivery, reliability, observability, and recovery" },
    { id: "mnemosyne", name: "Mnemosyne", role: "Memory & Data", focus: "Persistence, retrieval, provenance, and data lifecycle" },
    { id: "genesis", name: "Genesis", role: "Afterlife & Emergence", focus: "Procedural growth, legacy effects, and extensibility" },
    { id: "synthesis", name: "Synthesis", role: "Council Lead", focus: "Consensus, disagreements, decisions, and prioritized next actions" },
  ];

  function requirePuter() {
    if (!global.puter) {
      throw new Error("Puter.js is unavailable. Serve NeoGen over HTTP and reload.");
    }
    return global.puter;
  }

  function normalizedText(value) {
    if (typeof value === "string") return value;
    const content = value?.message?.content ?? value?.content ?? value?.text;
    if (typeof content === "string") return content;
    if (Array.isArray(content)) {
      return content.map((item) => item?.text || item?.content || "").filter(Boolean).join("\n");
    }
    return JSON.stringify(value, null, 2);
  }

  class NeoGenPuterClient {
    constructor() { this.user = null; }

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
      if (puter.auth.isSignedIn()) await puter.auth.signOut();
      this.user = null;
    }

    async listModels() { return requirePuter().ai.listModels(); }
    async listProviders() { return requirePuter().ai.listModelProviders(); }

    async chat(messages, options = {}, media = null) {
      const puter = requirePuter();
      if (media) {
        const last = [...messages].reverse().find((item) => item.role === "user");
        const response = await puter.ai.chat(last?.content || "Analyze this file.", media, false, options);
        return normalizedText(response);
      }
      const transcript = [...messages];
      for (let round = 0; round < 4; round += 1) {
        const response = await puter.ai.chat(transcript, options);
        const calls = response?.message?.tool_calls || [];
        if (!calls.length) return normalizedText(response);
        transcript.push(response.message);
        for (const call of calls) {
          let args = {};
          try { args = JSON.parse(call.function?.arguments || "{}"); } catch {}
          let output;
          try { output = await executeNeoGenTool(call.function?.name || "unknown", args); }
          catch (error) { output = { error: error.message }; }
          transcript.push({ role: "tool", tool_call_id: call.id, content: JSON.stringify(output) });
        }
      }
      throw new Error("Neo reached the maximum tool-call depth for one message.");
    }

    async generateImage(prompt) {
      return requirePuter().ai.txt2img(prompt, {
        quality: "low",
        puter_output_path: `${ROOT}/generations/image-${Date.now()}.png`,
      });
    }

    async generateVideo(prompt) { return requirePuter().ai.txt2vid(prompt, { seconds: 4 }); }
    async extractText(file) { return normalizedText(await requirePuter().ai.img2txt(file)); }

    async transcribe(file) {
      const result = await requirePuter().ai.speech2txt(file);
      return result?.text || normalizedText(result);
    }

    async speak(text) { return requirePuter().ai.txt2speech(text); }
    async changeVoice(file) { return requirePuter().ai.speech2speech(file); }

    async saveJson(path, value) {
      return requirePuter().fs.write(
        `${ROOT}/${path}`,
        JSON.stringify(value, null, 2),
        { createMissingParents: true, overwrite: true },
      );
    }

    async saveText(path, value) {
      return requirePuter().fs.write(
        `${ROOT}/${path}`,
        String(value),
        { createMissingParents: true, overwrite: true },
      );
    }

    async loadJson(path, fallback = null) {
      try {
        const blob = await requirePuter().fs.read(`${ROOT}/${path}`);
        return JSON.parse(await blob.text());
      } catch { return fallback; }
    }

    async backupConversation(conversation, messages) {
      if (!this.user) return null;
      const safeMessages = messages.map((message) => ({
        role: message.role,
        content: message.content,
        created_at: message.created_at,
        mode: message.mode || "chat",
        attachment: message.attachment || null,
        media_type: message.media_type || null,
      }));
      return this.saveJson(`conversations/${conversation.id}.json`, {
        conversation,
        messages: safeMessages,
        updated_at: new Date().toISOString(),
      });
    }

    async loadConversationBackup(id) {
      return this.loadJson(`conversations/${id}.json`, { messages: [] });
    }

    async loadConversationIndex() {
      return (await requirePuter().kv.get("neogen:conversation-index")) || [];
    }

    async saveConversationIndex(items) {
      return requirePuter().kv.set("neogen:conversation-index", items.slice(0, 100));
    }

    async deleteConversation(id) {
      try { await requirePuter().fs.delete(`${ROOT}/conversations/${id}.json`); } catch {}
    }

    async saveSetting(key, value) { return requirePuter().kv.set(`neogen:${key}`, value); }
    async loadSetting(key, fallback = null) {
      const value = await requirePuter().kv.get(`neogen:${key}`);
      return value ?? fallback;
    }

    async listCloud(path = ROOT) {
      try { return await requirePuter().fs.readdir(path); } catch { return []; }
    }

    async publish(subdomain, directory = ROOT) {
      return requirePuter().hosting.create(subdomain, directory);
    }
  }

  const puterClient = new NeoGenPuterClient();
  global.neogenPuter = puterClient;

  function apiBase() {
    const input = $("settingsApiBase")?.value || $("apiBase")?.value || "/api/v1";
    const value = input.trim();
    return (value && value !== "/api/v1" ? value : `${location.origin}/api/v1`).replace(/\/$/, "");
  }

  async function request(path, options = {}) {
    if (!state.token) throw new Error("Connect the local Genesis runtime to use this capability.");
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    headers.Authorization = `Bearer ${state.token}`;
    let response;
    try {
      response = await fetch(apiBase() + path, { ...options, headers });
    } catch {
      throw new Error(`Cannot reach the local NeoGen runtime at ${apiBase()}.`);
    }
    let data = {};
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data.error || response.statusText || "Request failed");
    return data;
  }

  function neoGenToolDefinitions() {
    const tools = [
      {
        type: "function",
        function: {
          name: "list_puter_cloud_files",
          description: "List the user's NeoGen files in their private Puter cloud storage.",
          strict: true,
          parameters: { type: "object", properties: {}, additionalProperties: false },
        },
      },
      {
        type: "function",
        function: {
          name: "save_puter_note",
          description: "Save a text note in the user's private NeoGen Puter folder. This asks the user for confirmation.",
          strict: true,
          parameters: {
            type: "object",
            properties: {
              filename: { type: "string", description: "A short filename without directories." },
              content: { type: "string", description: "The complete note text." },
            },
            required: ["filename", "content"],
            additionalProperties: false,
          },
        },
      },
    ];
    if (!state.token) return tools;
    return tools.concat([
      {
        type: "function",
        function: {
          name: "list_workspace_files",
          description: "List all files and directories in the authorized local NeoGen workspace.",
          strict: true,
          parameters: { type: "object", properties: {}, additionalProperties: false },
        },
      },
      {
        type: "function",
        function: {
          name: "read_workspace_file",
          description: "Read a source file from the authorized local NeoGen workspace.",
          strict: true,
          parameters: {
            type: "object",
            properties: { path: { type: "string", description: "Workspace-relative file path." } },
            required: ["path"],
            additionalProperties: false,
          },
        },
      },
      {
        type: "function",
        function: {
          name: "inspect_repository",
          description: "Inspect the current Git branch, commit, dirty state, status, diff, and recent history without mutation.",
          strict: true,
          parameters: { type: "object", properties: {}, additionalProperties: false },
        },
      },
      {
        type: "function",
        function: {
          name: "get_system_health",
          description: "Inspect health and metrics for the connected Genesis runtime.",
          strict: true,
          parameters: { type: "object", properties: {}, additionalProperties: false },
        },
      },
      {
        type: "function",
        function: {
          name: "search_conversation_memory",
          description: "Search the user's previous NeoGen conversations for relevant decisions, attempts, constraints, and outcomes.",
          strict: true,
          parameters: {
            type: "object",
            properties: { query: { type: "string", description: "Specific text to find in prior conversations." } },
            required: ["query"],
            additionalProperties: false,
          },
        },
      },
      {
        type: "function",
        function: {
          name: "prepare_verified_improvement",
          description: "Apply a complete multi-file NeoGen source improvement after one bundled user approval, then automatically run every supplied verification command and roll back all changes if any check fails. Read every target file first and use its exact sha256.",
          strict: true,
          parameters: {
            type: "object",
            properties: {
              goal: { type: "string", description: "Concrete improvement outcome and acceptance criteria." },
              changes: {
                type: "array", minItems: 1,
                items: {
                  type: "object",
                  properties: {
                    path: { type: "string" },
                    content: { type: "string", description: "Complete replacement content." },
                    expected_sha256: { type: "string", description: "SHA-256 returned by read_workspace_file, or missing for a new file." },
                  },
                  required: ["path", "content", "expected_sha256"],
                  additionalProperties: false,
                },
              },
              verification_commands: {
                type: "array", minItems: 1,
                items: { type: "array", items: { type: "string" }, minItems: 1 },
                description: "Argument-vector checks to run automatically after applying the change.",
              },
            },
            required: ["goal", "changes", "verification_commands"],
            additionalProperties: false,
          },
        },
      },
      {
        type: "function",
        function: {
          name: "write_workspace_file",
          description: "Write a complete local workspace file after the user approves the exact path and content once.",
          strict: true,
          parameters: {
            type: "object",
            properties: {
              path: { type: "string", description: "Workspace-relative file path." },
              content: { type: "string", description: "Complete replacement file content." },
            },
            required: ["path", "content"],
            additionalProperties: false,
          },
        },
      },
      {
        type: "function",
        function: {
          name: "run_terminal_command",
          description: "Run an argument-vector command in the local workspace after exact one-time user approval. Never uses a command shell.",
          strict: true,
          parameters: {
            type: "object",
            properties: {
              command: { type: "array", items: { type: "string" }, minItems: 1, description: "Executable followed by its arguments." },
            },
            required: ["command"],
            additionalProperties: false,
          },
        },
      },
      {
        type: "function",
        function: {
          name: "run_git_command",
          description: "Run a Git argument vector in the authorized repository after exact one-time user approval.",
          strict: true,
          parameters: {
            type: "object",
            properties: {
              arguments: { type: "array", items: { type: "string" }, minItems: 1, description: "Arguments after the git executable." },
            },
            required: ["arguments"],
            additionalProperties: false,
          },
        },
      },
    ]);
  }

  async function executeNeoGenTool(name, args) {
    if (name === "list_puter_cloud_files") {
      const items = await puterClient.listCloud(ROOT);
      return { items: items.map((item) => ({ name: item.name, path: item.path, directory: Boolean(item.is_dir) })) };
    }
    if (name === "save_puter_note") {
      const filename = String(args.filename || "note.txt").replace(/[^a-zA-Z0-9._-]/g, "-").replace(/^\.+/, "") || "note.txt";
      const path = `notes/${filename}`;
      const approved = await requestUserApproval({
        title: "Save Puter cloud note",
        summary: `${ROOT}/${path}`,
        scope: ["Write one private cloud file", "Use the displayed path", "No other cloud changes"],
      });
      if (!approved) {
        return { denied: true, path };
      }
      try {
        await puterClient.saveText(path, String(args.content || ""));
        completeAction(true, `Saved ${ROOT}/${path}`);
        return { saved: true, path: `${ROOT}/${path}` };
      } catch (error) {
        completeAction(false, error.message);
        throw error;
      }
    }
    if (!state.token) return { error: "The local Genesis runtime is not connected." };
    if (name === "list_workspace_files") {
      const data = await request("/workspace/list?recursive=true");
      return { items: (data.items || []).slice(0, 1000) };
    }
    if (name === "read_workspace_file") {
      const data = await request(`/workspace/read?path=${encodeURIComponent(String(args.path || ""))}`);
      return { ...data, content: String(data.content || "").slice(0, 160000) };
    }
    if (name === "inspect_repository") {
      const [snapshot, details] = await Promise.all([
        request("/guarded/repository"), request("/guarded/repository/status"),
      ]);
      return { snapshot, ...details };
    }
    if (name === "get_system_health") return request("/health");
    if (name === "search_conversation_memory") {
      return request(`/conversations/search?q=${encodeURIComponent(String(args.query || ""))}&limit=20`);
    }
    if (name === "prepare_verified_improvement") {
      const payload = {
        goal: String(args.goal || ""),
        changes: Array.isArray(args.changes) ? args.changes : [],
        verification_commands: Array.isArray(args.verification_commands) ? args.verification_commands : [],
      };
      const plan = await request("/guarded/improvements/prepare", {
        method: "POST", body: JSON.stringify(payload),
      });
      const commands = payload.verification_commands.map((command) => command.join(" "));
      const approved = await requestUserApproval({
        title: "Apply and verify NeoGen improvement",
        summary: plan.approval.summary,
        scope: [
          `${plan.code_proposal.files.length} exact source change(s)`,
          `${commands.length} automatic verification check(s): ${commands.join(" · ")}`,
          "Create a recovery checkpoint and roll back automatically on failure",
        ],
      });
      await decideApproval(plan.approval.id, approved);
      if (!approved) return { denied: true, diff: plan.code_proposal.diff };
      try {
        const result = await request("/guarded/improvements/execute", {
          method: "POST", body: JSON.stringify({ plan_id: plan.id }),
        });
        completeAction(result.state === "succeeded", result.state === "succeeded"
          ? `Improvement verified · checkpoint ${result.checkpoint_id}`
          : `Improvement ${result.state}: ${result.error || "verification failed"}`);
        return { ...result, diff: plan.code_proposal.diff, verification_commands: commands };
      } catch (error) {
        completeAction(false, error.message);
        throw error;
      }
    }
    if (name === "write_workspace_file") {
      const payload = { path: String(args.path || ""), content: String(args.content || "") };
      return executeApprovedTool(
        "/guarded/files/request-write", "/guarded/files/write", payload,
        "workspace file write",
      );
    }
    if (name === "run_terminal_command") {
      if (!Array.isArray(args.command) || !args.command.every((item) => typeof item === "string")) {
        return { error: "command must be a string array" };
      }
      return executeApprovedTool(
        "/guarded/terminal/request", "/guarded/terminal/execute", { command: args.command },
        "terminal command",
      );
    }
    if (name === "run_git_command") {
      if (!Array.isArray(args.arguments) || !args.arguments.every((item) => typeof item === "string")) {
        return { error: "arguments must be a string array" };
      }
      return executeApprovedTool(
        "/guarded/repository/request", "/guarded/repository/execute", { arguments: args.arguments },
        "Git operation",
      );
    }
    return { error: `Unknown NeoGen tool: ${name}` };
  }

  async function executeApprovedTool(requestPath, executePath, payload, label) {
    const approval = await request(requestPath, { method: "POST", body: JSON.stringify(payload) });
    const approved = await requestUserApproval({
      title: label,
      summary: approval.summary,
      scope: ["Run this exact action once", "Stay inside the authorized workspace", "Require a new approval for any change"],
    });
    if (!approved) {
      await decideApproval(approval.id, false);
      return { denied: true, summary: approval.summary };
    }
    try {
      await decideApproval(approval.id, true);
      const result = await request(executePath, {
        method: "POST",
        body: JSON.stringify({ ...payload, approval_id: approval.id }),
      });
      completeAction(true, `${label} completed and verified`);
      return result;
    } catch (error) {
      completeAction(false, error.message);
      throw error;
    }
  }

  function uid(prefix = "puter") {
    const value = global.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}:${value}`;
  }

  function titleFromPrompt(prompt) {
    const clean = String(prompt || "New conversation").replace(/\s+/g, " ").trim();
    return clean.length > 46 ? `${clean.slice(0, 46).trim()}…` : clean || "New conversation";
  }

  function toast(message, bad = false) {
    const item = document.createElement("div");
    item.className = `toast${bad ? " bad" : ""}`;
    item.textContent = message;
    $("toastRegion").appendChild(item);
    setTimeout(() => item.remove(), 4200);
  }

  function setStatus(message, bad = false) {
    const status = $("status");
    status.textContent = message;
    status.classList.toggle("bad", bad);
  }

  function showRail(view = "activity") {
    const activity = view === "activity";
    $("activityTab").classList.toggle("active", activity);
    $("canvasTab").classList.toggle("active", !activity);
    $("activityView").classList.toggle("hidden", !activity);
    $("canvasView").classList.toggle("hidden", activity);
    document.querySelector(".action-rail").classList.add("rail-open");
  }

  function requestUserApproval({ title, summary, scope = [] }) {
    if (state.pendingApproval) {
      return Promise.reject(new Error("Another action is already waiting for approval."));
    }
    const activeView = document.querySelector(".app-view.active");
    const returnView = activeView && activeView.id !== "chatView"
      ? { id: activeView.id, title: $("viewTitle").textContent }
      : null;
    if (returnView) switchView("chatView", "Approval required");
    showRail("activity");
    $("approvalEmpty").classList.add("hidden");
    $("approvalCard").className = "approval-card";
    $("approvalBadge").classList.remove("hidden");
    $("approvalState").textContent = "Approval requested";
    $("approvalTitle").textContent = title;
    $("approvalSummary").textContent = summary;
    $("approvalScope").replaceChildren(...scope.map((item) => {
      const row = document.createElement("span");
      row.textContent = item;
      return row;
    }));
    $("approvalButtons").classList.remove("hidden");
    $("actStep").className = "current";
    $("actStep").querySelector("b").textContent = "3";
    $("verifyStep").className = "";
    $("verifyStep").querySelector("b").textContent = "4";
    return new Promise((resolve) => {
      state.pendingApproval = { resolve, title, summary, returnView };
      requestAnimationFrame(() => $("approveAction").focus());
    });
  }

  function resolveUserApproval(approved) {
    const pending = state.pendingApproval;
    if (!pending) return;
    state.pendingApproval = null;
    state.activeAction = pending;
    $("approvalBadge").classList.add("hidden");
    $("approvalButtons").classList.add("hidden");
    $("approvalCard").classList.toggle("executing", approved);
    $("approvalCard").classList.toggle("denied", !approved);
    $("approvalState").textContent = approved ? "Approved · executing" : "Declined";
    if (approved) {
      $("actStep").className = "done";
      $("actStep").querySelector("b").textContent = "✓";
      $("verifyStep").className = "current";
    } else {
      addActivity("Action declined", pending.title, false);
      setTimeout(resetApprovalCard, 1500);
    }
    pending.resolve(approved);
    if (pending.returnView) {
      setTimeout(() => switchView(pending.returnView.id, pending.returnView.title), 0);
    }
  }

  function completeAction(success, detail) {
    if (!state.activeAction) return;
    $("approvalCard").classList.toggle("denied", !success);
    $("approvalState").textContent = success ? "Completed · verified" : "Action failed";
    $("verifyStep").className = success ? "done" : "current";
    $("verifyStep").querySelector("b").textContent = success ? "✓" : "!";
    addActivity(success ? "Completed" : "Failed", detail, success);
    setTimeout(resetApprovalCard, 1900);
  }

  function resetApprovalCard() {
    state.activeAction = null;
    $("approvalCard").className = "approval-card hidden";
    $("approvalEmpty").classList.remove("hidden");
    if (matchMedia("(max-width: 1100px)").matches) {
      document.querySelector(".action-rail").classList.remove("rail-open");
    }
  }

  function addActivity(title, detail, success = true) {
    const row = document.createElement("div");
    row.className = "activity-item";
    const icon = document.createElement("span");
    icon.className = "activity-icon";
    icon.textContent = success ? "✓" : "!";
    const copy = document.createElement("div");
    const heading = document.createElement("strong");
    heading.textContent = title;
    const note = document.createElement("small");
    note.textContent = detail;
    copy.append(heading, note);
    row.append(icon, copy);
    $("activityLog").prepend(row);
  }

  function openCanvas(content = "") {
    $("resultCanvas").value = content;
    showRail("canvas");
    $("resultCanvas").focus();
  }

  function closeSidebar() { $("appShell").classList.remove("sidebar-open"); }

  function switchView(id, title = null) {
    all(".app-view").forEach((view) => view.classList.toggle("active", view.id === id));
    all(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.view === id));
    $("viewTitle").textContent = title || all(`[data-view="${id}"]`)[0]?.dataset.title || "NeoGen";
    closeSidebar();
    if (id === "studioView") refreshWorkspace();
    if (id === "commandView") Promise.allSettled([loadDashboard(), loadHealth()]);
    if (id === "afterlifeView") Promise.allSettled([loadAvatar(), loadEconomy()]);
    if (id === "pluginsView") loadCapabilities();
    if (id === "trainingView") loadTrainingLibrary();
    if (id === "councilView") {
      if (!state.councilAgents.length) allocateCouncilSubjects(false);
      else renderCouncilAgents();
      if (state.token) loadCouncilRepositoryContext(false);
    }
  }

  function updateProfile() {
    const identity = state.localUser?.display_name || state.puterUser?.username || "NeoGen creator";
    const roles = new Set(state.localUser?.roles || []);
    const localRole = roles.has("owner") ? "Level 12 · Owner" : roles.has("admin") ? "Level 11 · Admin" : "Member";
    $("profileName").textContent = identity;
    $("profileAvatar").title = identity;
    $("profileMode").textContent = state.token ? "Puter + local Genesis" : "Puter cloud mode";
    $("settingsPuterIdentity").textContent = state.puterUser ? `Connected as @${state.puterUser.username}` : "Not connected";
    $("settingsPuterLogin").textContent = state.puterUser ? "Puter connected" : "Connect Puter";
    $("settingsLocalIdentity").textContent = state.localUser?.email || "Not connected";
    $("settingsLocalRole").textContent = state.localUser ? localRole : "Guest";
  }

  async function restorePuterIdentity() {
    try {
      state.puterUser = await puterClient.restoreSession();
      const text = state.puterUser ? `Puter connected as @${state.puterUser.username}` : "AI and cloud memory without a NeoGen-held API key.";
      $("puterIdentity").textContent = text;
      updateProfile();
      return state.puterUser;
    } catch (error) {
      $("puterIdentity").textContent = error.message;
      return null;
    }
  }

  async function connectPuter(enter = true) {
    try {
      if (enter && !legalConsentConfirmed()) throw new Error("Confirm the current legal notices and adult eligibility before entering NeoGen.");
      state.puterUser = await puterClient.signIn();
      localStorage.setItem("neogenLegalVersion", LEGAL_VERSION);
      $("puterIdentity").textContent = `Puter connected as @${state.puterUser.username}`;
      updateProfile();
      if (enter) await enterApp();
    } catch (error) {
      $("authError").textContent = error.message;
      toast(error.message, true);
    }
  }

  async function localLogin(register = false) {
    $("authError").textContent = "";
    try {
      if (!legalConsentConfirmed()) throw new Error("Confirm the current legal notices and adult eligibility before entering NeoGen.");
      if (register) {
        await requestUnauthenticated("/auth/register", {
          email: $("email").value,
          password: $("password").value,
          display_name: $("displayName").value || "NeoGen creator",
        });
      }
      const session = await requestUnauthenticated("/auth/login", {
        email: $("email").value,
        password: $("password").value,
      });
      state.token = session.token;
      localStorage.setItem("neogenToken", state.token);
      state.localUser = await request("/auth/me");
      await recordLegalAcceptance();
      let planRequest = null;
      if (state.selectedPlan !== "level-1") {
        planRequest = await request("/subscriptions/request", {
          method: "POST",
          body: JSON.stringify({ plan_id: state.selectedPlan }),
        });
      }
      await enterApp();
      if (planRequest?.checkout_required) {
        toast(`${PLAN_LABELS[state.selectedPlan]} request saved. Billing activation is still required.`);
      }
    } catch (error) { $("authError").textContent = error.message; }
  }

  function legalConsentConfirmed() {
    return Boolean($("legalAcceptance")?.checked) || localStorage.getItem("neogenLegalVersion") === LEGAL_VERSION;
  }

  async function recordLegalAcceptance() {
    if (!state.token) {
      localStorage.setItem("neogenLegalVersion", LEGAL_VERSION);
      return;
    }
    await request("/legal/acceptance", {
      method: "POST",
      body: JSON.stringify({
        documents: MANDATORY_LEGAL_DOCUMENTS,
        age_confirmed: true,
        locale: navigator.language || "",
        source: "neogen-web",
      }),
    });
    localStorage.setItem("neogenLegalVersion", LEGAL_VERSION);
    if ($("settingsLegalSummary")) $("settingsLegalSummary").textContent = `Accepted version ${LEGAL_VERSION} · manage privacy and regional rights in the Legal Centre.`;
  }

  async function requestUnauthenticated(path, payload) {
    let response;
    try {
      response = await fetch(apiBase() + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } catch { throw new Error(`Cannot reach the local NeoGen runtime at ${apiBase()}.`); }
    let data = {};
    try { data = await response.json(); } catch {}
    if (!response.ok) throw new Error(data.error || response.statusText || "Authentication failed");
    return data;
  }

  async function enterApp() {
    state.cloudOnly = !state.token;
    $("auth").classList.add("hidden");
    $("appShell").classList.remove("hidden");
    updateProfile();
    setStatus(state.token ? "local + cloud" : "cloud mode");
    await Promise.allSettled([loadConversations(), loadModels(), loadDashboard(), loadSubscription()]);
  }

  function updatePlanSelection() {
    const label = PLAN_LABELS[state.selectedPlan] || PLAN_LABELS["level-1"];
    if ($("selectedPlanName")) $("selectedPlanName").textContent = label;
    all("[data-plan-card]").forEach((card) => card.classList.toggle("selected", card.dataset.planCard === state.selectedPlan));
  }

  async function selectPlan(planId) {
    if (!PLAN_LABELS[planId]) return;
    state.selectedPlan = planId;
    localStorage.setItem("neogenSelectedPlan", planId);
    updatePlanSelection();

    if (state.token && $("auth").classList.contains("plan-browse-mode")) {
      try {
        const result = await request("/subscriptions/request", {
          method: "POST",
          body: JSON.stringify({ plan_id: planId }),
        });
        await loadSubscription();
        toast(result.checkout_required
          ? `${PLAN_LABELS[planId]} request saved. Billing activation is still required.`
          : `${PLAN_LABELS[planId]} is active.`);
      } catch (error) { toast(error.message, true); }
      return;
    }
    $("access").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadSubscription() {
    try {
      state.subscription = state.token
        ? await request("/subscriptions/current")
        : {
            subscription: { plan_id: "level-1", state: "active" },
            plan: {
              id: "level-1",
              name: "Spark",
              level: 1,
              summary: "Neo chat and persistent conversation memory.",
              abilities: ABILITY_CATALOG.filter((ability) => ability.plan === "level-1").map((ability) => ability.id),
            },
          };
      const plan = state.subscription.plan;
      const level = plan.level ? `Level ${plan.level} · ` : "";
      $("settingsPlanSummary").textContent = `${level}${plan.name} — ${plan.summary}`;
      state.abilities = new Set(plan.abilities || []);
      renderSubscriptionSettings();
      applyEntitlements();
    } catch (error) {
      $("settingsPlanSummary").textContent = error.message;
      state.abilities = new Set();
      renderSubscriptionSettings();
      applyEntitlements();
    }
  }

  function planIncludesAbility(planId, requiredPlan) {
    if (planId === "owner") return true;
    if (planId === "admin") {
      return requiredPlan === "admin" || requiredPlan === "business" || requiredPlan.startsWith("level-");
    }
    if (planId === "enterprise") {
      return ["business", "enterprise"].includes(requiredPlan) || requiredPlan.startsWith("level-");
    }
    if (planId === "business") {
      return requiredPlan === "business" || requiredPlan.startsWith("level-");
    }
    const planLevel = Number(planId.split("-")[1]);
    const requiredLevel = Number(requiredPlan.split("-")[1]);
    return Number.isFinite(requiredLevel) && requiredLevel <= planLevel;
  }

  function renderSubscriptionSettings() {
    const currentPlan = state.subscription?.plan?.id || "level-1";
    const planGrid = $("settingsPlanGrid");
    planGrid.replaceChildren();
    for (const [planId, label] of Object.entries(PLAN_LABELS)) {
      const abilities = ABILITY_CATALOG.filter((ability) => planIncludesAbility(planId, ability.plan));
      const card = document.createElement("article");
      card.className = `settings-plan${currentPlan === planId ? " current" : ""}`;
      const copy = document.createElement("div");
      const kicker = document.createElement("small");
      kicker.textContent = Number.isFinite(Number(planId.split("-")[1])) || ["admin", "owner"].includes(planId)
        ? `${abilities.length} cumulative abilities`
        : "Organization plan";
      const title = document.createElement("strong");
      title.textContent = label;
      copy.append(kicker, title);
      const button = document.createElement("button");
      button.className = "level-select";
      const privileged = ["admin", "owner"].includes(planId);
      button.textContent = currentPlan === planId ? "Current" : privileged ? "Role assigned" : "Request";
      button.disabled = currentPlan === planId || privileged;
      button.onclick = () => requestPlanFromSettings(planId);
      card.append(copy, button);
      planGrid.append(card);
    }

    const abilityGrid = $("settingsAbilityGrid");
    abilityGrid.replaceChildren();
    for (const ability of ABILITY_CATALOG) {
      const entitled = state.abilities.has(ability.id);
      let status = `Requires ${PLAN_LABELS[ability.plan]}`;
      let availability = "locked";
      if (entitled) {
        if (ability.connection === "puter" && !state.puterUser) {
          status = "Connect Puter";
          availability = "needs-connection";
        } else if (["local", "hybrid"].includes(ability.connection) && !state.token) {
          status = "Connect local runtime";
          availability = "needs-connection";
        } else if (ability.connection === "provider") {
          status = "Provider configuration required";
          availability = "needs-connection";
        } else {
          status = "Unlocked";
          availability = "unlocked";
        }
      }
      const option = document.createElement("article");
      option.className = `settings-option ${availability}`;
      const stateMark = document.createElement("span");
      stateMark.className = "settings-option-state";
      stateMark.textContent = availability === "unlocked" ? "✓" : availability === "locked" ? "◇" : "○";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = ability.label;
      const detail = document.createElement("p");
      detail.textContent = ability.detail;
      const requirement = document.createElement("small");
      requirement.textContent = status;
      copy.append(title, detail, requirement);
      option.append(stateMark, copy);
      abilityGrid.append(option);
    }
    $("abilityCount").textContent = `${ABILITY_CATALOG.length} visible abilities`;
  }

  function applyEntitlements() {
    all("[data-ability]").forEach((control) => {
      const locked = !state.abilities.has(control.dataset.ability);
      control.classList.toggle("ability-locked", locked);
      control.setAttribute("aria-disabled", String(locked));
      const ability = ABILITY_CATALOG.find((item) => item.id === control.dataset.ability);
      if (locked && ability) control.title = `Requires ${PLAN_LABELS[ability.plan]}`;
      else control.removeAttribute("title");
    });
  }

  async function requestPlanFromSettings(planId) {
    state.selectedPlan = planId;
    localStorage.setItem("neogenSelectedPlan", planId);
    updatePlanSelection();
    if (!state.token) {
      toast("Connect the local Genesis runtime to record a subscription request.", true);
      return;
    }
    try {
      const result = await request("/subscriptions/request", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      });
      await loadSubscription();
      toast(result.checkout_required
        ? `${PLAN_LABELS[planId]} request saved. Billing activation is still required.`
        : `${PLAN_LABELS[planId]} is active.`);
    } catch (error) { toast(error.message, true); }
  }

  function browsePlans() {
    $("auth").classList.remove("hidden");
    $("auth").classList.add("plan-browse-mode");
    $("openAccess").textContent = "Return to workspace";
    $("levels").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openAccess() {
    if ($("auth").classList.contains("plan-browse-mode")) {
      $("auth").classList.add("hidden");
      $("auth").classList.remove("plan-browse-mode");
      $("openAccess").textContent = "Enter NeoGen";
      return;
    }
    $("access").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function signOut() {
    if (state.token) {
      try { await request("/auth/logout", { method: "POST" }); } catch {}
    }
    try { await puterClient.signOut(); } catch {}
    localStorage.removeItem("neogenToken");
    state.token = "";
    location.reload();
  }

  async function loadModels() {
    if (!state.puterUser) return;
    try {
      const models = await puterClient.listModels();
      const normalized = [...new Map((models || []).map((model) => {
        const id = String(model.id || model.model || model.name || "");
        const label = model.name || model.display_name || id;
        return [id, { id, label, provider: model.provider || "" }];
      }).filter(([id]) => id)).values()];
      normalized.sort((a, b) => a.label.localeCompare(b.label));
      for (const select of [$("modelSelect"), $("settingsModel")]) {
        const first = select.options[0];
        select.replaceChildren(first.cloneNode(true));
        for (const model of normalized) {
          const option = document.createElement("option");
          option.value = model.id;
          option.textContent = model.provider ? `${model.label} · ${model.provider}` : model.label;
          select.appendChild(option);
        }
        select.value = state.model;
      }
    } catch (error) { toast(`Model catalogue: ${error.message}`, true); }
  }

  async function loadConversations() {
    try {
      if (state.token) {
        const data = await request("/conversations");
        state.conversations = data.items || [];
      } else if (state.puterUser) {
        state.conversations = await puterClient.loadConversationIndex();
      } else {
        state.conversations = [];
      }
      renderHistory();
      state.conversation = null;
      state.messages = [];
      renderConversation();
    } catch (error) {
      state.conversations = [];
      renderHistory();
      toast(error.message, true);
    }
  }

  function renderHistory() {
    const root = $("historyList");
    root.innerHTML = "";
    if (!state.conversations.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.style.cssText = "padding:0 11px;font-size:12px";
      empty.textContent = "No conversations yet.";
      root.appendChild(empty);
      return;
    }
    for (const conversation of state.conversations) {
      const item = document.createElement("div");
      item.className = `history-item${state.conversation?.id === conversation.id ? " active" : ""}`;
      item.tabIndex = 0;
      item.setAttribute("role", "button");
      const title = document.createElement("span");
      title.className = "history-title";
      title.textContent = conversation.title || "New conversation";
      const remove = document.createElement("button");
      remove.className = "history-delete";
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Delete ${title.textContent}`);
      remove.onclick = (event) => { event.stopPropagation(); deleteConversation(conversation); };
      item.append(title, remove);
      item.onclick = () => selectConversation(conversation);
      item.onkeydown = (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectConversation(conversation);
        }
      };
      root.appendChild(item);
    }
  }

  async function selectConversation(conversation) {
    state.conversation = conversation;
    state.messages = [];
    switchView("chatView", conversation.title || "Neo");
    renderHistory();
    renderConversation(true);
    try {
      if (state.token) {
        const data = await request(`/conversations/${encodeURIComponent(conversation.id)}/messages`);
        state.messages = data.items || [];
      } else {
        const backup = await puterClient.loadConversationBackup(conversation.id);
        state.messages = backup?.messages || [];
      }
      renderConversation();
    } catch (error) { toast(error.message, true); }
  }

  function startNewConversation() {
    state.conversation = null;
    state.messages = [];
    state.selectedFile = null;
    updateAttachment();
    switchView("chatView", "Neo");
    renderHistory();
    renderConversation();
    $("prompt").focus();
  }

  async function ensureConversation(prompt) {
    if (state.conversation) return state.conversation;
    const title = titleFromPrompt(prompt);
    if (state.token) {
      state.conversation = await request("/conversations", {
        method: "POST",
        body: JSON.stringify({ title }),
      });
    } else {
      state.conversation = {
        id: uid("puter"),
        title,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
    }
    state.conversations.unshift(state.conversation);
    await persistCloudIndex();
    renderHistory();
    $("viewTitle").textContent = title;
    return state.conversation;
  }

  async function deleteConversation(conversation) {
    const approved = await requestUserApproval({
      title: "Delete conversation",
      summary: conversation.title || "This conversation",
      scope: ["Delete this conversation only", "Remove its saved message history", "Leave other conversations unchanged"],
    });
    if (!approved) return;
    try {
      if (state.token) {
        await request(`/conversations/${encodeURIComponent(conversation.id)}`, { method: "DELETE" });
      } else {
        await puterClient.deleteConversation(conversation.id);
      }
      state.conversations = state.conversations.filter((item) => item.id !== conversation.id);
      if (state.conversation?.id === conversation.id) startNewConversation();
      await persistCloudIndex();
      renderHistory();
      completeAction(true, "Conversation deleted");
      toast("Conversation deleted");
    } catch (error) { completeAction(false, error.message); toast(error.message, true); }
  }

  async function persistCloudIndex() {
    if (!state.puterUser) return;
    try { await puterClient.saveConversationIndex(state.conversations); } catch {}
  }

  function renderConversation(loading = false) {
    $("emptyState").classList.toggle("hidden", loading || state.messages.length > 0);
    const root = $("messages");
    root.innerHTML = "";
    for (const message of state.messages) root.appendChild(messageElement(message));
    if (loading) root.appendChild(thinkingElement());
    requestAnimationFrame(() => { $("conversationScroll").scrollTop = $("conversationScroll").scrollHeight; });
  }

  function messageElement(message) {
    const article = document.createElement("article");
    article.className = `message ${message.role === "user" ? "user" : "assistant"}`;
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = message.role === "user" ? (state.localUser?.display_name || state.puterUser?.username || "You").slice(0, 1).toUpperCase() : "N";
    const body = document.createElement("div");
    body.className = "message-body";
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const name = document.createElement("strong");
    name.textContent = message.role === "user" ? "You" : "Neo";
    const mode = document.createElement("span");
    mode.textContent = message.mode && message.mode !== "chat" ? `· ${modeTitle(message.mode)}` : "· NeoGen intelligence";
    meta.append(name, mode);
    const content = document.createElement("div");
    content.className = "message-content";
    content.textContent = message.content || "";
    body.append(meta, content);

    if (message.attachment) {
      const attachment = document.createElement("div");
      attachment.className = "attachment-chip visible";
      attachment.textContent = `Attached · ${message.attachment}`;
      body.appendChild(attachment);
    }

    if (message.media_element || message.media_url) {
      const frame = document.createElement("div");
      frame.className = "message-media";
      if (message.media_element) {
        message.media_element.controls = message.media_element.tagName !== "IMG";
        frame.appendChild(message.media_element);
      } else {
        const tag = message.media_type === "video" ? "video" : message.media_type === "audio" ? "audio" : "img";
        const media = document.createElement(tag);
        media.src = message.media_url;
        if (tag !== "img") media.controls = true;
        frame.appendChild(media);
      }
      body.appendChild(frame);
    }

    const actions = document.createElement("div");
    actions.className = "message-actions";
    const copy = document.createElement("button");
    copy.className = "message-action";
    copy.textContent = "Copy";
    copy.onclick = async () => { await navigator.clipboard.writeText(message.content || ""); toast("Copied"); };
    actions.appendChild(copy);
    if (message.role !== "user" && message.content) {
      const speak = document.createElement("button");
      speak.className = "message-action";
      speak.textContent = "Listen";
      speak.onclick = () => speakText(message.content);
      actions.appendChild(speak);
      const canvas = document.createElement("button");
      canvas.className = "message-action";
      canvas.textContent = "Canvas";
      canvas.onclick = () => openCanvas(message.content);
      actions.appendChild(canvas);
    }
    body.appendChild(actions);
    article.append(avatar, body);
    return article;
  }

  function thinkingElement() {
    const article = document.createElement("article");
    article.className = "message assistant";
    article.innerHTML = '<div class="message-avatar">N</div><div class="message-body"><div class="message-meta"><strong>Neo</strong><span>· working</span></div><div class="typing"><i></i><i></i><i></i></div></div>';
    return article;
  }

  function appendMessage(role, content, extra = {}) {
    const message = {
      role,
      content,
      created_at: new Date().toISOString(),
      mode: extra.mode || state.mode,
      ...extra,
    };
    state.messages.push(message);
    renderConversation();
    return message;
  }

  function modeTitle(mode) {
    return ({ chat: "Reason + create", image: "Image generation", video: "Video generation", ocr: "OCR", transcribe: "Transcription", voice: "Voice conversion", speech: "Text to speech" })[mode] || mode;
  }

  async function sendCurrentMessage() {
    const prompt = $("prompt").value.trim();
    if (!prompt && !state.selectedFile) return;
    if (state.busy) return;
    if (!state.puterUser) {
      toast("Connect Puter to use Neo AI capabilities.", true);
      return;
    }
    if (["ocr", "transcribe", "voice"].includes(state.mode) && !state.selectedFile) {
      toast(`${modeTitle(state.mode)} requires an attached file.`, true);
      return;
    }

    state.busy = true;
    updateSendButton();
    const file = state.selectedFile;
    const userText = prompt || `${modeTitle(state.mode)}: ${file?.name || "attachment"}`;
    await ensureConversation(userText);
    appendMessage("user", userText, { attachment: file?.name || null, mode: state.mode });
    $("prompt").value = "";
    autoResizePrompt();
    state.selectedFile = null;
    updateAttachment();
    renderConversation(true);

    try {
      let envelope = null;
      if (state.token) {
        envelope = await request(`/conversations/${encodeURIComponent(state.conversation.id)}/chat`, {
          method: "POST",
          body: JSON.stringify({ prompt: userText, model: state.model || null }),
        });
      }
      const result = await executePuterMode(userText, file, envelope);
      if (state.token) {
        await request(`/conversations/${encodeURIComponent(state.conversation.id)}/responses`, {
          method: "POST",
          body: JSON.stringify({ content: result.content, provider: "puter", model: state.model || null }),
        });
      }
      appendMessage("assistant", result.content, { mode: state.mode, ...result.extra });
      state.conversation.updated_at = new Date().toISOString();
      state.conversations = [state.conversation, ...state.conversations.filter((item) => item.id !== state.conversation.id)];
      await Promise.allSettled([
        persistCloudIndex(),
        puterClient.backupConversation(state.conversation, state.messages),
      ]);
      renderHistory();
    } catch (error) {
      appendMessage("assistant", `I couldn't complete that request: ${error.message}`, { mode: state.mode });
    } finally {
      state.busy = false;
      updateSendButton();
      $("prompt").focus();
    }
  }

  async function executePuterMode(prompt, file, envelope) {
    if (state.mode === "image") {
      const element = await puterClient.generateImage(prompt);
      return { content: `Created an image for: ${prompt}`, extra: { media_element: element, media_type: "image" } };
    }
    if (state.mode === "video") {
      const element = await puterClient.generateVideo(prompt);
      return { content: `Created a video for: ${prompt}`, extra: { media_element: element, media_type: "video" } };
    }
    if (state.mode === "ocr") {
      const content = await puterClient.extractText(file);
      return { content: content || "No text was detected.", extra: {} };
    }
    if (state.mode === "transcribe") {
      const content = await puterClient.transcribe(file);
      return { content: content || "No speech was detected.", extra: {} };
    }
    if (state.mode === "voice") {
      const element = await puterClient.changeVoice(file);
      return { content: `Converted the voice in ${file.name}.`, extra: { media_element: element, media_type: "audio" } };
    }
    if (state.mode === "speech") {
      const element = await puterClient.speak(prompt);
      element.play?.().catch(() => {});
      return { content: "Generated speech from your message.", extra: { media_element: element, media_type: "audio" } };
    }
    const history = envelope?.execution?.payload?.arguments?.messages || state.messages
      .filter((message) => ["user", "assistant"].includes(message.role))
      .map((message) => ({ role: message.role, content: message.content }));
    const system = {
      role: "system",
      content: "You are Neo, the Puter-powered human–AI symbiosis intelligence at the center of NeoGen. Work toward the user's requested outcome, including multi-step research, writing, coding, form preparation, and connected workflows. Search conversation memory when prior decisions, constraints, attempts, or outcomes may matter. For coding and bug fixing, inspect the repository, list and read relevant source and tests, then prefer prepare_verified_improvement so the user approves the complete diff and verification suite once; it applies, tests, and rolls back automatically. Use separate mutation tools only when a verified improvement bundle is inappropriate. Read-only tools may run directly. Every mutation must remain visible. Never claim success unless its tool result confirms success. Preserve project continuity, verification, recovery, owner authority, and the endlessly expanding Afterlife design principle.",
    };
    const tools = neoGenToolDefinitions();
    if (state.model && /(^|\/)(gpt-|openai)/i.test(state.model)) tools.push({ type: "web_search" });
    const options = { ...(state.model ? { model: state.model } : {}), tools };
    const content = await puterClient.chat([system, ...history], options, file);
    return { content, extra: {} };
  }

  async function speakText(text) {
    try {
      if (!state.puterUser) await connectPuter(false);
      const audio = await puterClient.speak(text.slice(0, 3000));
      await audio.play();
    } catch (error) { toast(error.message, true); }
  }

  function setMode(mode) {
    state.mode = mode;
    all(".tool-option").forEach((option) => option.classList.toggle("active", option.dataset.mode === mode));
    $("modeLabel").textContent = mode === "chat" ? "Tools" : modeTitle(mode);
    $("modeButton").classList.toggle("active", mode !== "chat");
    $("toolPopover").classList.add("hidden");
    $("modeButton").setAttribute("aria-expanded", "false");
    const placeholders = {
      chat: "Tell Neo what outcome you want…",
      image: "Describe the image to create",
      video: "Describe the short video to create",
      ocr: "Attach an image or PDF to extract text",
      transcribe: "Attach audio to transcribe",
      voice: "Attach audio to transform its voice",
      speech: "Enter text to turn into speech",
    };
    $("prompt").placeholder = placeholders[mode];
  }

  function updateAttachment() {
    $("attachmentChip").classList.toggle("visible", Boolean(state.selectedFile));
    $("attachmentName").textContent = state.selectedFile?.name || "";
    updateSendButton();
  }

  function updateSendButton() {
    $("send").disabled = state.busy || (!$("prompt").value.trim() && !state.selectedFile);
  }

  function autoResizePrompt() {
    const prompt = $("prompt");
    prompt.style.height = "auto";
    prompt.style.height = `${Math.min(prompt.scrollHeight, 190)}px`;
    updateSendButton();
  }

  async function toggleVoiceInput() {
    if (state.recorder?.state === "recording") {
      state.recorder.stop();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      toast("Audio recording is not available in this browser.", true);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.recordingChunks = [];
      state.recorder = new MediaRecorder(stream);
      state.recorder.ondataavailable = (event) => { if (event.data.size) state.recordingChunks.push(event.data); };
      state.recorder.onstop = async () => {
        $("voiceInput").classList.remove("active");
        stream.getTracks().forEach((track) => track.stop());
        try {
          const blob = new Blob(state.recordingChunks, { type: state.recorder.mimeType || "audio/webm" });
          $("prompt").value = await puterClient.transcribe(blob);
          autoResizePrompt();
          toast("Voice transcribed");
        } catch (error) { toast(error.message, true); }
      };
      state.recorder.start();
      $("voiceInput").classList.add("active");
      toast("Recording… tap the microphone again to stop");
    } catch (error) { toast(error.message, true); }
  }

  async function loadFiles() {
    const data = await request("/workspace/list?recursive=true");
    const root = $("files");
    root.innerHTML = "";
    if (!data.items.length) {
      root.innerHTML = '<p class="muted" style="padding:10px">No files in this workspace.</p>';
      return;
    }
    for (const file of data.items) {
      const button = document.createElement("button");
      button.className = `file-entry${state.selectedPath === file.path ? " active" : ""}`;
      button.textContent = `${file.kind === "directory" ? "▸" : "·"} ${file.path}`;
      if (file.kind === "file") button.onclick = () => openFile(file.path);
      root.appendChild(button);
    }
  }

  async function openFile(path) {
    try {
      const data = await request(`/workspace/read?path=${encodeURIComponent(path)}`);
      state.selectedPath = data.path;
      state.sha = data.sha256;
      $("filePath").value = data.path;
      setEditorValue(data.content, data.path);
      await loadFiles();
    } catch (error) { toast(error.message, true); }
  }

  async function saveFile() {
    try {
      const payload = { path: $("filePath").value, content: editorValue() };
      const approval = await request("/guarded/files/request-write", { method: "POST", body: JSON.stringify(payload) });
      const approved = await requestUserApproval({
        title: "Save workspace file",
        summary: approval.summary,
        scope: ["Write the displayed file", "Use this exact content", "Consume this permission once"],
      });
      if (!approved) {
        await decideApproval(approval.id, false);
        toast("File write denied", true);
        return;
      }
      await decideApproval(approval.id, true);
      const result = await request("/guarded/files/write", {
        method: "POST",
        body: JSON.stringify({ ...payload, approval_id: approval.id }),
      });
      completeAction(true, `Saved ${result.path}`);
      toast(`Saved ${result.path}`);
      await Promise.all([loadFiles(), openFile(result.path)]);
    } catch (error) { completeAction(false, error.message); toast(error.message, true); }
  }

  async function decideApproval(approvalId, approved) {
    return request("/guarded/approvals/decide", {
      method: "POST",
      body: JSON.stringify({ approval_id: approvalId, approved }),
    });
  }

  function parseCommand(text) {
    return text.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((item) => item.replace(/^"|"$/g, "")) || [];
  }

  async function runTerminal(commandText = null) {
    const text = (commandText || $("terminalCommand").value).trim();
    if (!text) return;
    const args = parseCommand(text);
    const git = args[0] === "git";
    const operation = git ? args.slice(1) : args;
    const requestPath = git ? "/guarded/repository/request" : "/guarded/terminal/request";
    const executePath = git ? "/guarded/repository/execute" : "/guarded/terminal/execute";
      const field = git ? "arguments" : "command";
    $("terminalOutput").textContent += `\n$ ${text}`;
    try {
      const approval = await request(requestPath, { method: "POST", body: JSON.stringify({ [field]: operation }) });
      const approved = await requestUserApproval({
        title: git ? "Run Git operation" : "Run terminal command",
        summary: approval.summary,
        scope: ["Run this exact argument list", "Stay inside the authorized workspace", "Consume this permission once"],
      });
      if (!approved) {
        await decideApproval(approval.id, false);
        $("terminalOutput").textContent += "\nDENIED";
        return;
      }
      await decideApproval(approval.id, true);
      const result = await request(executePath, {
        method: "POST",
        body: JSON.stringify({ [field]: operation, approval_id: approval.id }),
      });
      completeAction(result.exit_code === 0, result.exit_code === 0 ? "Command completed" : `Command exited ${result.exit_code}`);
      $("terminalOutput").textContent += `\n${result.stdout || ""}${result.stderr ? `\n${result.stderr}` : ""}\n[exit ${result.exit_code}]`;
      if (git) await loadRepository();
    } catch (error) { completeAction(false, error.message); $("terminalOutput").textContent += `\nERROR: ${error.message}`; }
    $("terminalCommand").value = "";
    $("terminalOutput").scrollTop = $("terminalOutput").scrollHeight;
  }

  async function loadRepository() {
    try {
      const [snapshot, details] = await Promise.all([
        request("/guarded/repository"),
        request("/guarded/repository/status"),
      ]);
      state.repository = { snapshot, details };
      $("repositoryStatus").textContent = snapshot.available
        ? `${snapshot.branch || "detached"} · ${snapshot.dirty ? "changes present" : "clean"} · ${(snapshot.commit || "").slice(0, 8)}`
        : "The configured workspace is not a Git checkout.";
      $("repositoryLog").textContent = `${details.status || ""}\n\n${details.log || ""}`.trim() || "Repository is clean.";
    } catch (error) {
      $("repositoryStatus").textContent = error.message;
      $("repositoryLog").textContent = "Local repository inspection unavailable.";
    }
  }

  async function refreshWorkspace() {
    if (!state.token) {
      toast("Connect the local Genesis runtime to use the AI Workspace.", true);
      return;
    }
    await Promise.allSettled([loadFiles(), loadRepository()]);
  }

  async function loadDashboard() {
    if (!state.token) return;
    try {
      const [avatar, wallet, inventory, files] = await Promise.all([
        request("/avatar"), request("/wallet"), request("/inventory"), request("/workspace/list?recursive=true"),
      ]);
      $("dashAvatar").textContent = avatar.name || "Your evolving NeoGen identity core.";
      $("dashLevel").firstChild.textContent = avatar.level;
      $("dashBalance").firstChild.textContent = wallet.balance;
      $("dashItems").textContent = inventory.items.length;
      $("dashFiles").firstChild.textContent = files.items.filter((item) => item.kind === "file").length;
    } catch (error) { setStatus("runtime issue", true); }
  }

  async function loadHealth() {
    if (!state.token) return;
    try {
      const health = await request("/health");
      $("healthOutput").textContent = JSON.stringify(health, null, 2);
      const rows = [
        ["Genesis runtime", health.status],
        ["Conversations", `${health.conversations?.conversations || 0} persistent`],
        ["Tools", `${health.tools?.enabled || 0} enabled`],
        ["Verification", `${health.verification?.runs || 0} runs`],
        ["Approvals", `${health.permissions?.pending_approvals || 0} pending`],
      ];
      $("healthSummary").innerHTML = "";
      for (const [label, value] of rows) {
        const row = document.createElement("div");
        row.className = "status-row";
        const left = document.createElement("span");
        left.textContent = label;
        const right = document.createElement("span");
        right.className = "tag";
        right.textContent = value;
        row.append(left, right);
        $("healthSummary").appendChild(row);
      }
      setStatus("healthy");
    } catch (error) {
      $("healthOutput").textContent = error.message;
      setStatus("runtime issue", true);
    }
  }

  async function loadAvatar() {
    if (!state.token) return;
    try {
      const avatar = await request("/avatar");
      $("avatarName").value = avatar.name || "";
      $("avatarAppearance").value = JSON.stringify(avatar.appearance || {}, null, 2);
      $("avatarLevel").textContent = avatar.level;
    } catch (error) { toast(error.message, true); }
  }

  async function saveAvatar() {
    try {
      const appearance = JSON.parse($("avatarAppearance").value || "{}");
      await request("/avatar", {
        method: "POST",
        body: JSON.stringify({ name: $("avatarName").value, appearance }),
      });
      await Promise.all([loadAvatar(), loadDashboard()]);
      toast("Identity core updated");
    } catch (error) { toast(error.message, true); }
  }

  async function loadEconomy() {
    if (!state.token) return;
    try {
      const [wallet, inventory] = await Promise.all([request("/wallet"), request("/inventory")]);
      $("balance").textContent = wallet.balance;
      $("inventory").innerHTML = "";
      if (!inventory.items.length) $("inventory").innerHTML = '<span class="muted">No persistent items yet.</span>';
      for (const item of inventory.items) {
        const row = document.createElement("div");
        row.className = "cloud-item";
        row.textContent = `${item.name} · rarity ${item.rarity}`;
        $("inventory").appendChild(row);
      }
    } catch (error) { toast(error.message, true); }
  }

  async function loadCapabilities() {
    if (!state.puterUser) return;
    try {
      const providers = await puterClient.listProviders();
      $("refreshCapabilities").textContent = `${providers.length} AI providers available`;
    } catch (error) { toast(error.message, true); }
  }

  async function loadCloudFiles() {
    if (!state.puterUser) { toast("Connect Puter first.", true); return; }
    try {
      const items = await puterClient.listCloud(ROOT);
      const root = $("cloudFiles");
      root.innerHTML = "";
      if (!items.length) root.innerHTML = '<span class="muted">No NeoGen cloud files yet.</span>';
      for (const item of items) {
        const row = document.createElement("div");
        row.className = "cloud-item";
        const name = document.createElement("span");
        name.textContent = item.name || item.path;
        const kind = document.createElement("span");
        kind.className = "tag";
        kind.textContent = item.is_dir ? "folder" : "file";
        row.append(name, kind);
        root.appendChild(row);
      }
    } catch (error) { toast(error.message, true); }
  }

  function allocateCouncilSubjects(showNotice = true) {
    const subject = $("councilSubject").value.trim();
    if (!subject && showNotice) {
      toast("Give the council a question or outcome first.", true);
      return false;
    }
    state.councilAgents = COUNCIL_ROLES.map((agent) => ({
      ...agent,
      assignment: subject ? `${agent.focus} applied to “${subject}”` : agent.focus,
      status: subject ? "allocated" : "ready",
    }));
    renderCouncilAgents();
    if (subject && showNotice) {
      $("councilStatus").textContent = "Allocated";
      toast("Subject allocated across all 10 specialist roles");
    }
    return Boolean(subject);
  }

  function renderCouncilAgents() {
    const root = $("agentGrid");
    root.replaceChildren();
    const agents = state.councilAgents.length
      ? state.councilAgents
      : COUNCIL_ROLES.map((agent) => ({ ...agent, assignment: agent.focus, status: "ready" }));
    for (const agent of agents) {
      const card = document.createElement("article");
      card.className = `agent-card ${agent.status === "working" ? "active" : agent.status === "done" ? "done" : agent.status === "failed" ? "failed" : ""}`.trim();
      const avatar = document.createElement("span");
      avatar.className = "agent-avatar";
      avatar.textContent = agent.name.slice(0, 2).toUpperCase();
      const copy = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = `${agent.name} · ${agent.role}`;
      const assignment = document.createElement("small");
      assignment.textContent = agent.assignment || agent.focus;
      copy.append(name, assignment);
      const status = document.createElement("span");
      status.className = "agent-state";
      status.textContent = agent.status || "ready";
      card.append(avatar, copy, status);
      root.appendChild(card);
    }
  }

  function appendCouncilMessage(agent, content, round) {
    const root = $("councilChat");
    root.querySelector(".council-empty")?.remove();
    const message = document.createElement("article");
    message.className = `council-message${agent.id === "synthesis" ? " lead" : ""}`;
    const avatar = document.createElement("span");
    avatar.className = "agent-avatar";
    avatar.textContent = agent.name.slice(0, 2).toUpperCase();
    const body = document.createElement("div");
    const heading = document.createElement("div");
    heading.className = "council-message-head";
    const name = document.createElement("strong");
    name.textContent = agent.name;
    const role = document.createElement("span");
    role.textContent = `${agent.role} · round ${round}`;
    const text = document.createElement("p");
    text.textContent = content;
    heading.append(name, role);
    body.append(heading, text);
    message.append(avatar, body);
    root.appendChild(message);
    root.scrollTop = root.scrollHeight;
  }

  function sharedCouncilTranscript() {
    return state.councilTranscript
      .map((item) => `@${item.agent.name} (${item.agent.role}, round ${item.round}):\n${item.content}`)
      .join("\n\n")
      .slice(-18000);
  }

  function boundedCouncilText(value, limit) {
    const content = String(value || "").trim();
    if (content.length <= limit) return content;
    return `${content.slice(0, limit)}\n… ${content.length - limit} characters omitted`;
  }

  function formatCouncilRepositoryContext(repository = state.councilRepository) {
    if (!repository?.snapshot?.available) return "No Git repository context is available.";
    const { snapshot, details, files } = repository;
    const excludedParts = new Set([".git", ".genesis", ".pytest_cache", "__pycache__", "node_modules", ".venv", "venv"]);
    const sourceFiles = files.filter((item) => {
      if (item.kind !== "file") return false;
      const parts = String(item.path || "").split("/");
      if (parts.some((part) => excludedParts.has(part))) return false;
      return !/(^|\/)(\.env($|\.)|.*(?:secret|credential|token|private[-_.]?key).*)/i.test(item.path);
    });
    const inventory = sourceFiles.slice(0, 240).map((item) => item.path);
    return [
      `Branch: ${snapshot.branch || "detached"}`,
      `Commit: ${snapshot.commit || "unknown"}`,
      `Working tree: ${snapshot.dirty ? "changes present" : "clean"}`,
      `Remote names: ${(snapshot.remotes || []).join(", ") || "none"}`,
      `\nStatus:\n${boundedCouncilText(details.status, 4000) || "clean"}`,
      `\nRecent history:\n${boundedCouncilText(details.log, 5000) || "unavailable"}`,
      `\nBounded working-tree diff:\n${boundedCouncilText(details.diff, 12000) || "no unstaged diff"}`,
      `\nSource inventory (${inventory.length}/${sourceFiles.length} files):\n${inventory.join("\n") || "empty"}`,
    ].join("\n").slice(0, 26000);
  }

  async function loadCouncilRepositoryContext(showNotice = true) {
    if (!state.token) {
      state.councilRepository = null;
      $("councilRepositoryStatus").textContent = "Connect the local Genesis runtime to attach repository evidence.";
      $("councilRepositoryPreview").textContent = "No repository context loaded.";
      if (showNotice) toast("Connect the local Genesis runtime first.", true);
      return false;
    }
    $("councilRepositoryStatus").textContent = "Reading the authorized checkout…";
    try {
      const [snapshot, details, listing] = await Promise.all([
        request("/guarded/repository"),
        request("/guarded/repository/status"),
        request("/workspace/list?recursive=true"),
      ]);
      if (!snapshot.available) throw new Error("The authorized workspace is not a Git checkout.");
      state.councilRepository = { snapshot, details, files: listing.items || [] };
      const fileCount = state.councilRepository.files.filter((item) => item.kind === "file").length;
      $("councilRepositoryStatus").textContent = `${snapshot.branch || "detached"} · ${(snapshot.commit || "").slice(0, 8)} · ${snapshot.dirty ? "changes present" : "clean"} · ${fileCount} files`;
      $("councilRepositoryPreview").textContent = formatCouncilRepositoryContext();
      if (showNotice) toast("Live repository evidence attached to the council");
      return true;
    } catch (error) {
      state.councilRepository = null;
      $("councilRepositoryStatus").textContent = error.message;
      $("councilRepositoryPreview").textContent = "Repository context unavailable.";
      if (showNotice) toast(error.message, true);
      return false;
    }
  }

  async function runAgentCouncil(followup = false) {
    const subject = $("councilSubject").value.trim();
    const context = $("councilContext").value.trim();
    const followupText = $("councilFollowup").value.trim();
    if (!subject) { toast("Give the council a question or outcome first.", true); return; }
    if (followup && !followupText) { toast("Enter a follow-up for the council.", true); return; }
    if (!state.puterUser) await connectPuter(false);
    if (!state.puterUser) return;
    const includeRepository = $("includeCouncilRepository").checked;
    if (includeRepository) {
      const loaded = await loadCouncilRepositoryContext(false);
      if (!loaded) {
        toast("Repository evidence is enabled but unavailable. Reconnect the runtime or turn off the repository bridge.", true);
        return;
      }
    }
    const repositoryContext = includeRepository
      ? formatCouncilRepositoryContext()
      : "Repository context not attached for this round.";
    if (!state.councilAgents.length || state.councilAgents[0].assignment.indexOf(subject) < 0) {
      allocateCouncilSubjects(false);
    }
    const approved = await requestUserApproval({
      title: followup ? "Run council follow-up" : "Run 10-agent council",
      summary: subject,
      scope: [
        "Make exactly 10 Puter AI requests in this round",
        "Share only the displayed subject, context, and council transcript",
        ...(includeRepository ? ["Share the displayed bounded repository snapshot, diff, history, and file inventory"] : []),
        "Allow Oracle to search the public web for current sources",
        "Perform no file, terminal, Git, publishing, or account mutation",
      ],
    });
    if (!approved) { $("councilStatus").textContent = "Declined"; return; }
    state.councilEvidence = repositoryContext;
    if (!followup) {
      state.councilTranscript = [];
      $("councilChat").replaceChildren();
    }
    state.councilAgents = state.councilAgents.map((agent) => ({ ...agent, status: "allocated" }));
    $("runCouncil").disabled = true;
    $("askCouncil").disabled = true;
    $("saveCouncil").disabled = true;
    $("saveCouncilRepository").disabled = true;
    $("handoffCouncil").disabled = true;
    const round = (state.councilTranscript.reduce((highest, item) => Math.max(highest, item.round || 1), 0) || 0) + 1;
    let completed = 0;
    $("councilStatus").textContent = `Round ${round} · 0/10`;
    try {
      for (let index = 0; index < state.councilAgents.length; index += 1) {
        const agent = state.councilAgents[index];
        agent.status = "working";
        renderCouncilAgents();
        const previous = sharedCouncilTranscript() || "No earlier council statements in this discussion.";
        const leadInstruction = agent.id === "synthesis"
          ? "As the final council lead, synthesize consensus and disagreements, resolve what the evidence supports, and return a prioritized action plan with acceptance checks."
          : "Address or challenge earlier agents by name when useful. Add a distinct perspective; do not merely repeat the transcript.";
        const system = {
          role: "system",
          content: `You are ${agent.name}, the ${agent.role} specialist in NeoGen's ten-agent council. Your allocated focus is: ${agent.focus}. ${leadInstruction} Be concrete, distinguish evidence from assumptions, expose risks and unresolved questions, and stay under 260 words. Never claim you executed an action.`,
        };
        const user = {
          role: "user",
          content: `Council subject: ${subject}\nShared context: ${context || "No additional context supplied."}\n\nAuthorized repository evidence:\n${repositoryContext}\n${followup ? `\nFollow-up for every agent: ${followupText}\n` : ""}\nShared discussion so far:\n${previous}\n\nCross-analyse the repository evidence and earlier specialist findings. Contribute your distinct analysis now.`,
        };
        const options = {
          ...(state.model ? { model: state.model } : {}),
          ...(agent.id === "oracle" ? { tools: [{ type: "web_search" }] } : {}),
        };
        try {
          const content = await puterClient.chat([system, user], options);
          state.councilTranscript.push({ agent: { ...agent }, content, round, created_at: new Date().toISOString() });
          appendCouncilMessage(agent, content, round);
          agent.status = "done";
          completed += 1;
        } catch (error) {
          const content = `This specialist could not respond: ${error.message}`;
          state.councilTranscript.push({ agent: { ...agent }, content, round, created_at: new Date().toISOString(), failed: true });
          appendCouncilMessage(agent, content, round);
          agent.status = "failed";
        }
        $("councilStatus").textContent = `Round ${round} · ${index + 1}/10`;
        renderCouncilAgents();
      }
      const complete = completed === state.councilAgents.length;
      $("councilStatus").textContent = complete ? `Round ${round} complete` : `Round ${round} partial · ${completed}/10`;
      $("saveCouncil").disabled = !state.councilTranscript.length;
      $("saveCouncilRepository").disabled = !state.councilTranscript.length || !state.token;
      $("handoffCouncil").disabled = !state.councilTranscript.length;
      $("askCouncil").disabled = false;
      completeAction(complete, `${completed}/10 council specialists responded`);
      addActivity("Council analyzed subject", `${completed}/10 specialists · ${subject}`, complete);
    } finally {
      $("runCouncil").disabled = false;
      $("askCouncil").disabled = !state.councilTranscript.length;
    }
  }

  function councilTranscriptDocument() {
    const subject = $("councilSubject").value.trim() || "Council analysis";
    const repositoryContext = state.councilEvidence || "Repository context was not attached.";
    return [
      `# Neo Agent Council: ${subject}`,
      `\nCreated: ${new Date().toISOString()}`,
      `\nShared context:\n${$("councilContext").value.trim() || "None supplied."}`,
      `\n## Repository evidence\n\n${repositoryContext}`,
      ...state.councilTranscript.map((item) => `\n## ${item.agent.name} — ${item.agent.role} (round ${item.round})\n\n${item.content}`),
    ].join("\n");
  }

  async function saveCouncilTranscript() {
    if (!state.councilTranscript.length) { toast("Run the council before saving a transcript.", true); return; }
    if (!state.puterUser) await connectPuter(false);
    if (!state.puterUser) return;
    const subject = $("councilSubject").value.trim() || "Council analysis";
    const path = `councils/${trainingSlug(subject)}-${Date.now()}.md`;
    const approved = await requestUserApproval({
      title: "Save council transcript",
      summary: `${ROOT}/${path}`,
      scope: ["Save the displayed discussion", "Keep it in private Puter storage", "Do not publish or modify the local workspace"],
    });
    if (!approved) return;
    const body = councilTranscriptDocument();
    try {
      await puterClient.saveText(path, body);
      completeAction(true, `Saved ${ROOT}/${path}`);
      toast("Council transcript saved privately in Puter");
    } catch (error) { completeAction(false, error.message); toast(error.message, true); }
  }

  async function saveCouncilTranscriptToRepository() {
    if (!state.councilTranscript.length) { toast("Run the council before saving a transcript.", true); return; }
    if (!state.token) { toast("Connect the local Genesis runtime first.", true); return; }
    const subject = $("councilSubject").value.trim() || "Council analysis";
    const path = `docs/agent-council/${trainingSlug(subject)}-${Date.now()}.md`;
    const payload = { path, content: councilTranscriptDocument() };
    try {
      const approval = await request("/guarded/files/request-write", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const approved = await requestUserApproval({
        title: "Save council analysis to repository",
        summary: approval.summary,
        scope: ["Write this exact Markdown transcript once", "Stay inside the authorized checkout", "Do not commit, push, or modify another file"],
      });
      if (!approved) {
        await decideApproval(approval.id, false);
        return;
      }
      await decideApproval(approval.id, true);
      const result = await request("/guarded/files/write", {
        method: "POST",
        body: JSON.stringify({ ...payload, approval_id: approval.id }),
      });
      completeAction(true, `Saved ${result.path}`);
      addActivity("Council evidence saved", result.path, true);
      toast(`Saved ${result.path}; commit remains a separate approval`);
      await Promise.allSettled([loadCouncilRepositoryContext(false), loadRepository()]);
    } catch (error) { completeAction(false, error.message); toast(error.message, true); }
  }

  function handoffCouncilImprovement() {
    if (!state.councilTranscript.length) { toast("Run the council before creating an improvement.", true); return; }
    const subject = $("councilSubject").value.trim() || "NeoGen improvement";
    const synthesis = [...state.councilTranscript].reverse().find((item) => item.agent.id === "synthesis" && !item.failed)
      || [...state.councilTranscript].reverse().find((item) => !item.failed);
    const discussion = sharedCouncilTranscript();
    const repository = state.councilRepository?.snapshot;
    switchView("chatView", "Neo");
    $("prompt").value = `Turn this Agent Council cross-analysis into the smallest safe NeoGen improvement.\n\nSubject: ${subject}\nRepository baseline: ${repository ? `${repository.branch || "detached"} at ${repository.commit || "unknown"}${repository.dirty ? " with working-tree changes" : " (clean)"}` : "Re-inspect the authorized checkout before planning."}\n\nCouncil synthesis:\n${synthesis?.content || "No synthesis response was available."}\n\nShared council discussion:\n${discussion}\n\nImprovement protocol:\n1. Re-inspect the relevant repository files and tests; treat council claims as hypotheses until verified.\n2. Propose one coherent improvement with measurable acceptance checks.\n3. Show the exact diff before any mutation and request a fresh single-use approval.\n4. Create a recovery checkpoint, apply only the approved change, run the relevant tests, and roll back automatically if verification fails.\n5. Do not commit, push, merge, publish, or perform another consequential action without its own approval.`;
    autoResizePrompt();
    $("prompt").focus();
    addActivity("Council handed off to Neo", subject, true);
    toast("Council synthesis prepared as a governed improvement");
  }

  async function loadTrainingLibrary() {
    if (!state.puterUser) {
      renderTrainingLibrary();
      return;
    }
    try {
      state.trainingLibrary = await puterClient.loadSetting("training-library", []);
      if (!Array.isArray(state.trainingLibrary)) state.trainingLibrary = [];
      renderTrainingLibrary();
    } catch (error) { toast(`Training library: ${error.message}`, true); }
  }

  function renderTrainingLibrary() {
    const root = $("trainingLibrary");
    root.innerHTML = "";
    if (!state.trainingLibrary.length) {
      root.innerHTML = '<div class="training-empty">No curated training notes yet.</div>';
      return;
    }
    for (const item of state.trainingLibrary.slice(0, 30)) {
      const row = document.createElement("div");
      row.className = "training-note";
      const title = document.createElement("strong");
      title.textContent = item.topic || "Research note";
      const meta = document.createElement("span");
      meta.textContent = `${item.source_mode || "Primary sources"} · ${new Date(item.created_at).toLocaleDateString()}`;
      row.append(title, meta);
      row.onclick = () => {
        $("trainingTopic").value = item.topic || "";
        $("trainingGoal").value = item.goal || "";
        $("trainingLog").textContent = item.content || `Saved at ${item.path}`;
      };
      root.appendChild(row);
    }
  }

  function trainingSlug(value) {
    return String(value || "software-research")
      .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 54) || "software-research";
  }

  async function startTrainingResearch() {
    const topic = $("trainingTopic").value.trim();
    const goal = $("trainingGoal").value.trim();
    if (!topic) { toast("Choose a focused software or coding topic.", true); return; }
    if (!state.puterUser) await connectPuter(false);
    if (!state.puterUser) return;
    const officialOnly = $("officialSourcesOnly").checked;
    const compareWorkspace = $("compareWorkspace").checked;
    $("trainingStatus").textContent = "Researching";
    $("trainingLog").textContent = `Neo is researching ${topic}…`;
    $("startTraining").disabled = true;
    try {
      const system = {
        role: "system",
        content: "You are Neo's governed Training Lab. Research one focused software or coding topic using current web sources. Prefer official documentation, standards, and primary technical sources. Attribute every important claim with a URL. Do not copy full pages or collect bulk copyrighted text; create concise original notes, patterns, version caveats, risks, and practical examples. Distinguish facts from recommendations. This is retrieval and reusable knowledge curation, not hidden model-weight training.",
      };
      const requestText = `Topic: ${topic}\nGoal: ${goal || "Build reusable knowledge for future NeoGen improvements."}\nSource policy: ${officialOnly ? "Official documentation and primary sources first; use secondary sources only when necessary." : "Use reputable sources, prioritizing primary evidence."}\nWorkspace comparison: ${compareWorkspace ? "Explain what should be compared with the current NeoGen codebase before implementation." : "Do not assume access to the local workspace."}\n\nReturn: source-backed findings, reusable patterns, security and compatibility cautions, recommended experiments, and a small improvement curriculum.`;
      const options = { ...(state.model ? { model: state.model } : {}), tools: [{ type: "web_search" }] };
      const content = await puterClient.chat([system, { role: "user", content: requestText }], options);
      $("trainingLog").textContent = content;
      $("trainingStatus").textContent = "Ready to save";
      const path = `training/${trainingSlug(topic)}-${Date.now()}.md`;
      const approved = await requestUserApproval({
        title: "Save curated training note",
        summary: `${ROOT}/${path}`,
        scope: ["Save this source-backed summary", "Keep it in private Puter storage", "Do not save full scraped pages"],
      });
      if (!approved) { $("trainingStatus").textContent = "Not saved"; return; }
      await puterClient.saveText(path, content);
      const record = {
        topic,
        goal,
        path: `${ROOT}/${path}`,
        content: content.slice(0, 50000),
        source_mode: officialOnly ? "Primary sources" : "Reputable web",
        created_at: new Date().toISOString(),
      };
      state.trainingLibrary = [record, ...state.trainingLibrary].slice(0, 50);
      await puterClient.saveSetting("training-library", state.trainingLibrary);
      renderTrainingLibrary();
      completeAction(true, `Saved training note for ${topic}`);
      $("trainingStatus").textContent = "Saved";
      addActivity("Knowledge curated", topic, true);
    } catch (error) {
      completeAction(false, error.message);
      $("trainingStatus").textContent = "Research failed";
      $("trainingLog").textContent = `Research failed: ${error.message}`;
      toast(error.message, true);
    } finally { $("startTraining").disabled = false; }
  }

  async function forgeTrainingImprovement() {
    const topic = $("trainingTopic").value.trim() || state.trainingLibrary[0]?.topic;
    const goal = $("trainingGoal").value.trim() || state.trainingLibrary[0]?.goal;
    if (!topic) { toast("Research or select a training topic first.", true); return; }
    const target = $("improvementTarget").selectedOptions[0].textContent;
    const note = state.trainingLibrary.find((item) => item.topic === topic) || state.trainingLibrary[0];
    switchView("chatView", "Neo");
    $("prompt").value = `Use the Training Lab knowledge about “${topic}” to propose an improvement for: ${target}.\n\nDesired outcome: ${goal || "Improve NeoGen safely and measurably."}\n\n${note?.content ? `Curated research:\n${note.content.slice(0, 12000)}\n\n` : ""}First inspect relevant source and existing tests. Create the smallest coherent plan, explain expected benefit and risk, show the exact diff before applying it, require approval for every mutation, run relevant verification, and restore the checkpoint if verification fails.`;
    autoResizePrompt();
    $("prompt").focus();
    toast("Improvement proposal prepared in Neo chat");
  }

  async function publishPuter() {
    const subdomain = $("publishSubdomain").value.trim();
    if (!subdomain) { toast("Enter a Puter subdomain.", true); return; }
    try {
      const approved = await requestUserApproval({
        title: "Publish Puter site",
        summary: `${subdomain}.puter.site`,
        scope: ["Publish the NeoGen cloud directory", "Use this exact subdomain", "Do not change other sites"],
      });
      if (!approved) return;
      await puterClient.publish(subdomain);
      completeAction(true, `Published ${subdomain}.puter.site`);
      toast(`Publishing requested for ${subdomain}.puter.site`);
    } catch (error) { completeAction(false, error.message); toast(error.message, true); }
  }

  async function saveResultCanvas() {
    const content = $("resultCanvas").value.trim();
    if (!content) { toast("Open or write something in Neo Canvas first.", true); return; }
    try {
      if (!state.puterUser) await connectPuter(false);
      if (!state.puterUser) return;
      const approved = await requestUserApproval({
        title: "Save Neo Canvas",
        summary: `${ROOT}/canvas/latest.md`,
        scope: ["Write one private Puter file", "Use the current canvas text", "Overwrite only the latest canvas"],
      });
      if (!approved) return;
      await puterClient.saveText("canvas/latest.md", content);
      completeAction(true, "Canvas saved to Puter");
      toast("Canvas saved to Puter");
    } catch (error) { completeAction(false, error.message); toast(error.message, true); }
  }

  function askNeoAboutCanvas() {
    const content = $("resultCanvas").value.trim();
    switchView("chatView", "Neo");
    $("prompt").value = content
      ? `Refine this Neo Canvas into a stronger final result:\n\n${content}`
      : "Help me create a finished result in Neo Canvas.";
    autoResizePrompt();
    document.querySelector(".action-rail").classList.remove("rail-open");
    $("prompt").focus();
  }

  function selectModel(value) {
    state.model = value;
    localStorage.setItem("neogenModel", value);
    $("modelSelect").value = value;
    $("settingsModel").value = value;
    if (state.puterUser) puterClient.saveSetting("model", value).catch(() => {});
  }

  function editorValue() {
    return state.editor ? state.editor.getValue() : $("editor").value;
  }

  function languageForPath(path) {
    const extension = String(path || "").split(".").pop().toLowerCase();
    return ({
      py: "python", js: "javascript", mjs: "javascript", cjs: "javascript",
      ts: "typescript", tsx: "typescript", jsx: "javascript", json: "json",
      html: "html", css: "css", md: "markdown", yml: "yaml", yaml: "yaml",
      cs: "csharp", sh: "shell", sql: "sql", xml: "xml",
    })[extension] || "plaintext";
  }

  function setEditorValue(value, path = "") {
    if (state.editor) {
      state.editor.setValue(value || "");
      global.monaco.editor.setModelLanguage(state.editor.getModel(), languageForPath(path));
    } else {
      $("editor").value = value || "";
    }
  }

  function initializeMonaco() {
    if (!global.require?.config) return;
    global.require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.56.0/min/vs" } });
    global.require(["vs/editor/editor.main"], () => {
      const textarea = $("editor");
      const host = document.createElement("div");
      host.className = "code-editor";
      host.style.padding = "0";
      host.style.height = "100%";
      textarea.insertAdjacentElement("afterend", host);
      textarea.classList.add("hidden");
      state.editor = global.monaco.editor.create(host, {
        value: textarea.value,
        language: languageForPath($("filePath").value),
        theme: "vs-dark",
        automaticLayout: true,
        minimap: { enabled: false },
        fontSize: 13,
        lineHeight: 21,
        padding: { top: 14 },
        scrollBeyondLastLine: false,
        smoothScrolling: true,
        wordWrap: "on",
      });
    }, () => {});
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const control = event.target.closest?.("[data-ability].ability-locked");
      if (!control) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const ability = ABILITY_CATALOG.find((item) => item.id === control.dataset.ability);
      toast(`${ability?.label || "This ability"} requires ${PLAN_LABELS[ability?.plan] || "a higher level"}.`);
      switchView("settingsView", "Settings");
    }, true);
    $("openAccess").onclick = openAccess;
    all("[data-plan]").forEach((button) => button.addEventListener("click", () => selectPlan(button.dataset.plan)));
    $("puterLogin").onclick = () => connectPuter(true);
    $("settingsPuterLogin").onclick = () => connectPuter(false);
    $("managePlan").onclick = browsePlans;
    $("login").onclick = () => localLogin(false);
    $("register").onclick = () => localLogin(true);
    $("logout").onclick = signOut;
    $("openSidebar").onclick = () => $("appShell").classList.add("sidebar-open");
    $("closeSidebar").onclick = closeSidebar;
    $("sidebarScrim").onclick = closeSidebar;
    $("newChat").onclick = startNewConversation;
    $("activityTab").onclick = () => showRail("activity");
    $("canvasTab").onclick = () => showRail("canvas");
    $("approveAction").onclick = () => resolveUserApproval(true);
    $("denyAction").onclick = () => resolveUserApproval(false);
    $("saveCanvas").onclick = saveResultCanvas;
    $("askCanvas").onclick = askNeoAboutCanvas;
    all("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view, button.dataset.title)));
    all(".starter-card").forEach((button) => button.addEventListener("click", () => { $("prompt").value = button.dataset.prompt; autoResizePrompt(); $("prompt").focus(); }));
    $("send").onclick = sendCurrentMessage;
    $("prompt").addEventListener("input", autoResizePrompt);
    $("prompt").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendCurrentMessage(); }
    });
    $("modeButton").onclick = () => {
      const hidden = $("toolPopover").classList.toggle("hidden");
      $("modeButton").setAttribute("aria-expanded", String(!hidden));
    };
    all(".tool-option").forEach((button) => button.onclick = () => setMode(button.dataset.mode));
    $("attachButton").onclick = () => $("fileInput").click();
    $("fileInput").onchange = () => { state.selectedFile = $("fileInput").files[0] || null; updateAttachment(); };
    $("removeAttachment").onclick = () => { state.selectedFile = null; $("fileInput").value = ""; updateAttachment(); };
    $("voiceInput").onclick = toggleVoiceInput;
    $("modelSelect").onchange = () => selectModel($("modelSelect").value);
    $("settingsModel").onchange = () => selectModel($("settingsModel").value);
    $("settingsApiBase").onchange = () => {
      $("apiBase").value = $("settingsApiBase").value;
      localStorage.setItem("neogenApiBase", $("settingsApiBase").value);
      toast("Local API address saved for this device");
    };
    $("refreshFiles").onclick = loadFiles;
    $("refreshWorkspace").onclick = refreshWorkspace;
    $("newFile").onclick = () => { state.selectedPath = ""; state.sha = null; $("filePath").value = "new-file.txt"; setEditorValue("", "new-file.txt"); };
    $("saveFile").onclick = saveFile;
    $("runCommand").onclick = () => runTerminal();
    $("terminalCommand").addEventListener("keydown", (event) => { if (event.key === "Enter") runTerminal(); });
    $("refreshRepository").onclick = loadRepository;
    all(".repo-command").forEach((button) => button.onclick = async () => {
      const command = button.dataset.command;
      if (command === "test") {
        await runTerminal("python -m unittest discover -s tests -v");
      } else if (command.startsWith("diff") && state.repository) {
        $("repositoryLog").textContent = state.repository.details.diff || "No working-tree diff.";
      } else if (command.startsWith("log") && state.repository) {
        $("repositoryLog").textContent = state.repository.details.log || "No history available.";
      } else if (state.repository) {
        $("repositoryLog").textContent = state.repository.details.status || "Repository is clean.";
      } else {
        await loadRepository();
      }
    });
    $("refreshDashboard").onclick = () => Promise.allSettled([loadDashboard(), loadHealth()]);
    $("saveAvatar").onclick = saveAvatar;
    all("[data-world-action]").forEach((button) => button.onclick = () => toast(`${button.dataset.worldAction} queued for the next connected world simulation.`));
    all(".academy-start").forEach((button) => button.onclick = () => {
      switchView("chatView", "Neo");
      $("prompt").value = "Create a NeoGen Academy lesson from the module I am currently working on. Explain it, quiz me, then give me a safe practical exercise.";
      autoResizePrompt();
      $("prompt").focus();
    });
    $("refreshCapabilities").onclick = loadCapabilities;
    $("allocateCouncil").onclick = () => allocateCouncilSubjects(true);
    $("refreshCouncilRepository").onclick = () => loadCouncilRepositoryContext(true);
    $("runCouncil").onclick = () => runAgentCouncil(false);
    $("askCouncil").onclick = () => runAgentCouncil(true);
    $("saveCouncil").onclick = saveCouncilTranscript;
    $("saveCouncilRepository").onclick = saveCouncilTranscriptToRepository;
    $("handoffCouncil").onclick = handoffCouncilImprovement;
    $("startTraining").onclick = startTrainingResearch;
    $("refreshTraining").onclick = loadTrainingLibrary;
    $("forgeImprovement").onclick = forgeTrainingImprovement;
    $("loadCloudFiles").onclick = loadCloudFiles;
    $("publishPuter").onclick = publishPuter;
    document.addEventListener("click", (event) => {
      if (!$("toolPopover").contains(event.target) && !$("modeButton").contains(event.target)) {
        $("toolPopover").classList.add("hidden");
        $("modeButton").setAttribute("aria-expanded", "false");
      }
    });
  }

  async function initialize() {
    bindEvents();
    if ($("legalAcceptance") && localStorage.getItem("neogenLegalVersion") === LEGAL_VERSION) $("legalAcceptance").checked = true;
    updatePlanSelection();
    initializeMonaco();
    const savedApi = localStorage.getItem("neogenApiBase");
    if (savedApi) { $("apiBase").value = savedApi; $("settingsApiBase").value = savedApi; }
    $("modelSelect").value = state.model;
    $("settingsModel").value = state.model;
    await restorePuterIdentity();
    if ("serviceWorker" in navigator) {
      if (["127.0.0.1", "localhost"].includes(location.hostname)) {
        navigator.serviceWorker.getRegistrations().then((registrations) => registrations.forEach((registration) => registration.unregister()));
      } else {
        navigator.serviceWorker.register("./service-worker.js").catch(() => {});
      }
    }
    if (state.token) {
      try {
        state.localUser = await request("/auth/me");
        await enterApp();
        return;
      } catch {
        localStorage.removeItem("neogenToken");
        state.token = "";
      }
    }
    if (state.puterUser) await enterApp();
  }

  initialize();
})(globalThis);
