import Phaser from "phaser";
import "./styles.css";
import { ApiError, api, type CardData, type CardPage, type ClaimStatus, type DeckData, type Difficulty, type FightData, type FusionPreview, type MissionData, type ProfileData, type QuickState, type RoundData, type SkinCollection, type StatKey, type UpgradePreview } from "./api";
import { BattleScene } from "./BattleScene";

type Screen = "lobby" | "profileHub" | "collection" | "decks" | "progress" | "shop" | "quickMenu" | "quickWait" | "cards" | "quickMatch" | "quickResult" | "battle" | "result";

const state: {
  screen: Screen;
  profile?: ProfileData;
  profileStatus: "loading" | "ready" | "error";
  profileError?: string;
  cards: CardData[];
  selected?: CardData;
  difficulty: Difficulty;
  fight?: FightData;
  lastRound?: RoundData;
  loading: boolean;
  playMode: "solo" | "quick";
  quick?: QuickState;
  incomingInvite?: string;
  collection?: CardPage;
  collectionPage: number;
  collectionRarity: string;
  collectionSort: string;
  collectionQuery: string;
  detailCard?: CardData;
  pendingUpgrade?: UpgradePreview;
  decks: DeckData[];
  deckEditor?: { deckId?: string; name: string; cardIds: string[] };
  deleteDeckId?: string;
  claimStatus?: ClaimStatus;
  missions: MissionData[];
  rewardCard?: CardData;
  skinPanel?: { cardId: string; data: SkinCollection };
  fusion: { target: "epic" | "legend"; cardIds: string[]; retainedId?: string; preview?: FusionPreview };
} = {
  screen: "lobby",
  profileStatus: "loading",
  cards: [],
  difficulty: "medium",
  loading: false,
  playMode: "solo",
  collectionPage: 1,
  collectionRarity: "all",
  collectionSort: "rarity",
  collectionQuery: "",
  decks: [],
  missions: [],
  fusion: { target: "epic", cardIds: [] },
};

let quickPollTimer: number | undefined;

const labels: Record<StatKey, { title: string; short: string }> = {
  power: { title: "قدرت", short: "POW" },
  speed: { title: "سرعت", short: "SPD" },
  iq: { title: "هوش", short: "IQ" },
  popularity: { title: "محبوبیت", short: "POP" },
};

const scene = new BattleScene();
const game = new Phaser.Game({
  type: Phaser.AUTO,
  parent: "game-root",
  width: 720,
  height: 1280,
  transparent: false,
  antialias: true,
  render: { powerPreference: "high-performance" },
  scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  scene,
});

const ui = document.querySelector<HTMLDivElement>("#ui-root")!;
const toast = document.querySelector<HTMLDivElement>("#toast")!;

function haptic(kind: "light" | "medium" | "success" = "light"): void {
  const feedback = window.Telegram?.WebApp?.HapticFeedback;
  if (!feedback) return;
  if (kind === "success") feedback.notificationOccurred("success");
  else feedback.impactOccurred(kind);
}

function showToast(message: string): void {
  toast.textContent = message;
  toast.classList.add("toast--visible");
  window.setTimeout(() => toast.classList.remove("toast--visible"), 3000);
}

game.events.on("card-drag-start", () => haptic("light"));
game.events.on("hand-page-changed", (page: number, pageCount: number) => {
  ui.dataset.handPage = String(page);
  ui.dataset.handPageCount = String(pageCount);
});
game.events.on("card-dropped", (cardId: string) => {
  if (state.playMode !== "quick" || state.loading || state.quick?.phase !== "card_selection" || state.quick.my_card_locked) return;
  const card = state.cards.find((item) => item.card_id === cardId);
  if (!card) return;
  state.selected = card;
  void submitQuickCard();
});

function render(): void {
  ui.dataset.screen = state.screen;
  if (state.screen === "lobby") ui.innerHTML = lobbyTemplate();
  if (state.screen === "profileHub") ui.innerHTML = profileHubTemplate();
  if (state.screen === "collection") ui.innerHTML = collectionTemplate();
  if (state.screen === "decks") ui.innerHTML = decksTemplate();
  if (state.screen === "progress") ui.innerHTML = progressTemplate();
  if (state.screen === "shop") ui.innerHTML = shopTemplate();
  if (state.screen === "quickMenu") ui.innerHTML = quickMenuTemplate();
  if (state.screen === "quickWait") ui.innerHTML = quickWaitTemplate();
  if (state.screen === "cards") ui.innerHTML = cardsTemplate();
  if (state.screen === "quickMatch") ui.innerHTML = quickMatchTemplate();
  if (state.screen === "quickResult") ui.innerHTML = quickResultTemplate();
  if (state.screen === "battle") ui.innerHTML = battleTemplate();
  if (state.screen === "result") ui.innerHTML = resultTemplate();
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatDuration(totalSeconds = 0): string {
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours) return `${hours} ساعت و ${minutes} دقیقه`;
  if (minutes) return `${minutes} دقیقه`;
  return "کمتر از یک دقیقه";
}

