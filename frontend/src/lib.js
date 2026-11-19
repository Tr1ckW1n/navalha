// Utilitários de API, datas no fuso da barbearia, dinheiro e telefone.

export class ApiError extends Error {
  constructor(status, code, detail) {
    super(detail || code || `erro ${status}`);
    this.status = status;
    this.code = code;
  }
}

export async function api(path, { method = "GET", body, adminKey } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (adminKey) headers["X-Admin-Key"] = adminKey;
  const res = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 204) return null;
  let data = null;
  try { data = await res.json(); } catch { /* resposta sem corpo */ }
  if (!res.ok) {
    let detail = data?.detail;
    if (Array.isArray(detail)) detail = detail.map((d) => d.msg?.replace(/^Value error, /, "")).join("; ");
    throw new ApiError(res.status, data?.error, detail);
  }
  return data;
}

export const errorText = (e) =>
  e?.status === 429 ? "Muitas tentativas seguidas. Espere alguns minutos e tente de novo."
  : e?.status === 409 ? "Esse horário acabou de ser ocupado. Escolha outro."
  : e?.message || "Algo deu errado. Tente de novo.";

// ---------- datas (sempre no fuso da barbearia) ----------
export const WD = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
export const WD_LONG = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"];
export const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export const todayIn = (tz) => new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date());
export const addDays = (k, n) => {
  const [y, m, d] = k.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
};
export const weekday = (k) => {
  const [y, m, d] = k.split("-").map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7; // 0 = segunda
};
export const fmtDay = (k) => {
  const [, m, d] = k.split("-").map(Number);
  return `${WD_LONG[weekday(k)]}, ${d} de ${MES[m - 1]}`;
};
export const shortDay = (k) => {
  const [, m, d] = k.split("-").map(Number);
  return `${WD[weekday(k)]} ${d}/${String(m).padStart(2, "0")}`;
};
export const timeIn = (iso, tz) =>
  new Intl.DateTimeFormat("pt-BR", { timeZone: tz, hour: "2-digit", minute: "2-digit" }).format(new Date(iso));
export const dayIn = (iso, tz) => new Intl.DateTimeFormat("en-CA", { timeZone: tz }).format(new Date(iso));

// ---------- dinheiro e telefone ----------
export const brl = (cents) => (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
export const fmtPhone = (e) => {
  if (!/^\+55\d{10,11}$/.test(e || "")) return e || "";
  const d = e.slice(3);
  return `(${d.slice(0, 2)}) ${d.length === 11 ? d.slice(2, 7) + "-" + d.slice(7) : d.slice(2, 6) + "-" + d.slice(6)}`;
};
export const waUrl = (phone, text) => `https://wa.me/${String(phone).replace(/\D/g, "")}${text ? "?text=" + encodeURIComponent(text) : ""}`;
export const mapsUrl = (shop) =>
  `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${shop.address.replace(" · ", ", ")}${shop.cep ? ", " + shop.cep : ""}`)}`;

// ---------- armazenamento local (só conveniência; pode falhar em aba anônima) ----------
export const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* ignore */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
};
