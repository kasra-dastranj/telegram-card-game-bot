import type { CardData, ProfileData, StatKey } from "./api";

export const statIcons: Record<StatKey, string> = { power: "💪", speed: "⚡", iq: "🧠", popularity: "❤️" };
const statNames: Record<StatKey, string> = { power: "قدرت", speed: "سرعت", iq: "هوش", popularity: "محبوبیت" };
export type Outcome = "win" | "loss" | "tie";

export function safe(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]!));
}

export function brand(profile?: ProfileData): string {
  return `<div class="citadel-brand"><div class="citadel-brand__title"><span class="citadel-sigil" aria-hidden="true">♜</span><span><b dir="ltr">TelBattle</b><small>میدان افسانه‌ها</small></span></div><div class="citadel-purse"><span aria-label="سکه">◉ <bdi>${profile?.coins?.toLocaleString("fa-IR") ?? "—"}</bdi></span><span aria-label="جان">♥ <bdi dir="ltr">${profile ? `${profile.hearts}/${profile.max_hearts}` : "—"}</bdi></span></div></div>`;
}

export function portrait(card: CardData, eager = false): string {
  return `<span class="portrait-fallback" aria-hidden="true">♜</span>${card.image_url ? `<img class="portrait-image" src="${safe(card.image_url)}" alt="${safe(card.name)}" loading="${eager ? "eager" : "lazy"}" decoding="async">` : ""}`;
}

export function combatCard(card?: CardData | null, side = "player", values?: Partial<Record<StatKey, number>>, hiddenLabel = "کارت حریف هنوز مخفیه"): string {
  if (!card) return `<article class="combat-card combat-card--hidden"><div class="card-back-pattern"><span>♜</span><b dir="ltr">TELBATTLE</b></div><p>${safe(hiddenLabel)}</p></article>`;
  return `<article class="combat-card combat-card--${safe(side)} rarity-${safe(card.rarity)}"><div class="combat-card__name"><bdi>${safe(card.name)}</bdi></div><div class="combat-card__portrait">${portrait(card,true)}</div><small class="combat-card__rarity"><bdi>${safe(card.rarity.toUpperCase())}</bdi>${card.origin === "custom" ? " · سفارشی" : ""}</small><div class="combat-card__stats">${(Object.keys(statNames) as StatKey[]).map(stat => `<span title="${statNames[stat]}"><i aria-hidden="true">${statIcons[stat]}</i><bdi>${values?.[stat] ?? card[stat]}</bdi></span>`).join("")}</div></article>`;
}

export function duel(mine?: CardData | null, rival?: CardData | null, values?: Partial<Record<StatKey,number>>, outcome?: Outcome): string {
  return `<div class="citadel-duel ${outcome ? `citadel-duel--${outcome}` : ""}"><div class="duel-side duel-side--player"><small>مبارز تو</small>${combatCard(mine,"player",values,"مبارزت رو انتخاب کن")}</div><span class="duel-vs" aria-hidden="true">VS</span><div class="duel-side duel-side--rival"><small>حریف</small>${combatCard(rival,"rival")}</div></div>`;
}

export function roundTrack(round: number, count = 3): string {
  return `<div class="round-track" aria-label="راوند ${round} از ${count}">${Array.from({length:count},(_,index)=>`<i class="${index+1<round ? "is-done" : index+1===round ? "is-active" : ""}"></i>`).join("")}</div>`;
}

export function resultCrest(outcome: Outcome, title: string): string {
  return `<header class="victory-crest victory-crest--${outcome}"><span aria-hidden="true">${outcome === "win" ? "♛" : outcome === "tie" ? "⚖" : "⚔"}</span><p dir="ltr">${outcome === "win" ? "VICTORY" : outcome === "tie" ? "DRAW" : "DEFEAT"}</p><h2>${safe(title)}</h2></header>`;
}

export function rewardTiles(rewards?: Record<string,number | undefined>): string {
  if (!rewards) return "";
  const names: Record<string,[string,string]> = { xp:["XP","تجربه"],score:["♜","امتیاز"],coins:["◉","سکه"],hearts_lost:["♥","جان مصرف‌شده"],tp_delta:["✦","تغییر رتبه"] };
  const items = Object.entries(names).filter(([key])=>typeof rewards[key] === "number" && Number.isFinite(rewards[key]));
  if (!items.length) return "";
  return `<section class="citadel-rewards glass-panel" aria-label="پاداش واقعی نبرد"><h3>دستاورد نبرد</h3><div>${items.map(([key,[icon,label]])=>{const value=key === "hearts_lost" ? -Math.abs(rewards[key]!) : rewards[key]!;return `<article class="${value<0 ? "is-cost" : ""}"><i aria-hidden="true">${icon}</i><bdi dir="ltr">${value>0 ? "+" : ""}${value}</bdi><small>${label}</small></article>`;}).join("")}</div></section>`;
}

export function playerProgress(profile?: ProfileData): string {
  const xp=profile?.current_xp, target=profile?.xp_to_next_level;
  if (xp === undefined || target === undefined) return "";
  const percent=target>0 ? Math.max(0,Math.min(100,xp/target*100)) : 100;
  return `<article class="citadel-level glass-panel"><span class="level-medallion"><small>LEVEL</small><bdi>${profile?.level ?? 1}</bdi></span><div><header><strong>مسیر پیشرفتت</strong><bdi dir="ltr">${xp} / ${target} XP</bdi></header><div class="citadel-meter" role="progressbar" aria-label="پیشرفت سطح" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(percent)}"><i style="width:${percent}%"></i></div><small>${target>0 ? `${Math.max(0,target-xp)} XP تا سطح بعد` : "به بالاترین سطح رسیدی"}</small></div></article>`;
}

export function shopArt(kind: string): string {
  const paths: Record<string,string> = {
    upgrade_card:'<path d="m12 4 7 8h-4v8H9v-8H5l7-8Z"/>',
    silver_ticket:'<path d="M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4V6Z"/><path d="m12 8 1.2 2.4 2.8.4-2 2 .5 2.8L12 14l-2.5 1.6.5-2.8-2-2 2.8-.4L12 8Z"/>',
    deck_slot:'<rect x="3" y="5" width="11" height="15" rx="1"/><path d="m12 3 8 3-4 14M7 12h5m-2.5-2.5v5"/>',
    refill:'<path d="M12 20 3.5 11.5a5 5 0 0 1 7-7L12 6l1.5-1.5a5 5 0 0 1 7 7L12 20Z"/>',
    permanent_heart:'<path d="M12 20 3.5 11.5a5 5 0 0 1 7-7L12 6l1.5-1.5a5 5 0 0 1 7 7L12 20ZM9 11h6m-3-3v6"/>',
  };
  return `<span class="shop-art shop-art--${safe(kind)}" aria-hidden="true"><svg viewBox="0 0 24 24">${paths[kind] || paths.silver_ticket}</svg><i></i></span>`;
}
