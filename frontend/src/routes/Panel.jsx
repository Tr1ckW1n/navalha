// Painel do dono (provisório até a Fase 3): agenda do dia por barbeiro, status, encaixe e lembrete.
// Acesso pela chave de administração; ela fica salva só neste aparelho.
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { addDays, api, brl, errorText, fmtDay, fmtPhone, shortDay, store, timeIn, todayIn, waUrl } from "../lib.js";

const STATUS_PT = { scheduled: "Agendado", completed: "Concluído", no_show: "Não veio", canceled: "Cancelado" };
const KEY_STORE = "navalha-admin-key";
const n = (k, one, many) => `${k} ${k === 1 ? one : many}`;

function useToast() {
  const [msg, setMsg] = useState("");
  useEffect(() => { if (!msg) return; const t = setTimeout(() => setMsg(""), 2600); return () => clearTimeout(t); }, [msg]);
  return [msg, setMsg];
}

export default function Panel() {
  const { slug } = useParams();
  const [shop, setShop] = useState(null);
  const [key, setKey] = useState(store.get(KEY_STORE) || "");
  const [authed, setAuthed] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [authErr, setAuthErr] = useState("");
  const [barbers, setBarbers] = useState([]);
  const [services, setServices] = useState([]);
  const [day, setDay] = useState(null);
  const [appts, setAppts] = useState(null);
  const [confirmCancel, setConfirmCancel] = useState(null);
  const [showFit, setShowFit] = useState(false);
  const [toast, setToast] = useToast();

  useEffect(() => {
    api(`/public/${slug}`).then((p) => { setShop(p.shop); setDay(todayIn(p.shop.timezone)); document.title = `Painel · ${p.shop.name}`; })
      .catch(() => setAuthErr("Barbearia não encontrada."));
  }, [slug]);

  const tryKey = useCallback(async (k) => {
    if (!shop || !k) return;
    try {
      const [b, s] = await Promise.all([
        api(`/admin/shops/${shop.id}/barbers`, { adminKey: k }),
        api(`/admin/shops/${shop.id}/services`, { adminKey: k }),
      ]);
      setBarbers(b.filter((x) => x.active)); setServices(s.filter((x) => x.active));
      setKey(k); store.set(KEY_STORE, k); setAuthed(true); setAuthErr("");
    } catch (e) {
      store.del(KEY_STORE); setAuthed(false);
      setAuthErr(e.status === 401 ? "Chave incorreta." : e.status === 503 ? "Painel desligado no servidor (ADMIN_API_KEY não configurada)." : errorText(e));
    }
  }, [shop]);

  useEffect(() => { if (shop && key && !authed) tryKey(key); }, [shop, key, authed, tryKey]);

  const load = useCallback(async () => {
    if (!authed || !day) return;
    try { setAppts(await api(`/admin/shops/${shop.id}/appointments?date=${day}`, { adminKey: key })); }
    catch (e) { setToast(errorText(e)); }
  }, [authed, day, shop, key, setToast]);

  useEffect(() => { setAppts(null); load(); }, [load]);
  useEffect(() => { const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);

  async function setStatus(a, status) {
    try {
      await api(`/admin/shops/${shop.id}/appointments/${a.id}`, { method: "PATCH", body: { status }, adminKey: key });
      setToast(`${a.clientName.split(" ")[0]}: ${STATUS_PT[status].toLowerCase()}`); setConfirmCancel(null); load();
    } catch (e) { setToast(errorText(e)); }
  }

  if (!shop) return <main className="wrap"><p className="muted">{authErr || "Carregando…"}</p></main>;

  if (!authed) return (
    <main className="wrap fade" style={{ maxWidth: 480 }}>
      <form className="card stack" onSubmit={(e) => { e.preventDefault(); tryKey(keyInput.trim()); }}>
        <div><span className="eyebrow">Painel</span><h2>{shop.name}</h2></div>
        <label className="f">Chave de acesso<input className="i" type="password" value={keyInput} onChange={(e) => setKeyInput(e.target.value)} autoComplete="current-password" /></label>
        {authErr && <p className="err" role="alert">{authErr}</p>}
        <button className="btn" type="submit" disabled={!keyInput.trim()}>Entrar</button>
        <p className="note">Acesso provisório. Na próxima versão cada barbeiro terá o próprio login.</p>
      </form>
    </main>
  );

  const tz = shop.timezone, today = todayIn(tz);
  const list = appts || [];
  const count = (s) => list.filter((a) => a.status === s).length;
  const sum = (s) => list.filter((a) => a.status === s).reduce((t, a) => t + a.price, 0);
  const remindable = (a) => a.status === "scheduled" && (day === today || day === addDays(today, 1)) && new Date(a.startsAt) > new Date();
  const reminder = (a) => `Olá, ${a.clientName.split(" ")[0]}! Passando pra lembrar do seu horário na ${shop.name}:\n\n✂️ ${a.serviceName} com ${a.barberName}\n📅 ${day === today ? "hoje" : "amanhã"}, às ${timeIn(a.startsAt, tz)}\n📍 ${shop.address}\n\nResponda *SIM* para confirmar.`;

  return (<>
    <header className="topbar"><div className="in">
      <img src={`/logos/${shop.slug}.webp`} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />
      <b style={{ fontFamily: "var(--f-display)", fontSize: 22, textTransform: "uppercase" }}>{shop.name}</b>
      <span className="muted" style={{ fontSize: 12 }}>painel</span>
      <div className="row" style={{ marginLeft: "auto" }}>
        <a className="btn ghost sm" href={`/${shop.slug}`} target="_blank" rel="noopener">Ver link público</a>
        <button className="btn ghost sm" onClick={() => { store.del(KEY_STORE); setAuthed(false); setKey(""); }}>Sair</button>
      </div>
    </div></header>

    <main className="wrap wide stack">
      <div className="row between">
        <div className="row">
          <button className="btn ghost sm" onClick={() => setDay(addDays(day, -1))} aria-label="Dia anterior">←</button>
          <button className="btn ghost sm" onClick={() => setDay(today)}>Hoje</button>
          <button className="btn ghost sm" onClick={() => setDay(addDays(day, 1))} aria-label="Próximo dia">→</button>
          <input className="i" type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} style={{ width: "auto", padding: "7px 10px", fontSize: 14 }} />
          <h3>{fmtDay(day)}</h3>
        </div>
        <button className="btn sm" onClick={() => setShowFit(!showFit)}>{showFit ? "Fechar encaixe" : "+ Encaixe"}</button>
      </div>

      <div className="chips">
        <span className="chip">{n(count("scheduled"), "agendado", "agendados")}</span>
        <span className="chip" style={{ color: "var(--ok)" }}>{n(count("completed"), "concluído", "concluídos")}</span>
        <span className="chip" style={{ color: "var(--warn)" }}>{n(count("no_show"), "não veio", "não vieram")}</span>
        <span className="chip" style={{ color: "var(--dim)" }}>{n(count("canceled"), "cancelado", "cancelados")}</span>
        <span className="chip mono">feito <b style={{ color: "var(--ok)" }}>{brl(sum("completed"))}</b> · previsto <b style={{ color: "var(--gold)" }}>{brl(sum("scheduled"))}</b></span>
      </div>

      {showFit && <FitIn shop={shop} barbers={barbers} services={services} day={day < today ? today : day} adminKey={key}
        onDone={(a) => { setShowFit(false); setToast(`${a.clientName.split(" ")[0]} encaixado às ${timeIn(a.startsAt, tz)}`); if (a && day >= today) load(); }} />}

      {appts === null ? <div className="skeleton" /> :
        <div className="cols">{barbers.map((b) => {
          const mine = list.filter((a) => a.barberId === b.id);
          return <section key={b.id} className="col">
            <h3><span className="avatar">{b.name[0]}</span>{b.name} <span className="muted" style={{ fontSize: 13, fontFamily: "var(--f-body)", textTransform: "none" }}>· {mine.filter((a) => a.status !== "canceled").length} no dia</span></h3>
            {mine.length === 0 && <p className="muted" style={{ margin: 0 }}>Sem agendamentos.</p>}
            {mine.map((a) => (
              <div key={a.id} className={`ap ${a.status}`}>
                <div className="row between"><span className="t">{timeIn(a.startsAt, tz)}–{timeIn(a.endsAt, tz)}</span><span className={`pill ${a.status}`}>{STATUS_PT[a.status]}</span></div>
                <div><b>{a.clientName}</b> <span className="muted mono" style={{ fontSize: 12 }}>{fmtPhone(a.clientPhone)}</span></div>
                <div className="muted" style={{ fontSize: 13 }}>{a.serviceName} · <span className="price">{brl(a.price)}</span>{a.source === "panel" ? " · encaixe" : ""}</div>
                {a.status === "scheduled" && <div className="row" style={{ gap: 6 }}>
                  <button className="mini ok" onClick={() => setStatus(a, "completed")}>✓ Concluído</button>
                  <button className="mini warn" onClick={() => setStatus(a, "no_show")}>Não veio</button>
                  {confirmCancel === a.id
                    ? <button className="mini off" onClick={() => setStatus(a, "canceled")}>Confirmar cancelamento</button>
                    : <button className="mini off" onClick={() => setConfirmCancel(a.id)}>Cancelar</button>}
                  {remindable(a) && <a className="mini wa" href={waUrl(a.clientPhone, reminder(a))} target="_blank" rel="noopener">Lembrar no WhatsApp</a>}
                </div>}
              </div>))}
          </section>;
        })}</div>}
      <p className="note">Cancelar libera o horário na hora para o link público. A agenda atualiza sozinha a cada minuto.</p>
    </main>
    {toast && <div className="toast" role="status">{toast}</div>}
  </>);
}

