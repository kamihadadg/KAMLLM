"use client";

import { apiBase } from "@/lib/api";
import { TOKEN_KEY } from "@/lib/session";
import { useCallback, useEffect, useState } from "react";

type Proj = { public_id: string; title: string };

type LlHealth = {
  models_ready?: boolean;
  ready_for_chat?: boolean;
  ollama?: { ok: boolean; error?: string | null };
  embed?: { ok: boolean; error?: string | null; dimension?: number | null };
  chat_model?: { ok: boolean; error?: string | null };
  index?: {
    chunk_count?: number;
    db_exists?: boolean;
    error?: string | null;
    path?: string;
  };
  models?: { chat?: string; embed?: string };
  note?: string | null;
};

function fmtDetail(data: unknown): string {
  if (!data || typeof data !== "object") return "Request failed";
  const d = (data as { detail?: unknown }).detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d))
    return d
      .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x)))
      .join(", ");
  try {
    return JSON.stringify(data);
  } catch {
    return "Request failed";
  }
}

export default function Home() {
  const [token, setToken] = useState<string | null>(null);

  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authErr, setAuthErr] = useState<string | null>(null);

  const [meEmail, setMeEmail] = useState<string | null>(null);
  const [projects, setProjects] = useState<Proj[]>([]);
  const [newTitle, setNewTitle] = useState("Untitled workspace");

  const [pid, setPid] = useState<string | null>(null);

  const [globalHealth, setGlobalHealth] = useState<LlHealth | null>(null);
  const [projHealth, setProjHealth] = useState<LlHealth | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);

  const [messages, setMessages] = useState<{ role: "user" | "assistant"; text: string }[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [ingestNote, setIngestNote] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [resetIndex, setResetIndex] = useState(false);

  useEffect(() => {
    setToken(window.localStorage.getItem(TOKEN_KEY));
  }, []);

  const refreshGlobalHealth = useCallback(async () => {
    setHealthErr(null);
    try {
      const r = await fetch(`${apiBase()}/api/health`, { cache: "no-store" });
      const data = await r.json();
      if (!r.ok) {
        setGlobalHealth(null);
        setHealthErr(fmtDetail(data));
        return;
      }
      setGlobalHealth(data as LlHealth);
    } catch (e) {
      setGlobalHealth(null);
      setHealthErr(e instanceof Error ? e.message : "API unreachable");
    }
  }, []);

  useEffect(() => {
    void refreshGlobalHealth();
  }, [refreshGlobalHealth]);

  const authHeaders = useCallback(() => {
    const h = new Headers();
    if (token) h.set("Authorization", `Bearer ${token}`);
    return h;
  }, [token]);

  const authJsonHeaders = useCallback(() => {
    const h = authHeaders();
    h.set("Content-Type", "application/json");
    return h;
  }, [authHeaders]);

  const loadWorkspace = useCallback(async () => {
    if (!token) {
      setMeEmail(null);
      setProjects([]);
      setPid(null);
      return;
    }
    try {
      const mr = await fetch(`${apiBase()}/api/auth/me`, { headers: authHeaders() });
      const mj = await mr.json();
      if (!mr.ok) {
        window.localStorage.removeItem(TOKEN_KEY);
        setToken(null);
        return;
      }
      setMeEmail(String(mj.email));

      const pr = await fetch(`${apiBase()}/api/projects`, { headers: authHeaders() });
      const pj = await pr.json();
      if (!pr.ok) throw new Error(fmtDetail(pj));
      const list = (pj.projects ?? []) as Proj[];
      setProjects(list);
      setPid((prev) => {
        if (!list.length) return null;
        if (!prev || !list.some((p) => p.public_id === prev)) return list[0].public_id;
        return prev;
      });
    } catch {
      setMeEmail(null);
    }
  }, [token, authHeaders]);

  useEffect(() => {
    void loadWorkspace();
  }, [token, loadWorkspace]);

  const refreshProjHealth = useCallback(async () => {
    if (!token || !pid) {
      setProjHealth(null);
      return;
    }
    try {
      const r = await fetch(`${apiBase()}/api/projects/${pid}/health`, { headers: authHeaders() });
      const j = await r.json();
      if (!r.ok) {
        setProjHealth(null);
        return;
      }
      setProjHealth(j as LlHealth);
    } catch {
      setProjHealth(null);
    }
  }, [token, pid, authHeaders]);

  useEffect(() => {
    void refreshProjHealth();
  }, [refreshProjHealth]);

  const logout = () => {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setMeEmail(null);
    setProjects([]);
    setPid(null);
    setMessages([]);
  };

  const doRegister = async () => {
    setAuthErr(null);
    try {
      const r = await fetch(`${apiBase()}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(fmtDetail(data));
      const t = String(data.access_token);
      window.localStorage.setItem(TOKEN_KEY, t);
      setToken(t);
      setPassword("");
    } catch (e) {
      setAuthErr(e instanceof Error ? e.message : "Something went wrong");
    }
  };

  const doLogin = async () => {
    setAuthErr(null);
    try {
      const r = await fetch(`${apiBase()}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(fmtDetail(data));
      const t = String(data.access_token);
      window.localStorage.setItem(TOKEN_KEY, t);
      setToken(t);
      setPassword("");
    } catch (e) {
      setAuthErr(e instanceof Error ? e.message : "Something went wrong");
    }
  };

  const createProject = async () => {
    if (!token || !newTitle.trim()) return;
    const r = await fetch(`${apiBase()}/api/projects`, {
      method: "POST",
      headers: authJsonHeaders(),
      body: JSON.stringify({ title: newTitle.trim() }),
    });
    const data = await r.json();
    if (!r.ok) {
      setAuthErr(fmtDetail(data));
      return;
    }
    await loadWorkspace();
    setPid(String(data.public_id));
    setMessages([]);
  };

  const deleteProject = async () => {
    if (!token || !pid) return;
    if (
      !window.confirm(
        "Delete this workspace? All indexed PDF chunks for this project will be removed. This cannot be undone.",
      )
    )
      return;
    const r = await fetch(`${apiBase()}/api/projects/${pid}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    if (!r.ok) {
      const data = await r.json();
      setAuthErr(fmtDetail(data));
      return;
    }
    setPid(null);
    setMessages([]);
    await loadWorkspace();
  };

  const sendMessage = async () => {
    const q = input.trim();
    if (!q || busy || !token || !pid) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const r = await fetch(`${apiBase()}/api/projects/${pid}/chat`, {
        method: "POST",
        headers: authJsonHeaders(),
        body: JSON.stringify({ message: q }),
      });
      const data = await r.json();
      if (!r.ok) {
        setMessages((m) => [...m, { role: "assistant", text: fmtDetail(data) }]);
        return;
      }
      setMessages((m) => [...m, { role: "assistant", text: String(data.reply ?? "") }]);
    } finally {
      setBusy(false);
      void refreshProjHealth();
    }
  };

  const onUpload = async (files: FileList | null) => {
    if (!files?.length || ingesting || !token || !pid) return;
    setIngesting(true);
    setIngestNote(null);
    try {
      const fd = new FormData();
      fd.append("reset", resetIndex ? "true" : "false");
      Array.from(files).forEach((f) => fd.append("files", f));
      const headers = new Headers();
      headers.set("Authorization", `Bearer ${token}`);
      const r = await fetch(`${apiBase()}/api/projects/${pid}/ingest`, {
        method: "POST",
        headers,
        body: fd,
      });
      const data = await r.json();
      if (!r.ok) {
        setIngestNote({ tone: "err", text: fmtDetail(data) });
        return;
      }
      setIngestNote({
        tone: "ok",
        text: `Indexed ${data.chunks_indexed ?? 0} chunks from ${data.pdf_count ?? 0} file(s).`,
      });
      void refreshProjHealth();
    } finally {
      setIngesting(false);
    }
  };

  const modelsOperational = Boolean(globalHealth?.models_ready);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 text-slate-900 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950 dark:text-slate-100">
      <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/80 backdrop-blur-md dark:border-slate-800/80 dark:bg-slate-950/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white shadow-sm shadow-indigo-600/25">
              K
            </div>
            <div>
              <h1 className="text-base font-semibold tracking-tight text-slate-900 dark:text-white">KAMLLM</h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">Your documents, one conversation</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                modelsOperational
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/50 dark:text-emerald-300"
                  : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${modelsOperational ? "bg-emerald-500" : "bg-amber-500"}`} />
              {modelsOperational ? "Models ready" : "Models offline"}
            </span>
            <code className="hidden rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-[10px] text-slate-600 sm:inline dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
              {apiBase()}
            </code>
            <button
              type="button"
              onClick={() => void refreshGlobalHealth()}
              className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            >
              Refresh status
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-8 px-6 py-10 lg:grid-cols-[minmax(0,320px)_1fr]">
        <aside className="space-y-5">
          {!token ? (
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
              <p className="mb-4 text-xs font-medium uppercase tracking-wider text-slate-400">Account</p>
              <div className="mb-4 flex rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800">
                <button
                  type="button"
                  className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
                    tab === "login"
                      ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                      : "text-slate-600 dark:text-slate-400"
                  }`}
                  onClick={() => setTab("login")}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  className={`flex-1 rounded-md py-2 text-sm font-medium transition ${
                    tab === "register"
                      ? "bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white"
                      : "text-slate-600 dark:text-slate-400"
                  }`}
                  onClick={() => setTab("register")}
                >
                  Create account
                </button>
              </div>
              <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">Work email</label>
              <input
                className="mb-3 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none ring-indigo-500/0 transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-950"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                placeholder="you@company.com"
              />
              <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">
                Password (min. 8 characters)
              </label>
              <input
                type="password"
                className="mb-4 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none ring-indigo-500/0 transition focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-600 dark:bg-slate-950"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={tab === "register" ? "new-password" : "current-password"}
                placeholder="••••••••"
              />
              {authErr && <p className="mb-3 text-xs text-red-600 dark:text-red-400">{authErr}</p>}
              <button
                type="button"
                onClick={() => void (tab === "login" ? doLogin() : doRegister())}
                className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white shadow-sm shadow-indigo-600/20 transition hover:bg-indigo-500"
              >
                {tab === "login" ? "Sign in" : "Create account"}
              </button>
            </section>
          ) : (
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
              <div className="mb-4 flex items-start justify-between gap-2">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-slate-400">Signed in</p>
                  <p className="mt-1 truncate text-sm font-medium text-slate-900 dark:text-white">{meEmail}</p>
                </div>
                <button
                  type="button"
                  onClick={logout}
                  className="shrink-0 text-xs font-medium text-slate-500 underline-offset-2 hover:text-red-600 hover:underline dark:text-slate-400 dark:hover:text-red-400"
                >
                  Sign out
                </button>
              </div>

              <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">Workspaces</h2>
              <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">Notebook-style projects with their own PDF index.</p>
              <select
                className="mb-3 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-950"
                value={pid ?? ""}
                onChange={(e) => {
                  setPid(e.target.value || null);
                  setMessages([]);
                }}
              >
                {projects.length === 0 && <option value="">No workspaces yet</option>}
                {projects.map((p) => (
                  <option key={p.public_id} value={p.public_id}>
                    {p.title}
                  </option>
                ))}
              </select>
              <div className="flex gap-2">
                <input
                  className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-950"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="Workspace name"
                />
                <button
                  type="button"
                  onClick={() => void createProject()}
                  className="shrink-0 rounded-lg bg-indigo-600 px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-500"
                >
                  New
                </button>
              </div>
              {projects.length > 0 && (
                <button
                  type="button"
                  onClick={() => void deleteProject()}
                  className="mt-3 text-xs font-medium text-red-600 underline-offset-2 hover:underline dark:text-red-400"
                >
                  Delete current workspace
                </button>
              )}
            </section>
          )}

          <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
            <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">Ollama stack</h2>
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">Local inference health check.</p>
            {healthErr && <p className="mb-2 text-xs text-red-600 dark:text-red-400">{healthErr}</p>}
            {globalHealth && (
              <ul className="space-y-2 text-xs text-slate-600 dark:text-slate-400">
                <li className="flex justify-between gap-2">
                  <span>Ollama</span>
                  <span className="font-medium text-slate-900 dark:text-slate-200">
                    {globalHealth.ollama?.ok ? "Connected" : "Error"}
                  </span>
                </li>
                <li className="flex justify-between gap-2">
                  <span>Embeddings</span>
                  <span className="font-medium text-slate-900 dark:text-slate-200">
                    {globalHealth.embed?.ok ? "OK" : "Fail"}
                  </span>
                </li>
                <li className="flex justify-between gap-2">
                  <span>Chat model</span>
                  <span className="font-medium text-slate-900 dark:text-slate-200">
                    {globalHealth.chat_model?.ok ? "OK" : "Fail"}
                  </span>
                </li>
                <li className="border-t border-slate-100 pt-2 dark:border-slate-800">
                  <span className="font-semibold text-emerald-700 dark:text-emerald-400">
                    Ready for chat: {globalHealth.models_ready ? "Yes" : "No"}
                  </span>
                </li>
              </ul>
            )}
          </section>

          {token && pid && (
            <section className="rounded-2xl border border-slate-200/90 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900/60">
              <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">This workspace</h2>
              <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">Upload PDFs to build the retrieval index.</p>
              {projHealth && (
                <p className="mb-3 text-xs text-slate-600 dark:text-slate-400">
                  Chunks indexed: <span className="font-medium text-slate-900 dark:text-slate-200">{projHealth.index?.chunk_count ?? 0}</span>
                  {" · "}
                  Chat ready:{" "}
                  <span className="font-medium text-slate-900 dark:text-slate-200">
                    {projHealth.ready_for_chat ? "Yes" : "No"}
                  </span>
                </p>
              )}
              <label className="mb-3 flex cursor-pointer items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                <input
                  type="checkbox"
                  checked={resetIndex}
                  onChange={(e) => setResetIndex(e.target.checked)}
                  className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                />
                Clear index before this upload
              </label>
              <input
                type="file"
                accept=".pdf,application/pdf"
                multiple
                disabled={ingesting}
                className="block w-full text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-2 file:font-medium file:text-white dark:file:bg-slate-700"
                onChange={(e) => void onUpload(e.target.files)}
              />
              {ingesting && <p className="mt-2 text-xs text-slate-500">Indexing…</p>}
              {ingestNote && (
                <p
                  className={`mt-2 text-xs ${ingestNote.tone === "ok" ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
                >
                  {ingestNote.text}
                </p>
              )}
            </section>
          )}
        </aside>

        <section className="flex min-h-[560px] flex-col overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-md dark:border-slate-800 dark:bg-slate-900/40">
          <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Assistant</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">Answers use only your uploaded PDFs for this workspace.</p>
          </div>
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto bg-slate-50/50 p-5 dark:bg-slate-950/30">
            {!token && (
              <div className="rounded-xl border border-dashed border-slate-200 bg-white/80 px-4 py-10 text-center dark:border-slate-700 dark:bg-slate-900/40">
                <p className="text-sm text-slate-600 dark:text-slate-400">Create an account or sign in to open a workspace and chat.</p>
              </div>
            )}
            {token && !pid && (
              <div className="rounded-xl border border-dashed border-slate-200 bg-white/80 px-4 py-10 text-center dark:border-slate-700 dark:bg-slate-900/40">
                <p className="text-sm text-slate-600 dark:text-slate-400">Create or select a workspace to get started.</p>
              </div>
            )}
            {messages.length === 0 && token && pid && (
              <div className="rounded-xl border border-dashed border-slate-200 bg-white/80 px-4 py-10 text-center dark:border-slate-700 dark:bg-slate-900/40">
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Upload PDFs in the sidebar, then ask questions about your documents.
                </p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`max-w-[min(100%,42rem)] rounded-xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                  msg.role === "user"
                    ? "ml-auto border border-indigo-100 bg-indigo-600 text-white dark:border-indigo-900/50 dark:bg-indigo-600"
                    : "mr-auto border border-slate-200 bg-white text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                }`}
              >
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider opacity-75">
                  {msg.role === "user" ? "You" : "Assistant"}
                </div>
                <div className="whitespace-pre-wrap">{msg.text}</div>
              </div>
            ))}
          </div>
          <div className="border-t border-slate-100 bg-white p-4 dark:border-slate-800 dark:bg-slate-900/80">
            <div className="flex gap-3">
              <textarea
                value={input}
                disabled={busy || !token || !pid}
                onChange={(e) => setInput(e.target.value)}
                placeholder={
                  !pid ? "Select a workspace first…" : "Ask something about your documents…"
                }
                rows={2}
                className="flex-1 resize-none rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm outline-none ring-indigo-500/0 transition focus:border-indigo-500 focus:bg-white focus:ring-2 focus:ring-indigo-500/15 disabled:opacity-45 dark:border-slate-600 dark:bg-slate-950 dark:focus:bg-slate-950"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendMessage();
                  }
                }}
              />
              <button
                type="button"
                disabled={busy || !input.trim() || !token || !pid}
                onClick={() => void sendMessage()}
                className="self-end rounded-xl bg-indigo-600 px-5 py-3 text-sm font-semibold text-white shadow-sm shadow-indigo-600/25 transition hover:bg-indigo-500 disabled:opacity-35"
              >
                Send
              </button>
            </div>
            <p className="mt-2 text-[10px] text-slate-400">Shift+Enter for a new line</p>
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-100 py-8 text-center text-[11px] text-slate-400 dark:border-slate-800 dark:text-slate-500">
        KAMLLM · Self-hosted RAG · API {apiBase()}
      </footer>
    </div>
  );
}
