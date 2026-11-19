// Página pública de agendamento: serviço → barbeiro → dia e horário → dados → confirmação.
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import {
  addDays, api, brl, dayIn, errorText, fmtDay, fmtPhone, mapsUrl, MES, store, timeIn, todayIn, WD, weekday,
} from "../lib.js";

const STEPS = ["Serviço", "Barbeiro", "Horário", "Seus dados"];

export default function Booking() {
  const { slug } = useParams();
  const [page, setPage] = useState(null); // {shop, barbers, services}
  const [loadErr, setLoadErr] = useState("");
  const [step, setStep] = useState(0);
  const [serviceId, setServiceId] = useState(null);
  const [barberId, setBarberId] = useState(null);
  const [day, setDay] = useState(null);
  const [slots, setSlots] = useState(null);
  const [start, setStart] = useState(null);
  const me = store.get("navalha-me") || {};
  const [name, setName] = useState(me.name || "");
  const [phone, setPhone] = useState(me.phone || "");
  const [consent, setConsent] = useState(false);
  const [remember, setRemember] = useState(!!me.phone);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);

  useEffect(() => {
    api(`/public/${slug}`)
      .then((p) => { setPage(p); document.title = `Agendar · ${p.shop.name}`; })
      .catch((e) => setLoadErr(e.status === 404 ? "Barbearia não encontrada. Confira o link." : errorText(e)));
  }, [slug]);

  const shop = page?.shop;
  const tz = shop?.timezone || "America/Sao_Paulo";
  const service = page?.services.find((s) => s.id === serviceId);
  const barberName = barberId === "any" ? "qualquer barbeiro" : page?.barbers.find((b) => b.id === barberId)?.name;
  const days = useMemo(() => (shop ? [...Array(14)].map((_, i) => addDays(todayIn(tz), i)) : []), [shop, tz]);
  const openDay = (k) => (shop?.openingHours?.[String(weekday(k))] || []).length > 0;

  const loadSlots = useCallback(async (k) => {
    setSlots(null); setStart(null);
    try {
      const r = await api(`/public/${slug}/availability?serviceId=${serviceId}&date=${k}&barberId=${barberId}`);
      setSlots(r.slots);
    } catch (e) { setSlots([]); setErr(errorText(e)); }
  }, [slug, serviceId, barberId]);

  useEffect(() => { if (step === 2 && day) loadSlots(day); }, [step, day, loadSlots]);

  function goBarber(id) {
    setBarberId(id); setErr("");
    setDay(days.find(openDay) || days[0]);
    setStep(2);
  }

  async function submit(e) {
    e.preventDefault(); setErr("");
    if (!consent) { setErr("Para agendar, aceite receber o lembrete e a política de privacidade."); return; }
    setBusy(true);
    try {
      const a = await api(`/public/${slug}/appointments`, {
        method: "POST",
        body: { serviceId, barberId, startsAt: start, clientName: name.trim(), clientPhone: phone, consent },
      });
      if (remember) store.set("navalha-me", { name: name.trim(), phone }); else store.del("navalha-me");
      setDone(a);
    } catch (e2) {
      setErr(errorText(e2));
      if (e2.status === 409) { setStep(2); loadSlots(day); }
    } finally { setBusy(false); }
  }

  function restart() {
    setDone(null); setStep(0); setServiceId(null); setBarberId(null); setDay(null); setSlots(null); setStart(null); setErr(""); setConsent(false);
  }

  if (loadErr) return <main className="wrap"><div className="card"><h2>Ops</h2><p className="muted">{loadErr}</p></div></main>;
  if (!page) return <main className="wrap"><div className="stack"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div></main>;

  const hero = (
    <section className="hero">
      <div className="logo">
        <img src={`/logos/${shop.slug}.webp`} alt={`Logo ${shop.name}`} onError={(e) => { e.currentTarget.replaceWith(Object.assign(document.createElement("div"), { className: "initial", textContent: shop.name[0] })); }} />
      </div>
      <div className="stack" style={{ gap: 8 }}>
        <h1><span className="gold-text">{shop.name}</span></h1>
        <span className="muted">{shop.address}{shop.cep ? ` · CEP ${shop.cep}` : ""}</span>
        <div className="row"><a className="btn ghost sm" href={mapsUrl(shop)} target="_blank" rel="noopener">📍 Como chegar</a>
          {shop.whatsapp && <a className="btn ghost sm" href={`https://wa.me/${shop.whatsapp.replace(/\D/g, "")}`} target="_blank" rel="noopener">WhatsApp</a>}</div>
      </div>
    </section>
  );

  if (done) {
    const d = dayIn(done.startsAt, tz);
    return (
      <main className="wrap fade">{hero}
        <div className="ticket stack">
          <div className="row" style={{ gap: 14 }}><span className="check-ic" aria-hidden>✓</span>
            <div><span className="eyebrow">Horário garantido</span><h2>{fmtDay(d)} · {timeIn(done.startsAt, tz)}</h2></div></div>
          <dl className="dl">
            <dt>Serviço</dt><dd>{done.serviceName} · <span className="price">{brl(done.price)}</span></dd>
            <dt>Barbeiro</dt><dd>{done.barberName}</dd>
            <dt>Nome</dt><dd>{done.clientName}</dd>
            <dt>Endereço</dt><dd>{shop.address} · <a href={mapsUrl(shop)} target="_blank" rel="noopener">ver no mapa</a></dd>
          </dl>
          <p className="note">Na véspera a barbearia te manda um lembrete no WhatsApp. Precisa mudar? Fale com a barbearia{shop.whatsapp ? ` pelo ${fmtPhone(shop.whatsapp)}` : ""}.</p>
        </div>
        <div className="row" style={{ marginTop: 16 }}><button className="btn" onClick={restart}>Agendar outro horário</button></div>
      </main>
    );
  }

  return (
    <main className="wrap">
      {hero}
      <div className="progress" aria-hidden>{STEPS.map((l, i) => <div key={l} className={i <= step ? "on" : ""}><span><i /></span>{l}</div>)}</div>
      <div className="stack fade" key={step}>
        {step === 0 && <>
          <h2>Escolha o serviço</h2>
          <div className="choices">{page.services.map((s) => (
            <button key={s.id} className="choice" aria-pressed={s.id === serviceId} onClick={() => { setServiceId(s.id); setStep(1); }}>
              <b>{s.name}</b><span className="price">{brl(s.price)}</span><span className="muted">{s.durationMin} min</span>
            </button>))}
          </div>
        </>}

        {step === 1 && <>
          <h2>Com quem?</h2>
          <div className="choices">
            {page.barbers.length > 1 && <button className="choice" onClick={() => goBarber("any")}><span className="avatar gold">★</span><b>Qualquer um</b><span className="muted">mais horários disponíveis</span></button>}
            {page.barbers.map((b) => <button key={b.id} className="choice" aria-pressed={b.id === barberId} onClick={() => goBarber(b.id)}><span className="avatar">{b.name[0]}</span><b>{b.name}</b></button>)}
          </div>
        </>}

        {step === 2 && <>
          <h2>Dia e horário</h2>
          <div className="days">{days.map((k) => {
            const [, m, d] = k.split("-");
            return <button key={k} className="day" aria-pressed={k === day} disabled={!openDay(k)} onClick={() => setDay(k)}>
              <small>{k === days[0] ? "hoje" : WD[weekday(k)]}</small><b>{+d}</b><small>{MES[+m - 1]}</small></button>;
          })}</div>
          <p className="muted" style={{ margin: 0 }}>{fmtDay(day)} · {service.name} ({service.durationMin} min) com {barberName}</p>
          {slots === null ? <div className="skeleton" />
            : slots.length ? <div className="slots">{slots.map((s) => (
              <button key={s.startsAt} className="slot" aria-pressed={s.startsAt === start} onClick={() => setStart(s.startsAt)}>{s.localTime}</button>))}</div>
            : <p className="note">Sem horários livres nesse dia. Tente outro dia{barberId !== "any" ? " ou “qualquer um”" : ""}.</p>}
          {err && <p className="err" role="alert">{err}</p>}
        </>}

        {step === 3 && <>
          <h2>Seus dados</h2>
          <div className="card"><dl className="dl">
            <dt>Serviço</dt><dd>{service.name} · <span className="price">{brl(service.price)}</span></dd>
            <dt>Barbeiro</dt><dd>{barberId === "any" ? "qualquer barbeiro (definido ao confirmar)" : barberName}</dd>
            <dt>Quando</dt><dd>{fmtDay(day)} · {timeIn(start, tz)}</dd>
          </dl></div>
          <form className="stack" onSubmit={submit} noValidate>
            <label className="f">Nome<input className="i" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" placeholder="Como te chamamos" required /></label>
            <label className="f">WhatsApp<input className="i" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" autoComplete="tel" placeholder="(62) 99999-1234" required /></label>
            <label className="check"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /><span>Aceito receber o lembrete deste horário pelo WhatsApp e concordo com a política de privacidade.</span></label>
            <label className="check"><input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} /><span>Lembrar meu nome e telefone neste aparelho</span></label>
            <details className="muted" style={{ fontSize: 13 }}><summary style={{ cursor: "pointer", color: "var(--gold)" }}>Política de privacidade (resumo)</summary>
              <p>A {shop.name} guarda seu nome, telefone e histórico de atendimentos para organizar a agenda e enviar lembretes. Os dados não são vendidos nem compartilhados. Para apagar seus dados, peça à barbearia.</p></details>
            {err && <p className="err" role="alert">{err}</p>}
            <button className="btn gold" type="submit" disabled={busy || !name.trim() || !phone.trim()}>{busy ? "Confirmando…" : "Confirmar agendamento"}</button>
          </form>
        </>}

        {step > 0 && <div className="row">
          <button className="btn ghost sm" onClick={() => { setErr(""); setStep(step - 1); }}>← Voltar</button>
          {step === 2 && start && <button className="btn" onClick={() => { setErr(""); setStep(3); }}>Continuar →</button>}
        </div>}
      </div>
    </main>
  );
}