function navIcon(kind: "game" | "cards" | "decks" | "progress" | "shop"): string {
  const paths = {
    game: '<path d="M8 12h8M12 8v8M5 7.5 3.8 16a3 3 0 0 0 5.1 2.5l1.1-1h4l1.1 1a3 3 0 0 0 5.1-2.5L19 7.5A4 4 0 0 0 15 4H9a4 4 0 0 0-4 3.5Z"/>',
    cards: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="m9 8 3-2 3 2-3 4-3-4Z"/>',
    decks: '<path d="m6 4 12 3-12 3-3-3 3-3Z"/><path d="m3 12 3 3 12-3M3 17l3 3 12-3"/>',
    progress: '<path d="M4 19V9M10 19V5M16 19v-7M22 19H2"/>',
    shop: '<path d="M4 9h16l-1 12H5L4 9Z"/><path d="M8 9a4 4 0 0 1 8 0"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[kind]}</svg>`;
}

function bottomNav(active?: "game" | "cards" | "decks" | "progress" | "shop"): string {
  const items: Array<["game" | "cards" | "decks" | "progress" | "shop", string, string]> = [
    ["game", "بازی", "hub-game"],
    ["cards", "کارت‌ها", "open-collection"],
    ["decks", "دک‌ها", "hub-decks"],
    ["progress", "پیشرفت", "hub-progress"],
    ["shop", "فروشگاه", "hub-shop"],
  ];
  return `<nav class="hub-nav glass-panel" aria-label="مرکز بازیکن">
    ${items.map(([key, label, action]) => `<button data-action="${action}" class="${active === key ? "is-active" : ""}" aria-current="${active === key ? "page" : "false"}">${navIcon(key)}<span>${label}</span></button>`).join("")}
  </nav>`;
}

function resourceHud(): string {
  const p = state.profile;
  const xp = p?.current_xp ?? 0;
  const needed = p?.xp_to_next_level ?? 0;
  const percent = needed > 0 ? Math.min(100, Math.round((xp / needed) * 100)) : 100;
  const pending = state.profileStatus === "loading" && !p;
  const value = (amount?: number) => pending ? "…" : amount === undefined ? "—" : amount.toLocaleString("fa-IR");
  return `<header class="hub-hud glass-panel">
    <button class="hub-avatar" data-action="open-profile" aria-label="نمایش پروفایل">${escapeHtml((p?.first_name || "T").slice(0, 1))}</button>
    <div class="hub-level"><span><b>LV ${p?.level ?? 1}</b><small>${escapeHtml(p?.current_tier ?? "Bronze")}</small></span><i><b style="width:${percent}%"></b></i></div>
    <div class="hub-resources">
      <span class="hub-resource hub-heart"><small>جان</small><b dir="ltr">${p ? `${p.hearts}/${p.max_hearts}` : value()}</b></span>
      <span class="hub-resource hub-coin"><small>سکه</small><b>${value(p?.coins)}</b></span>
      <span class="hub-resource hub-cards"><small>کارت</small><b>${value(p?.counts?.cards)}</b></span>
      <span class="hub-resource hub-decks"><small>دک</small><b>${value(p?.counts?.decks)}</b></span>
    </div>
  </header>${profileStatusNotice()}`;
}

function profileStatusNotice(): string {
  if (state.profileStatus === "loading" && !state.profile) {
    return `<div class="profile-sync-note" role="status">در حال همگام‌سازی اطلاعات بازیکن…</div>`;
  }
  if (state.profileStatus !== "error") return "";
  return `<div class="profile-auth-error" role="alert"><p>${escapeHtml(state.profileError || "اطلاعات بازیکن دریافت نشد.")}</p><button data-action="retry-profile">تلاش دوباره</button></div>`;
}

function profileHubTemplate(): string {
  const p = state.profile;
  const stats = p?.stats || {};
  const wins = Number(stats.wins ?? stats.total_wins ?? 0);
  const losses = Number(stats.losses ?? stats.total_losses ?? 0);
  const fights = Number(stats.total_fights ?? stats.total ?? wins + losses);
  const claimText = p?.claim?.can_claim ? "کارت روزانه آماده دریافت است" : `Claim بعدی: ${formatDuration(p?.claim?.remaining_seconds)}`;
  return `
    <section class="screen hub-screen profile-hub-screen">
      ${resourceHud()}
      <div class="hub-scroll">
        <header class="hub-title"><div><p class="eyebrow">PLAYER HUB</p><h1>مرکز فرمانده</h1></div><span class="tier-badge">${escapeHtml(p?.current_tier ?? "Bronze")} · ${p?.tier_points ?? 0} TP</span></header>
        <article class="profile-card glass-panel">
          <div class="profile-avatar">${escapeHtml((p?.first_name || "T").slice(0, 1))}</div>
          <div><small>فرمانده</small><h2>${escapeHtml(p?.first_name || "بازیکن")}</h2><p dir="ltr">${p?.username ? `@${escapeHtml(p.username)}` : "TelBattle Player"}</p></div>
          <strong>${(p?.total_score ?? 0).toLocaleString("fa-IR")}<small>امتیاز</small></strong>
        </article>
        <div class="profile-metrics">
          <article><small>نبردها</small><strong>${fights.toLocaleString("fa-IR")}</strong></article>
          <article><small>برد</small><strong class="positive">${wins.toLocaleString("fa-IR")}</strong></article>
          <article><small>باخت</small><strong class="negative">${losses.toLocaleString("fa-IR")}</strong></article>
        </div>
        <article class="progress-card glass-panel">
          <div><span>Level ${p?.level ?? 1}</span><strong dir="ltr">${p?.current_xp ?? 0} / ${p?.xp_to_next_level ?? 0} XP</strong></div>
          <i><b style="width:${p?.xp_to_next_level ? Math.min(100, ((p.current_xp || 0) / p.xp_to_next_level) * 100) : 100}%"></b></i>
        </article>
        <div class="hub-summary-list">
          <button data-action="open-collection"><span>کلکسیون کارت‌ها<small>${p?.counts?.cards ?? 0} کارت در اختیار داری</small></span><b>←</b></button>
          <button data-action="hub-decks"><span>دک‌های من<small>${p?.counts?.decks ?? 0} دک ساخته شده</small></span><b>←</b></button>
          <button data-action="hub-progress"><span>پاداش‌ها و مأموریت‌ها<small>${p?.counts?.missions_ready ?? 0} پاداش آماده · ${claimText}</small></span><b>←</b></button>
        </div>
        ${p && p.hearts < p.max_hearts ? `<p class="heart-timer">بازیابی جان‌ها: ${formatDuration(p.heart_reset_seconds)}</p>` : ""}
      </div>
      ${bottomNav()}
    </section>`;
}

function collectionTemplate(): string {
  const page = state.collection;
  const cards = (page?.cards || []).map((card) => `
    <button class="collection-card rarity-${escapeHtml(card.rarity)}" data-action="card-detail" data-id="${escapeHtml(card.card_id)}">
      <span class="collection-card__art" style="background-image:url('${escapeHtml(card.image_url)}')"></span>
      <span class="collection-card__body"><strong dir="auto">${escapeHtml(card.name)}</strong><small>${escapeHtml(card.rarity.toUpperCase())} · ${card.score ?? card.power + card.speed + card.iq + card.popularity}</small></span>
      ${card.is_in_cooldown ? '<i class="cooldown-badge">COOLDOWN</i>' : ""}
    </button>`).join("");
  const detail = state.detailCard ? cardDetailSheet(state.detailCard) : state.skinPanel ? skinsSheet() : "";
  return `
    <section class="screen hub-screen collection-screen">
      ${resourceHud()}
      <div class="hub-scroll">
        <header class="hub-title"><div><p class="eyebrow">COLLECTION</p><h1>کارت‌های من</h1></div><strong>${page?.total ?? state.profile?.counts?.cards ?? 0}</strong></header>
        <div class="collection-tools glass-panel">
          <label class="search-field"><span class="sr-only">جستجوی کارت</span><input id="collection-query" value="${escapeHtml(state.collectionQuery)}" placeholder="نام کارت را جستجو کن" autocomplete="off"></label>
          <div>
            <label><span>Rarity</span><select id="collection-rarity"><option value="all">همه</option><option value="normal" ${state.collectionRarity === "normal" ? "selected" : ""}>Normal</option><option value="rare" ${state.collectionRarity === "rare" ? "selected" : ""}>Rare</option><option value="epic" ${state.collectionRarity === "epic" ? "selected" : ""}>Epic</option><option value="legend" ${state.collectionRarity === "legend" ? "selected" : ""}>Legend</option></select></label>
            <label><span>مرتب‌سازی</span><select id="collection-sort"><option value="rarity">Rarity</option><option value="score" ${state.collectionSort === "score" ? "selected" : ""}>امتیاز کل</option><option value="power" ${state.collectionSort === "power" ? "selected" : ""}>قدرت</option><option value="speed" ${state.collectionSort === "speed" ? "selected" : ""}>سرعت</option><option value="iq" ${state.collectionSort === "iq" ? "selected" : ""}>هوش</option><option value="popularity" ${state.collectionSort === "popularity" ? "selected" : ""}>محبوبیت</option><option value="name" ${state.collectionSort === "name" ? "selected" : ""}>نام</option></select></label>
          </div>
        </div>
        <div class="collection-grid" aria-live="polite">${state.loading ? skeletons() : cards || '<p class="empty-state">کارتی با این مشخصات پیدا نشد.</p>'}</div>
        ${page && page.page_count > 1 ? `<div class="pager"><button data-action="collection-page" data-page="${page.page - 1}" ${page.page <= 1 ? "disabled" : ""}>قبلی</button><span>صفحه ${page.page} از ${page.page_count}</span><button data-action="collection-page" data-page="${page.page + 1}" ${page.page >= page.page_count ? "disabled" : ""}>بعدی</button></div>` : ""}
      </div>
      ${bottomNav("cards")}
      ${detail}
    </section>`;
}

function cardDetailSheet(card: CardData): string {
  const stats: Array<[string, number]> = [["قدرت", card.power], ["سرعت", card.speed], ["هوش", card.iq], ["محبوبیت", card.popularity]];
  const upgrade = card.upgrade;
  const pending = state.pendingUpgrade?.card_id === card.card_id ? state.pendingUpgrade : undefined;
  const upgradeControl = upgrade?.ok
    ? `<button class="primary-button" data-action="preview-upgrade" ${upgrade.blocked_by_match || !upgrade.can_afford || state.loading ? "disabled" : ""}>ارتقا به <b dir="ltr">${escapeHtml(upgrade.to_rarity?.toUpperCase())}</b> · ${Number(upgrade.price || 0).toLocaleString("fa-IR")} سکه</button>
       ${upgrade.blocked_by_match ? '<p class="sheet-warning">تا پایان مسابقه امکان ارتقا وجود ندارد.</p>' : !upgrade.can_afford ? '<p class="sheet-warning">سکه کافی برای این ارتقا نداری.</p>' : ""}`
    : `<p class="upgrade-unavailable">${escapeHtml(upgrade?.error || "این کارت قابل ارتقا نیست.")}</p>`;
  const confirm = pending?.ok ? `<div class="upgrade-confirm" role="alertdialog" aria-label="تأیید ارتقای کارت">
    <strong>ارتقای نهایی را تأیید می‌کنی؟</strong>
    <p><span dir="ltr">${escapeHtml(pending.from_rarity?.toUpperCase())}</span> به <span dir="ltr">${escapeHtml(pending.to_rarity?.toUpperCase())}</span> · ${Number(pending.price || 0).toLocaleString("fa-IR")} سکه · ${pending.xp} XP</p>
    <div><button class="secondary-button" data-action="cancel-upgrade">انصراف</button><button class="primary-button" data-action="confirm-upgrade" ${state.loading ? "disabled" : ""}>${state.loading ? "در حال انجام…" : "تأیید ارتقا"}</button></div>
  </div>` : "";
  return `<div class="sheet-backdrop" data-action="close-card-detail"></div>
    <aside class="card-sheet glass-panel" role="dialog" aria-modal="true" aria-label="جزئیات کارت">
      <button class="sheet-close" data-action="close-card-detail" aria-label="بستن">×</button>
      <div class="card-sheet__hero" style="background-image:url('${escapeHtml(card.image_url)}')"></div>
      <div class="card-sheet__content">
        <p class="eyebrow">${escapeHtml(card.rarity.toUpperCase())}</p>
        <h2 dir="auto">${escapeHtml(card.name)}</h2>
        <p>${escapeHtml(card.biography || "زندگینامه‌ای ثبت نشده است.")}</p>
        <div class="card-stat-list">${stats.map(([name, value]) => `<span><small>${name}</small><strong>${value}</strong></span>`).join("")}</div>
        <div class="card-meta"><span>نوع: <b dir="ltr">${escapeHtml(card.card_type || "—")}</b></span><span>Ability: <b>${escapeHtml(card.abilities?.join("، ") || "ندارد")}</b></span></div>
        ${card.is_in_cooldown ? '<p class="sheet-warning">این کارت در Cooldown است.</p>' : ""}
        <div class="card-actions"><button class="secondary-button" data-action="open-skins" data-id="${escapeHtml(card.card_id)}">ظاهر کارت</button>${upgradeControl}</div>
        ${confirm}
      </div>
    </aside>`;
}

function decksTemplate(): string {
  const decks = state.decks.map((deck) => `<article class="deck-panel glass-panel">
    <header><div><small>${deck.is_valid ? "آماده نبرد" : "نیازمند اصلاح"}</small><h2>${escapeHtml(deck.deck_name)}</h2></div><strong>+${deck.synergy.score}</strong></header>
    <div class="deck-card-strip">${deck.cards.map((card) => `<span title="${escapeHtml(card.name)}" style="background-image:url('${escapeHtml(card.image_url)}')"><b dir="auto">${escapeHtml(card.name)}</b></span>`).join("")}</div>
    <p>${deck.synergy.reasons.length ? deck.synergy.reasons.map(escapeHtml).join(" · ") : "بدون هم‌افزایی ویژه"}</p>
    <footer><button class="secondary-button" data-action="edit-deck" data-id="${escapeHtml(deck.deck_id)}">ویرایش</button><button class="danger-button" data-action="ask-delete-deck" data-id="${escapeHtml(deck.deck_id)}">حذف</button></footer>
  </article>`).join("");
  return `<section class="screen hub-screen decks-screen">
    ${resourceHud()}
    <div class="hub-scroll">
      <header class="hub-title"><div><p class="eyebrow">DECK LAB</p><h1>دک‌های من</h1></div><button class="compact-cta" data-action="new-deck">دک جدید</button></header>
      <p class="section-note">هر دک دقیقاً سه کارت دارد. هم‌افزایی فقط روی سرور محاسبه می‌شود.</p>
      <div class="deck-list">${state.loading ? skeletons() : decks || '<p class="empty-state">هنوز دکی نساختی.</p>'}</div>
    </div>
    ${bottomNav("decks")}
    ${state.deckEditor ? deckEditorSheet() : ""}
    ${state.deleteDeckId ? deleteDeckConfirm() : ""}
  </section>`;
}

function deckEditorSheet(): string {
  const editor = state.deckEditor!;
  return `<div class="sheet-backdrop" data-action="close-deck-editor"></div><aside class="deck-editor glass-panel" role="dialog" aria-modal="true" aria-label="ویرایش دک">
    <header><div><p class="eyebrow">${editor.deckId ? "EDIT DECK" : "NEW DECK"}</p><h2>${editor.deckId ? "ویرایش دک" : "ساخت دک"}</h2></div><button class="sheet-close" data-action="close-deck-editor" aria-label="بستن">×</button></header>
    <label class="deck-name-field"><span>نام دک</span><input id="deck-name" maxlength="20" value="${escapeHtml(editor.name)}" placeholder="مثلاً تیم اصلی"></label>
    <div class="selection-counter"><strong>${editor.cardIds.length} / 3</strong><span>سه کارت متفاوت انتخاب کن</span></div>
    <div class="deck-picker">${state.cards.map((card) => `<button class="deck-pick ${editor.cardIds.includes(card.card_id) ? "is-selected" : ""}" data-action="toggle-deck-card" data-id="${escapeHtml(card.card_id)}" aria-pressed="${editor.cardIds.includes(card.card_id)}"><span style="background-image:url('${escapeHtml(card.image_url)}')"></span><b dir="auto">${escapeHtml(card.name)}</b><small dir="ltr">${escapeHtml(card.rarity.toUpperCase())}</small></button>`).join("")}</div>
    <button class="primary-button" data-action="save-deck" ${editor.cardIds.length !== 3 || state.loading ? "disabled" : ""}>${state.loading ? "در حال ذخیره…" : "ذخیره دک"}</button>
  </aside>`;
}

function deleteDeckConfirm(): string {
  const deck = state.decks.find((item) => item.deck_id === state.deleteDeckId);
  return `<div class="sheet-backdrop" data-action="cancel-delete-deck"></div><aside class="confirm-dialog glass-panel" role="alertdialog" aria-modal="true" aria-label="تأیید حذف دک"><h2>حذف «${escapeHtml(deck?.deck_name || "دک") }»؟</h2><p>کارت‌ها حذف نمی‌شوند؛ فقط ترکیب دک پاک می‌شود.</p><div><button class="secondary-button" data-action="cancel-delete-deck">انصراف</button><button class="danger-button" data-action="confirm-delete-deck" ${state.loading ? "disabled" : ""}>حذف دک</button></div></aside>`;
}

function progressTemplate(): string {
  const claim = state.claimStatus;
  const missions = state.missions.map((mission) => `<article class="mission-card glass-panel ${mission.completed ? "is-complete" : ""}">
    <header><div><small dir="auto">${escapeHtml(mission.card_name)}</small><h2>${escapeHtml(mission.name)}</h2></div><strong>${mission.progress_percent}%</strong></header>
    <p>${escapeHtml(mission.description)}</p><i><b style="width:${mission.progress_percent}%"></b></i>
    <footer><span dir="ltr">${mission.current_progress} / ${mission.target}</span>${mission.reward_claimed ? '<em>دریافت شده</em>' : mission.can_claim ? `<button data-action="claim-mission" data-id="${escapeHtml(mission.mission_id)}">دریافت Legend</button>` : '<em>در حال انجام</em>'}</footer>
  </article>`).join("");
  return `<section class="screen hub-screen progress-screen">
    ${resourceHud()}<div class="hub-scroll"><header class="hub-title"><div><p class="eyebrow">PROGRESS</p><h1>پیشرفت و پاداش</h1></div></header>
    <article class="daily-claim glass-panel"><div><small>DAILY CARD</small><h2>${claim?.can_claim ? "کارت روزانه آماده است" : "کارت امروز دریافت شده"}</h2><p>${claim?.can_claim ? `${claim.pool_count} کارت در Pool` : `دریافت بعدی: ${formatDuration(claim?.remaining_seconds)}`}</p></div><button data-action="claim-daily" ${!claim?.can_claim || state.loading ? "disabled" : ""}>${state.loading ? "…" : "دریافت کارت"}</button></article>
    ${state.rewardCard ? `<article class="reward-reveal glass-panel"><span style="background-image:url('${escapeHtml(state.rewardCard.image_url)}')"></span><div><small>پاداش تازه</small><h2 dir="auto">${escapeHtml(state.rewardCard.name)}</h2><b dir="ltr">${escapeHtml(state.rewardCard.rarity.toUpperCase())}</b></div></article>` : ""}
    <header class="subsection-title"><h2>مأموریت‌های کارت</h2><span>${state.missions.length}</span></header><div class="mission-list">${state.loading ? skeletons() : missions || '<p class="empty-state">برای کارت‌های فعلی مأموریتی ثبت نشده است.</p>'}</div></div>${bottomNav("progress")}
  </section>`;
}

function skinsSheet(): string {
  const panel = state.skinPanel!;
  const card = state.cards.find((item) => item.card_id === panel.cardId);
  const items = panel.data.skins.map((skin) => {
    const unlocked = Boolean(skin.unlocked);
    const active = panel.data.active_skin_id === skin.skin_id;
    return `<article class="skin-card ${active ? "is-active" : ""}"><span style="background-image:url('${escapeHtml(skin.image_url)}')"></span><div><small dir="ltr">${escapeHtml(skin.skin_type.toUpperCase())}</small><h3 dir="auto">${escapeHtml(skin.name)}</h3><p>${escapeHtml(skin.description || "ظاهر اختصاصی کارت")}</p></div>${active ? '<b>فعال</b>' : unlocked ? `<button data-action="activate-skin" data-card="${escapeHtml(panel.cardId)}" data-id="${escapeHtml(skin.skin_id)}">فعال‌کردن</button>` : `<button data-action="purchase-skin" data-card="${escapeHtml(panel.cardId)}" data-id="${escapeHtml(skin.skin_id)}">${skin.price.toLocaleString("fa-IR")} سکه</button>`}</article>`;
  }).join("");
  return `<div class="sheet-backdrop" data-action="close-skins"></div><aside class="skins-sheet glass-panel" role="dialog" aria-modal="true" aria-label="پوسته‌های کارت"><header><div><p class="eyebrow">CARD SKINS</p><h2 dir="auto">${escapeHtml(card?.name || "ظاهر کارت")}</h2></div><button class="sheet-close" data-action="close-skins" aria-label="بستن">×</button></header><button class="default-skin ${panel.data.active_skin_id ? "" : "is-active"}" data-action="activate-default-skin" data-card="${escapeHtml(panel.cardId)}">ظاهر پیش‌فرض ${panel.data.active_skin_id ? "" : "· فعال"}</button><div class="skin-list">${items || '<p class="empty-state">هنوز پوسته‌ای برای این کارت ثبت نشده است.</p>'}</div></aside>`;
}

function shopTemplate(): string {
  const source = state.fusion.target === "epic" ? "normal" : "epic";
  const eligible = state.cards.filter((card) => card.rarity === source);
  const selectedCards = state.fusion.cardIds.map((id) => state.cards.find((card) => card.card_id === id)).filter(Boolean) as CardData[];
  const cards = eligible.map((card) => `<button class="fusion-card ${state.fusion.cardIds.includes(card.card_id) ? "is-selected" : ""}" data-action="toggle-fusion-card" data-id="${escapeHtml(card.card_id)}" aria-pressed="${state.fusion.cardIds.includes(card.card_id)}"><span style="background-image:url('${escapeHtml(card.image_url)}')"></span><b dir="auto">${escapeHtml(card.name)}</b><small dir="ltr">${escapeHtml(card.rarity.toUpperCase())}</small></button>`).join("");
  const retain = selectedCards.length === 3 ? `<div class="retained-picker"><p>کدام کارت باقی بماند و ارتقا بگیرد؟</p>${selectedCards.map((card) => `<button data-action="retain-fusion-card" data-id="${escapeHtml(card.card_id)}" class="${state.fusion.retainedId === card.card_id ? "is-selected" : ""}" dir="auto">${escapeHtml(card.name)}</button>`).join("")}</div>` : "";
  return `<section class="screen hub-screen shop-screen">${resourceHud()}<div class="hub-scroll"><header class="hub-title"><div><p class="eyebrow">WORKSHOP</p><h1>آزمایشگاه Fusion</h1></div></header>
    <article class="fusion-warning glass-panel"><strong>سه کارت وارد می‌شوند؛ فقط یکی باقی می‌ماند.</strong><p>دو کارت دیگر برای همیشه از کلکسیون خارج می‌شوند. قبل از اجرا نتیجه را می‌بینی.</p></article>
    <div class="fusion-target"><button data-action="fusion-target" data-value="epic" class="${state.fusion.target === "epic" ? "is-active" : ""}"><b dir="ltr">NORMAL → EPIC</b><small>${state.cards.filter((card) => card.rarity === "normal").length} کارت واجد شرایط</small></button><button data-action="fusion-target" data-value="legend" class="${state.fusion.target === "legend" ? "is-active" : ""}"><b dir="ltr">EPIC → LEGEND</b><small>${state.cards.filter((card) => card.rarity === "epic").length} کارت واجد شرایط</small></button></div>
    <div class="selection-counter"><strong>${state.fusion.cardIds.length} / 3</strong><span>کارت‌های ${source.toUpperCase()}</span></div><div class="fusion-grid">${cards || '<p class="empty-state">کارت کافی برای این Fusion نداری.</p>'}</div>${retain}
    <button class="primary-button fusion-preview-button" data-action="preview-fusion" ${state.fusion.cardIds.length !== 3 || !state.fusion.retainedId || state.loading ? "disabled" : ""}>پیش‌نمایش Fusion</button></div>${bottomNav("shop")}${state.fusion.preview ? fusionConfirmDialog() : ""}</section>`;
}

function fusionConfirmDialog(): string {
  const preview = state.fusion.preview!;
  const retained = preview.cards.find((card) => card.card_id === preview.retained_card_id);
  const consumed = preview.cards.filter((card) => preview.consumed_card_ids.includes(card.card_id));
  return `<div class="sheet-backdrop" data-action="cancel-fusion"></div><aside class="fusion-confirm glass-panel" role="alertdialog" aria-modal="true" aria-label="تأیید نهایی Fusion"><p class="eyebrow">FINAL CHECK</p><h2>این عملیات قابل برگشت نیست</h2><div class="fusion-result-card"><span style="background-image:url('${escapeHtml(retained?.image_url)}')"></span><div><small>کارت باقی‌مانده</small><strong dir="auto">${escapeHtml(retained?.name)}</strong><b dir="ltr">${preview.target_rarity.toUpperCase()} · +${preview.xp} XP</b></div></div><p>کارت‌های مصرفی: ${consumed.map((card) => `<b dir="auto">${escapeHtml(card.name)}</b>`).join("، ")}</p><div><button class="secondary-button" data-action="cancel-fusion">بازبینی</button><button class="danger-button" data-action="execute-fusion" ${state.loading ? "disabled" : ""}>${state.loading ? "در حال Fusion…" : "تأیید و مصرف کارت‌ها"}</button></div></aside>`;
}

function lobbyTemplate(): string {
  const p = state.profile;
  const pending = state.profileStatus === "loading" && !p;
  const value = (amount?: number) => pending ? "…" : amount === undefined ? "—" : amount.toLocaleString("fa-IR");
  return `
    <section class="screen lobby-screen hub-screen">
      <header class="topbar">
        <button class="brand-mark" data-action="open-profile" aria-label="نمایش پروفایل">TB</button>
        <div class="resource-row" aria-label="منابع بازیکن">
          <span class="resource resource--heart"><small>جان</small><b dir="ltr">${p ? `${p.hearts}/${p.max_hearts}` : value()}</b></span>
          <span class="resource resource--coin"><small>سکه</small><b>${value(p?.coins)}</b></span>
          <span class="resource resource--cards"><small>کارت</small><b>${value(p?.counts?.cards)}</b></span>
          <span class="resource resource--decks"><small>دک</small><b>${value(p?.counts?.decks)}</b></span>
        </div>
      </header>
      ${profileStatusNotice()}
      <div class="hero-copy">
        <p class="eyebrow">TACTICAL CARD BATTLE</p>
        <h1>فرماندهی را<br><span>به دست بگیر</span></h1>
        <p>سه راند. چهار ویژگی. فقط یک تصمیم درست بین تو و پیروزی فاصله دارد.</p>
      </div>
      <div class="command-panel glass-panel">
        <div class="commander-row">
          <div><small>فرمانده</small><strong>${p?.first_name ?? "بازیکن"}</strong></div>
          <div class="tier-badge">${p?.current_tier ?? "ROOKIE"} · LV ${p?.level ?? 1}</div>
        </div>
        <div class="mode-actions">
          <button class="primary-button" data-action="enter-quick" ${state.loading ? "disabled" : ""}>
            <span>Quick با بازیکن واقعی</span><span class="live-dot" aria-hidden="true"></span>
          </button>
          <button class="secondary-button" data-action="enter-arena" ${state.loading ? "disabled" : ""}>تمرین Solo با ASO</button>
        </div>
        <p class="demo-note">Quick: مسابقه تصادفی یا دعوت دوست · انتخاب‌ها نهایی هستند</p>
      </div>
      ${bottomNav("game")}
    </section>`;
}

function quickMenuTemplate(): string {
  const invite = state.incomingInvite;
  return `
    <section class="screen quick-menu-screen">
      <header class="section-header"><button class="icon-button" data-action="home" aria-label="بازگشت">←</button><div><p class="eyebrow">QUICK MODE</p><h2>${invite ? "دعوت نبرد" : "حریفت را پیدا کن"}</h2></div></header>
      <div class="quick-hero glass-panel">
        <span class="quick-hero__mark">Q</span>
        <div><strong>${invite ? "یک بازیکن منتظر توست" : "یک نبرد، یک کارت، یک ویژگی"}</strong><p>${invite ? "با پذیرش دعوت مستقیم وارد انتخاب کارت می‌شوی." : "انتخاب کارت و حرکت اول نهایی است و قابل تغییر نیست."}</p></div>
      </div>
      ${invite ? `
        <button class="primary-button" data-action="accept-invite" ${state.loading ? "disabled" : ""}>پذیرش دعوت</button>
        <button class="secondary-button" data-action="dismiss-invite">رد کردن</button>
      ` : `
        <div class="quick-options">
          <button class="mode-card" data-action="quick-random" ${state.loading ? "disabled" : ""}><span class="mode-card__icon">⌁</span><div><strong>حریف تصادفی</strong><small>اتصال خودکار به یک بازیکن</small></div><i>←</i></button>
          <button class="mode-card" data-action="quick-invite" ${state.loading ? "disabled" : ""}><span class="mode-card__icon">↗</span><div><strong>دعوت با لینک</strong><small>لینک ۵ دقیقه‌ای برای دوستت</small></div><i>←</i></button>
        </div>
      `}
      <div class="rule-strip"><span>۵:۰۰</span><p>اگر کسی درخواست را نپذیرد، خودکار منقضی می‌شود.</p></div>
    </section>`;
}

function quickWaitTemplate(): string {
  const quick = state.quick;
  const expired = quick?.status === "expired";
  const cancelled = quick?.status === "cancelled";
  const seconds = Math.max(0, Math.ceil((new Date(quick?.expires_at || 0).getTime() - Date.now()) / 1000));
  const time = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  return `
    <section class="screen quick-wait-screen">
      <header class="section-header"><button class="icon-button" data-action="cancel-quick" aria-label="بازگشت">←</button><div><p class="eyebrow">MATCHMAKING</p><h2>${expired ? "زمان درخواست تمام شد" : cancelled ? "درخواست لغو شد" : "در جستجوی حریف"}</h2></div></header>
      <div class="radar ${expired || cancelled ? "is-stopped" : ""}"><i></i><i></i><span>VS</span></div>
      <div class="waiting-copy">
        <strong>${expired ? "درخواست منقضی شد" : cancelled ? "به پایگاه برگرد" : quick?.source === "invite_link" ? "منتظر پذیرش دعوت" : "در حال اتصال تصادفی"}</strong>
        <p>${quick?.message || (expired ? "برای ساخت درخواست جدید دوباره تلاش کن." : "این صفحه را باز نگه دار؛ به محض ورود حریف نبرد شروع می‌شود.")}</p>
      </div>
      <div class="wait-panel glass-panel">
        <div><small>مهلت باقی‌مانده</small><strong class="countdown">${time}</strong></div>
        ${quick?.invite_url && !expired && !cancelled ? `<button class="share-button" data-action="share-invite" data-url="${quick.invite_url}">اشتراک لینک دعوت</button>` : ""}
        ${expired || cancelled ? `<button class="primary-button" data-action="enter-quick">درخواست جدید</button>` : `<button class="secondary-button" data-action="cancel-quick">لغو درخواست</button>`}
      </div>
    </section>`;
}

function cardsTemplate(): string {
  if (state.playMode === "quick") {
    const arena = state.quick?.arena;
    return `
      <section class="screen cards-screen drag-card-screen">
        <header class="section-header drag-card-header">
          <button class="icon-button" data-action="back" aria-label="بازگشت">←</button>
          <div><p class="eyebrow">QUICK · DRAG TO PLAY</p><h2>${arena ? `${arena.emoji || ""} ${arena.name}` : "کارتت را وارد میدان کن"}</h2></div>
        </header>
        <div class="drag-guide" role="status" aria-live="polite">
          <span class="drag-guide__grip" aria-hidden="true"></span>
          <div><strong>${state.loading ? "در حال ثبت انتخاب…" : "کارت را بکش و وسط زمین رها کن"}</strong><small>${state.loading ? "انتخاب نهایی است و دیگر تغییر نمی‌کند." : `${state.cards.length} کارت · برای دیدن بقیه از فلش‌های کنار دست استفاده کن`}</small></div>
        </div>
      </section>`;
  }
  const cards = state.cards.map((card) => {
    const selected = state.selected?.card_id === card.card_id;
    return `<button class="card-choice rarity-${card.rarity} ${selected ? "is-selected" : ""}" data-action="select-card" data-id="${card.card_id}" aria-pressed="${selected}">
      <span class="card-choice__art" style="background-image:url('${card.image_url}')"></span>
      <span class="card-choice__shade"></span>
      <span class="card-choice__name">${card.name}</span>
      <span class="card-choice__score">${Math.round((card.power + card.speed + card.iq + card.popularity) / 4)}</span>
    </button>`;
  }).join("");
  return `
    <section class="screen cards-screen">
      <header class="section-header"><button class="icon-button" data-action="back" aria-label="بازگشت">←</button><div><p class="eyebrow">LOADOUT</p><h2>قهرمانت را انتخاب کن</h2></div></header>
      <div class="difficulty" role="group" aria-label="درجه سختی">
        ${(["easy", "medium", "hard"] as Difficulty[]).map((item) => `<button data-action="difficulty" data-value="${item}" class="difficulty__item ${state.difficulty === item ? "is-active" : ""}">${item === "easy" ? "آسان" : item === "medium" ? "تاکتیکی" : "بی‌رحم"}</button>`).join("")}
      </div>
      <div class="card-grid" aria-label="کارت‌های شما">${state.loading ? skeletons() : cards || `<p class="empty-state">کارتی برای نمایش پیدا نشد.</p>`}</div>
      <div class="selection-dock glass-panel ${state.selected ? "is-visible" : ""}">
        <div><small>انتخاب شما</small><strong>${state.selected?.name ?? "یک کارت انتخاب کن"}</strong></div>
        <button class="primary-button primary-button--compact" data-action="start" ${!state.selected || state.loading ? "disabled" : ""}>شروع نبرد</button>
      </div>
    </section>`;
}

function quickMatchTemplate(): string {
  const quick = state.quick;
  const arena = quick?.arena;
  const waitingForOpponent = (
    (quick?.phase === "card_selection" && quick.my_card_locked)
    || (quick?.phase === "ability_selection" && quick.my_ability_locked)
    || (quick?.phase === "stat_selection" && quick.my_stat_locked)
  );
  const phaseTitle = quick?.phase === "ability_selection" ? "توانایی تاکتیکی" : quick?.phase === "stat_selection" ? "ویژگی نهایی" : "انتخاب کارت";
  const modifiers = Object.entries(arena?.modifiers || {}).map(([key, value]) => `${labels[key as StatKey].title} ${Number(value) > 0 ? "+" : ""}${value}`).join(" · ");
  return `
    <section class="screen quick-match-screen">
      <header class="quick-match-hud glass-panel">
        <div><small>QUICK</small><strong>${phaseTitle}</strong></div>
        <div class="versus-chip"><span>تو</span><i>VS</i><span>حریف</span></div>
      </header>
      ${arena ? `<div class="arena-banner"><span>${arena.emoji || "◇"}</span><div><small>میدان</small><strong>${arena.name}</strong><p>${modifiers || "بدون تغییر ویژگی"}</p></div></div>` : ""}
      ${quick?.opponent_card ? `<div class="reveal-card glass-panel"><span class="reveal-card__art" style="background-image:url('${quick.opponent_card.image_url}')"></span><div><small>کارت حریف آشکار شد</small><strong>${quick.opponent_card.name}</strong></div></div>` : ""}
      <div class="decision-panel glass-panel">
        ${waitingForOpponent ? `
          <div class="choice-locked"><span>✓</span><strong>انتخابت ثبت و قفل شد</strong><p>منتظر تصمیم حریف هستیم…</p></div>
        ` : quick?.phase === "ability_selection" ? `
          <div class="decision-title"><small>یک بار مصرف</small><strong>Ability را انتخاب کن</strong></div>
          <div class="ability-list">
            ${(quick.abilities || []).map((ability) => `<button data-action="quick-ability" data-value="${ability.ability_key}"><div><strong>${ability.title}</strong><small>${ability.description}</small></div><span>×${ability.quantity}</span></button>`).join("")}
            <button data-action="quick-ability" data-value="skip"><div><strong>بدون Ability</strong><small>مستقیم به انتخاب ویژگی برو</small></div><span>←</span></button>
          </div>
        ` : quick?.phase === "stat_selection" ? `
          <div class="decision-title"><small>انتخاب نهایی و غیرقابل تغییر</small><strong>با کدام ویژگی حمله می‌کنی؟</strong></div>
          <div class="stat-grid quick-stat-grid">
            ${(Object.keys(labels) as StatKey[]).map((key) => {
              const enabled = (quick.allowed_stats || []).includes(key) && !state.loading;
              return `<button class="stat-button" data-action="quick-stat" data-value="${key}" ${enabled ? "" : "disabled"}><span>${labels[key].short}</span><strong>${quick.my_card?.[key] ?? "—"}</strong><small>${labels[key].title}</small></button>`;
            }).join("")}
          </div>
        ` : `<div class="choice-locked"><span>✓</span><strong>کارتت ثبت شد</strong><p>منتظر انتخاب کارت حریف…</p></div>`}
        ${state.loading ? `<div class="turn-progress"><span></span><p>در حال ثبت انتخاب…</p></div>` : ""}
      </div>
    </section>`;
}

function quickResultTemplate(): string {
  const quick = state.quick;
  const report = quick?.report;
  const tie = report?.is_tie;
  const won = !tie && report?.winner_id === quick?.user_id;
  const mine = quick && report?.breakdown?.[String(quick.user_id)];
  const opponent = quick?.opponent_id != null ? report?.breakdown?.[String(quick.opponent_id)] : undefined;
  return `
    <section class="screen result-screen quick-result-screen">
      <div class="result-emblem ${won ? "result-emblem--win" : "result-emblem--lose"}"><span>${tie ? "=" : won ? "W" : "L"}</span></div>
      <p class="eyebrow">QUICK COMPLETE</p>
      <h2>${tie ? "نبرد مساوی شد" : won ? "تصمیم تو برنده شد" : "حریف این نبرد را برد"}</h2>
      <p>${report?.forfeit ? "نتیجه به‌خاطر پایان مهلت انتخاب ثبت شد." : "انتخاب‌های نهایی هر دو بازیکن مقایسه شدند."}</p>
      <div class="reward-panel glass-panel"><div><small>ویژگی تو</small><strong>${mine ? labels[mine.selected_stat].short : "—"}</strong></div><div class="reward-list"><span><small>YOU</small><strong>${mine?.final_value ?? "—"}</strong></span><span><small>RIVAL</small><strong>${opponent?.final_value ?? "—"}</strong></span></div></div>
      <button class="primary-button" data-action="enter-quick">Quick دوباره</button>
      <button class="secondary-button" data-action="home">بازگشت به پایگاه</button>
    </section>`;
}

function battleTemplate(): string {
  const fight = state.fight;
  const round = state.lastRound;
  const available = round?.available_stats ?? fight?.available_stats ?? [];
  return `
    <section class="screen battle-screen">
      <header class="battle-hud glass-panel">
        <div><small>راند</small><strong>${round?.next_round && !round.game_over ? round.next_round : fight?.current_round ?? 1}<span>/3</span></strong></div>
        <div class="round-score" aria-label="امتیاز راند"><span class="score-player">${round?.player_rounds_won ?? 0}</span><i></i><span class="score-ai">${round?.ai_rounds_won ?? 0}</span></div>
        <div class="arena-name"><small>میدان</small><strong>${fight?.arena.name_fa ?? "—"}</strong></div>
      </header>
      <div class="opponent-callout"><span>ASO</span><p>${round?.aso_dialog ?? fight?.aso_dialog ?? "در حال ورود حریف..."}</p></div>
      <div class="versus-label">VS</div>
      <div class="stat-console glass-panel">
        <div class="console-title"><div><small>حرکت بعدی</small><strong>ویژگی حمله را انتخاب کن</strong></div><span>BOOST: ${fight ? labels[fight.arena.boost_stat].title : "—"}</span></div>
        <div class="stat-grid">
          ${(Object.keys(labels) as StatKey[]).map((key) => {
            const value = fight?.player_card[key] ?? 0;
            const enabled = available.includes(key) && !state.loading;
            return `<button class="stat-button ${fight?.arena.boost_stat === key ? "is-boosted" : ""}" data-action="stat" data-value="${key}" ${enabled ? "" : "disabled"}><span>${labels[key].short}</span><strong>${value}</strong><small>${labels[key].title}</small></button>`;
          }).join("")}
        </div>
        ${state.loading ? `<div class="turn-progress"><span></span><p>در حال تحلیل حرکت حریف...</p></div>` : ""}
      </div>
    </section>`;
}

function resultTemplate(): string {
  const result = state.lastRound?.final_result;
  const won = result?.winner === "player";
  const rewards = result?.rewards ?? {};
  return `
    <section class="screen result-screen">
      <div class="result-emblem ${won ? "result-emblem--win" : "result-emblem--lose"}"><span>${won ? "W" : "L"}</span></div>
      <p class="eyebrow">BATTLE COMPLETE</p>
      <h2>${won ? "میدان برای توست" : "این نبرد تمام شد"}</h2>
      <p>${result?.aso_dialog ?? "نتیجه نبرد ثبت شد."}</p>
      <div class="reward-panel glass-panel">
        <div><small>نتیجه</small><strong>${state.lastRound?.player_rounds_won ?? 0} — ${state.lastRound?.ai_rounds_won ?? 0}</strong></div>
        <div class="reward-list">${Object.entries(rewards).map(([key, value]) => `<span><small>${key.toUpperCase()}</small><strong>+${value}</strong></span>`).join("") || "<span>پاداش ثبت شد</span>"}</div>
      </div>
      <button class="primary-button" data-action="again">نبرد دوباره</button>
      <button class="secondary-button" data-action="home">بازگشت به پایگاه</button>
    </section>`;
}

function skeletons(): string {
  return Array.from({ length: 4 }, () => `<div class="card-skeleton"></div>`).join("");
}

function profileErrorMessage(error: unknown): string {
  if (!window.Telegram?.WebApp?.initData) {
    return "اطلاعات ورود تلگرام دریافت نشد. مینی‌اپ را از دکمه داخل ربات باز کن.";
  }
  if (error instanceof ApiError && error.code === "invalid_init_data") {
    return "ورود تلگرام منقضی یا نامعتبر است. مینی‌اپ را ببند و دوباره از ربات باز کن.";
  }
  return error instanceof Error ? error.message : "اطلاعات بازیکن دریافت نشد.";
}

async function refreshProfile(): Promise<void> {
  state.profileStatus = "loading";
  state.profileError = undefined;
  try {
    state.profile = await api.profile();
    state.profileStatus = "ready";
  } catch (error) {
    state.profileStatus = "error";
    state.profileError = profileErrorMessage(error);
    throw error;
  }
}

async function retryProfile(): Promise<void> {
  if (state.profileStatus === "loading") return;
  const pending = refreshProfile();
  render();
  try {
    await pending;
    haptic("success");
  } catch (error) {
    showToast(profileErrorMessage(error));
  } finally {
    render();
  }
}

async function openProfileHub(): Promise<void> {
  stopQuickPolling();
  state.screen = "profileHub";
  state.loading = true;
  scene.showIdle();
  render();
  try {
    await refreshProfile();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "پروفایل دریافت نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function loadCollection(page = state.collectionPage): Promise<void> {
  state.collectionPage = Math.max(1, page);
  state.loading = true;
  render();
  try {
    state.collection = await api.cardPage({
      page: state.collectionPage,
      limit: 20,
      rarity: state.collectionRarity,
      sort: state.collectionSort,
      query: state.collectionQuery,
    });
    state.collectionPage = state.collection.page;
  } catch (error) {
    showToast(error instanceof Error ? error.message : "کلکسیون دریافت نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function openCollection(): Promise<void> {
  stopQuickPolling();
  state.screen = "collection";
  state.detailCard = undefined;
  scene.showIdle();
  render();
  await loadCollection(1);
}

async function openCardDetail(cardId: string): Promise<void> {
  const localCard = state.collection?.cards.find((card) => card.card_id === cardId);
  state.detailCard = localCard;
  render();
  try {
    state.detailCard = await api.cardDetail(cardId);
    render();
  } catch (error) {
    state.detailCard = undefined;
    showToast(error instanceof Error ? error.message : "جزئیات کارت دریافت نشد");
    render();
  }
}

async function previewUpgrade(): Promise<void> {
  if (!state.detailCard || state.loading) return;
  state.loading = true;
  render();
  try {
    state.pendingUpgrade = await api.upgradePreview(state.detailCard.card_id);
  } catch (error) {
    showToast(error instanceof Error ? error.message : "پیش‌نمایش ارتقا دریافت نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function confirmUpgrade(): Promise<void> {
  const card = state.detailCard;
  const upgrade = state.pendingUpgrade;
  if (!card || !upgrade?.upgrade_key || state.loading) return;
  state.loading = true;
  render();
  try {
    const result = await api.upgradeCard(card.card_id, upgrade.upgrade_key);
    state.profile = { ...(state.profile || {} as ProfileData), ...result.profile };
    state.detailCard = await api.cardDetail(result.data.card.card_id);
    state.pendingUpgrade = undefined;
    await loadCollection(state.collectionPage);
    haptic("success");
    showToast(result.message);
  } catch (error) {
    showToast(error instanceof Error ? error.message : "ارتقای کارت انجام نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function openDecks(): Promise<void> {
  state.screen = "decks";
  state.detailCard = undefined;
  state.loading = true;
  render();
  try {
    const [decks, cards] = await Promise.all([api.decks(), state.cards.length ? Promise.resolve(state.cards) : api.cards()]);
    state.decks = decks;
    state.cards = cards;
  } catch (error) {
    showToast(error instanceof Error ? error.message : "دک‌ها دریافت نشدند");
  } finally {
    state.loading = false;
    render();
  }
}

function editDeck(deckId?: string): void {
  const deck = state.decks.find((item) => item.deck_id === deckId);
  state.deckEditor = deck ? { deckId: deck.deck_id, name: deck.deck_name, cardIds: deck.cards.map((card) => card.card_id) } : { name: "", cardIds: [] };
  render();
}

async function saveDeck(): Promise<void> {
  const editor = state.deckEditor;
  if (!editor || editor.cardIds.length !== 3 || state.loading) return;
  state.loading = true;
  render();
  try {
    const saved = editor.deckId
      ? await api.updateDeck(editor.deckId, editor.name.trim(), editor.cardIds)
      : await api.createDeck(editor.name.trim(), editor.cardIds);
    state.decks = editor.deckId ? state.decks.map((deck) => deck.deck_id === saved.deck_id ? saved : deck) : [saved, ...state.decks];
    state.deckEditor = undefined;
    await refreshProfile();
    haptic("success");
    showToast(editor.deckId ? "دک بروزرسانی شد" : "دک ساخته شد");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "ذخیره دک انجام نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function confirmDeleteDeck(): Promise<void> {
  const deckId = state.deleteDeckId;
  if (!deckId || state.loading) return;
  state.loading = true;
  render();
  try {
    await api.deleteDeck(deckId);
    state.decks = state.decks.filter((deck) => deck.deck_id !== deckId);
    state.deleteDeckId = undefined;
    await refreshProfile();
    showToast("دک حذف شد");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "حذف دک انجام نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function openProgress(): Promise<void> {
  state.screen = "progress"; state.loading = true; render();
  try { [state.claimStatus, state.missions] = await Promise.all([api.claimStatus(), api.missions()]); }
  catch (error) { showToast(error instanceof Error ? error.message : "پیشرفت دریافت نشد"); }
  finally { state.loading = false; render(); }
}

async function claimDaily(): Promise<void> {
  if (state.loading || !state.claimStatus?.can_claim) return;
  state.loading = true; render();
  try { const result = await api.claimDaily(); state.rewardCard = result.data.card; state.profile = { ...(state.profile || {} as ProfileData), ...result.profile }; state.claimStatus = await api.claimStatus(); haptic("success"); showToast(result.message); }
  catch (error) { showToast(error instanceof Error ? error.message : "دریافت کارت انجام نشد"); }
  finally { state.loading = false; render(); }
}

async function claimMission(missionId: string): Promise<void> {
  if (state.loading) return; state.loading = true; render();
  try { const result = await api.claimMission(missionId); state.rewardCard = result.data.card; state.missions = await api.missions(); await refreshProfile(); haptic("success"); showToast(result.message); }
  catch (error) { showToast(error instanceof Error ? error.message : "دریافت پاداش انجام نشد"); }
  finally { state.loading = false; render(); }
}

async function openSkins(cardId: string): Promise<void> {
  if (state.loading) return; state.loading = true; render();
  try { state.skinPanel = { cardId, data: await api.cardSkins(cardId) }; state.detailCard = undefined; }
  catch (error) { showToast(error instanceof Error ? error.message : "پوسته‌ها دریافت نشدند"); }
  finally { state.loading = false; render(); }
}

async function mutateSkin(cardId: string, skinId: string | null, purchase = false): Promise<void> {
  if (state.loading) return; state.loading = true; render();
  try { if (purchase && skinId) await api.purchaseSkin(cardId, skinId); await api.activateSkin(cardId, skinId); state.skinPanel = { cardId, data: await api.cardSkins(cardId) }; await refreshProfile(); haptic("success"); showToast(purchase ? "پوسته خریداری و فعال شد" : "ظاهر کارت تغییر کرد"); }
  catch (error) { showToast(error instanceof Error ? error.message : "تغییر پوسته انجام نشد"); }
  finally { state.loading = false; render(); }
}

async function openShop(): Promise<void> {
  state.screen = "shop"; state.loading = true; state.fusion.preview = undefined; render();
  try { state.cards = await api.cards(); }
  catch (error) { showToast(error instanceof Error ? error.message : "کارت‌ها دریافت نشدند"); }
  finally { state.loading = false; render(); }
}

async function previewFusion(): Promise<void> {
  if (state.loading || state.fusion.cardIds.length !== 3 || !state.fusion.retainedId) return;
  state.loading = true; render();
  try { state.fusion.preview = await api.fusionPreview(state.fusion.cardIds, state.fusion.retainedId, state.fusion.target); }
  catch (error) { showToast(error instanceof Error ? error.message : "پیش‌نمایش Fusion انجام نشد"); }
  finally { state.loading = false; render(); }
}

async function executeFusion(): Promise<void> {
  const fusion = state.fusion;
  if (state.loading || !fusion.retainedId || !fusion.preview) return;
  state.loading = true; render();
  try { const result = await api.executeFusion(fusion.cardIds, fusion.retainedId, fusion.target); state.rewardCard = result.data.card; state.profile = { ...(state.profile || {} as ProfileData), ...result.profile }; state.cards = await api.cards(); state.fusion = { target: fusion.target, cardIds: [] }; haptic("success"); showToast(result.message); }
  catch (error) { showToast(error instanceof Error ? error.message : "Fusion انجام نشد"); }
  finally { state.loading = false; render(); }
}

async function enterArena(): Promise<void> {
  state.playMode = "solo";
  state.screen = "cards";
  state.loading = true;
  render();
  try {
    state.cards = await api.cards();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "خطا در دریافت کارت‌ها");
  } finally {
    state.loading = false;
    render();
  }
}

async function loadCards(): Promise<void> {
  if (state.cards.length) return;
  state.cards = await api.cards();
}

function stopQuickPolling(): void {
  if (quickPollTimer !== undefined) window.clearTimeout(quickPollTimer);
  quickPollTimer = undefined;
}

function syncQuickScreen(): void {
  const quick = state.quick;
  if (!quick) return;
  if (quick.status === "expired" || quick.status === "cancelled" || quick.status === "waiting") {
    state.screen = "quickWait";
    scene.showIdle();
  } else if (quick.phase === "card_selection" && !quick.my_card_locked) {
    state.playMode = "quick";
    state.screen = "cards";
    scene.showCardHand(state.cards, quick.arena?.id);
  } else if (quick.phase === "completed") {
    state.screen = "quickResult";
    stopQuickPolling();
    const mine = quick.report?.breakdown?.[String(quick.user_id)];
    const opponent = quick.opponent_id ? quick.report?.breakdown?.[String(quick.opponent_id)] : undefined;
    if (quick.my_card && quick.opponent_card) {
      const outcome = quick.report?.is_tie ? "tie" : quick.report?.winner_id === quick.user_id ? "win" : "loss";
      scene.showQuickResult(quick.my_card, quick.opponent_card, {
        outcome,
        playerValue: mine?.final_value,
        opponentValue: opponent?.final_value,
      }, quick.arena?.id);
    }
  } else {
    state.screen = "quickMatch";
    if (quick.my_card) scene.showQuickDuel(quick.my_card, quick.opponent_card, quick.arena?.id);
  }
}

function scheduleQuickPoll(delay = 2200): void {
  stopQuickPolling();
  if (!state.quick || ["expired", "cancelled", "completed"].includes(state.quick.status)) return;
  quickPollTimer = window.setTimeout(() => void pollQuick(), delay);
}

async function pollQuick(): Promise<void> {
  if (!state.quick) return;
  try {
    state.quick = await api.quickStatus(state.quick.request_id);
    if (state.quick.phase === "card_selection" && !state.quick.my_card_locked) await loadCards();
    syncQuickScreen();
    render();
    scheduleQuickPoll();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "وضعیت مسابقه دریافت نشد");
    scheduleQuickPoll(4000);
  }
}

async function beginQuick(kind: "random" | "invite"): Promise<void> {
  state.loading = true;
  state.playMode = "quick";
  render();
  try {
    state.quick = kind === "random" ? await api.quickMatchmaking() : await api.createQuickInvite();
    state.selected = undefined;
    syncQuickScreen();
    render();
    scheduleQuickPoll(900);
  } catch (error) {
    showToast(error instanceof Error ? error.message : "ساخت درخواست ممکن نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function acceptInvite(): Promise<void> {
  if (!state.incomingInvite) return;
  state.loading = true;
  render();
  try {
    state.quick = await api.acceptQuickInvite(state.incomingInvite);
    state.playMode = "quick";
    state.incomingInvite = undefined;
    await loadCards();
    syncQuickScreen();
    scheduleQuickPoll();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "پذیرش دعوت ممکن نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function submitQuickCard(): Promise<void> {
  if (!state.quick || !state.selected || state.loading) return;
  state.loading = true;
  render();
  try {
    state.quick = await api.quickCard(state.quick.request_id, state.selected.card_id);
    syncQuickScreen();
    haptic("success");
    scheduleQuickPoll();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "کارت ثبت نشد");
    scene.resetCardHand();
  } finally {
    state.loading = false;
    render();
  }
}

async function submitQuickAbility(abilityKey: string): Promise<void> {
  if (!state.quick || state.loading) return;
  state.loading = true;
  render();
  try {
    state.quick = await api.quickAbility(state.quick.request_id, abilityKey);
    syncQuickScreen();
    scheduleQuickPoll();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "Ability ثبت نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function submitQuickStat(stat: StatKey): Promise<void> {
  if (!state.quick || state.loading) return;
  state.loading = true;
  render();
  try {
    state.quick = await api.quickStat(state.quick.request_id, stat);
    syncQuickScreen();
    haptic(state.quick.report?.winner_id === state.quick.user_id ? "success" : "medium");
    scheduleQuickPoll();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "ویژگی ثبت نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function cancelQuick(): Promise<void> {
  stopQuickPolling();
  if (state.quick?.status === "waiting") {
    try { state.quick = await api.cancelQuick(state.quick.request_id); } catch { /* It may already be accepted. */ }
  }
  state.quick = undefined;
  state.selected = undefined;
  state.screen = "lobby";
  render();
}

async function shareInvite(url: string): Promise<void> {
  try {
    const canShare = typeof navigator.share === "function";
    if (canShare) await navigator.share({ title: "دعوت به TelBattle", text: "بیا با هم Quick بازی کنیم", url });
    else await navigator.clipboard.writeText(url);
    showToast(canShare ? "دعوت آماده ارسال است" : "لینک دعوت کپی شد");
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") return;
    showToast("کپی لینک ممکن نشد");
  }
}

async function startFight(): Promise<void> {
  if (!state.selected) return;
  state.loading = true;
  render();
  try {
    state.fight = await api.start(state.selected.card_id, state.difficulty);
    state.lastRound = undefined;
    state.screen = "battle";
    scene.showBattle(state.fight);
    haptic("medium");
  } catch (error) {
    showToast(error instanceof Error ? error.message : "شروع نبرد ممکن نشد");
  } finally {
    state.loading = false;
    render();
  }
}

async function playStat(stat: StatKey): Promise<void> {
  if (!state.fight || state.loading) return;
  state.loading = true;
  render();
  try {
    const result = await api.round(state.fight.fight_id, stat);
    await scene.animateRound(result);
    state.lastRound = result;
    haptic(result.round_winner === "player" ? "success" : "medium");
    if (result.game_over) {
      scene.showVictory(result.final_result?.winner === "player");
      window.setTimeout(() => { state.screen = "result"; render(); }, 520);
    }
  } catch (error) {
    showToast(error instanceof Error ? error.message : "حرکت ثبت نشد");
  } finally {
    state.loading = false;
    render();
  }
}

ui.addEventListener("click", (event) => {
  const button = (event.target as HTMLElement).closest<HTMLElement>("[data-action]");
  if (!button || button.hasAttribute("disabled")) return;
  const action = button.dataset.action;
  haptic();
  if (action === "enter-arena") void enterArena();
  if (action === "retry-profile") void retryProfile();
  if (action === "open-profile") void openProfileHub();
  if (action === "open-collection") void openCollection();
  if (action === "card-detail") void openCardDetail(button.dataset.id || "");
  if (action === "close-card-detail") { state.detailCard = undefined; state.pendingUpgrade = undefined; render(); }
  if (action === "preview-upgrade") void previewUpgrade();
  if (action === "cancel-upgrade") { state.pendingUpgrade = undefined; render(); }
  if (action === "confirm-upgrade") void confirmUpgrade();
  if (action === "collection-page") void loadCollection(Number(button.dataset.page || 1));
  if (action === "hub-game") { state.screen = "lobby"; state.detailCard = undefined; scene.showIdle(); render(); }
  if (action === "hub-decks") void openDecks();
  if (action === "new-deck") editDeck();
  if (action === "edit-deck") editDeck(button.dataset.id);
  if (action === "close-deck-editor") { state.deckEditor = undefined; render(); }
  if (action === "toggle-deck-card" && state.deckEditor) {
    const cardId = button.dataset.id || "";
    const selected = state.deckEditor.cardIds.includes(cardId);
    state.deckEditor.cardIds = selected ? state.deckEditor.cardIds.filter((id) => id !== cardId) : state.deckEditor.cardIds.length < 3 ? [...state.deckEditor.cardIds, cardId] : state.deckEditor.cardIds;
    if (!selected && state.deckEditor.cardIds.length === 3 && !state.deckEditor.cardIds.includes(cardId)) showToast("هر دک فقط سه کارت دارد");
    render();
  }
  if (action === "save-deck") void saveDeck();
  if (action === "ask-delete-deck") { state.deleteDeckId = button.dataset.id; render(); }
  if (action === "cancel-delete-deck") { state.deleteDeckId = undefined; render(); }
  if (action === "confirm-delete-deck") void confirmDeleteDeck();
  if (action === "hub-progress") void openProgress();
  if (action === "claim-daily") void claimDaily();
  if (action === "claim-mission") void claimMission(button.dataset.id || "");
  if (action === "open-skins") void openSkins(button.dataset.id || "");
  if (action === "close-skins") { state.skinPanel = undefined; render(); }
  if (action === "purchase-skin") void mutateSkin(button.dataset.card || "", button.dataset.id || "", true);
  if (action === "activate-skin") void mutateSkin(button.dataset.card || "", button.dataset.id || "");
  if (action === "activate-default-skin") void mutateSkin(button.dataset.card || "", null);
  if (action === "hub-shop") void openShop();
  if (action === "fusion-target") { state.fusion = { target: button.dataset.value as "epic" | "legend", cardIds: [] }; render(); }
  if (action === "toggle-fusion-card") {
    const cardId = button.dataset.id || ""; const selected = state.fusion.cardIds.includes(cardId);
    state.fusion.cardIds = selected ? state.fusion.cardIds.filter((id) => id !== cardId) : state.fusion.cardIds.length < 3 ? [...state.fusion.cardIds, cardId] : state.fusion.cardIds;
    if (state.fusion.retainedId && !state.fusion.cardIds.includes(state.fusion.retainedId)) state.fusion.retainedId = undefined;
    render();
  }
  if (action === "retain-fusion-card") { state.fusion.retainedId = button.dataset.id; render(); }
  if (action === "preview-fusion") void previewFusion();
  if (action === "cancel-fusion") { state.fusion.preview = undefined; render(); }
  if (action === "execute-fusion") void executeFusion();
  if (action === "enter-quick") { stopQuickPolling(); state.quick = undefined; state.incomingInvite = undefined; state.screen = "quickMenu"; scene.showIdle(); render(); }
  if (action === "quick-random") void beginQuick("random");
  if (action === "quick-invite") void beginQuick("invite");
  if (action === "accept-invite") void acceptInvite();
  if (action === "dismiss-invite") { state.incomingInvite = undefined; state.screen = "lobby"; render(); }
  if (action === "cancel-quick") void cancelQuick();
  if (action === "share-invite") void shareInvite(button.dataset.url || "");
  if (action === "back") {
    if (state.playMode === "quick") void cancelQuick();
    else { state.screen = "lobby"; state.selected = undefined; scene.showIdle(); render(); }
  }
  if (action === "home") {
    stopQuickPolling();
    state.screen = "lobby";
    state.quick = undefined;
    state.selected = undefined;
    scene.showIdle();
    render();
    void refreshProfile().then(render).catch(() => undefined);
  }
  if (action === "difficulty") { state.difficulty = button.dataset.value as Difficulty; render(); }
  if (action === "select-card") { state.selected = state.cards.find((card) => card.card_id === button.dataset.id); render(); }
  if (action === "start") { if (state.playMode === "quick") void submitQuickCard(); else void startFight(); }
  if (action === "quick-ability") void submitQuickAbility(button.dataset.value || "skip");
  if (action === "quick-stat") void submitQuickStat(button.dataset.value as StatKey);
  if (action === "stat") void playStat(button.dataset.value as StatKey);
  if (action === "again") { state.screen = "cards"; state.lastRound = undefined; scene.showIdle(); render(); }
});

let collectionSearchTimer: number | undefined;
ui.addEventListener("input", (event) => {
  const input = event.target as HTMLInputElement;
  if (input.id === "deck-name" && state.deckEditor) { state.deckEditor.name = input.value; return; }
  if (input.id !== "collection-query") return;
  state.collectionQuery = input.value;
  if (collectionSearchTimer !== undefined) window.clearTimeout(collectionSearchTimer);
  collectionSearchTimer = window.setTimeout(() => void loadCollection(1), 320);
});

ui.addEventListener("change", (event) => {
  const select = event.target as HTMLSelectElement;
  if (select.id === "collection-rarity") {
    state.collectionRarity = select.value;
    void loadCollection(1);
  }
  if (select.id === "collection-sort") {
    state.collectionSort = select.value;
    void loadCollection(1);
  }
});

async function boot(): Promise<void> {
  const tg = window.Telegram?.WebApp;
  tg?.ready();
  tg?.expand();
  tg?.setHeaderColor?.("#07110e");
  tg?.setBackgroundColor?.("#07110e");
  state.incomingInvite = new URLSearchParams(location.search).get("invite") || undefined;
  if (state.incomingInvite) state.screen = "quickMenu";
  render();
  try {
    await refreshProfile();
  } catch {
    // The lobby remains usable and renders a visible retryable auth error.
  }
  render();
}

void boot();