function FitIn({ shop, barbers, services, day: initialDay, adminKey, onDone }) {
  const [serviceId, setServiceId] = useState(services[0]?.id || "");
  const [barberId, setBarberId] = useState("any");
  const [day, setDay] = useState(initialDay);
  const [slots, setSlots] = useState(null);
  const [start, setStart] = useState("");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!serviceId) return;
    setSlots(null); setStart("");
    api(`/public/${shop.slug}/availability?serviceId=${serviceId}&date=${day}&barberId=${barberId}`)
      .then((r) => { setSlots(r.slots); setStart(r.slots[0]?.startsAt || ""); })
      .catch((e) => { setSlots([]); setErr(errorText(e)); });
  }, [shop.slug, serviceId, barberId, day]);

  async function submit(e) {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const a = await api(`/admin/shops/${shop.id}/appointments`, {
        method: "POST", adminKey,
        body: { serviceId, barberId, startsAt: start, clientName: name.trim(), clientPhone: phone, consent: false },
      });
      onDone(a);
    } catch (e2) { setErr(errorText(e2)); } finally { setBusy(false); }
  }

  return (
    <form className="card stack fade" onSubmit={submit} noValidate>
      <div><span className="eyebrow">Encaixe</span><h3>Cliente que ligou ou chegou sem marcar</h3></div>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <label className="f" style={{ flex: "1 1 180px" }}>Serviço<select className="i" value={serviceId} onChange={(e) => setServiceId(e.target.value)}>
          {services.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.durationMin} min · {brl(s.price)}</option>)}</select></label>
        <label className="f" style={{ flex: "1 1 150px" }}>Barbeiro<select className="i" value={barberId} onChange={(e) => setBarberId(e.target.value)}>
          <option value="any">Qualquer um livre</option>{barbers.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select></label>
        <label className="f" style={{ flex: "1 1 150px" }}>Dia<input className="i" type="date" value={day} min={todayIn(shop.timezone)} onChange={(e) => e.target.value && setDay(e.target.value)} /></label>
        <label className="f" style={{ flex: "1 1 120px" }}>Horário<select className="i" value={start} onChange={(e) => setStart(e.target.value)} disabled={!slots?.length}>
          {slots === null ? <option>carregando…</option> : slots.length ? slots.map((s) => <option key={s.startsAt} value={s.startsAt}>{s.localTime}</option>) : <option value="">sem horário livre</option>}</select></label>
      </div>
      <div className="row" style={{ alignItems: "flex-end" }}>
        <label className="f" style={{ flex: "2 1 200px" }}>Nome<input className="i" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="f" style={{ flex: "1 1 170px" }}>Telefone<input className="i" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" placeholder="(62) 99999-1234" /></label>
        <button className="btn gold" type="submit" disabled={busy || !start || !name.trim() || !phone.trim()}>{busy ? "Agendando…" : `Encaixar ${shortDay(day)}`}</button>
      </div>
      {err && <p className="err" role="alert">{err}</p>}
    </form>
  );
}
