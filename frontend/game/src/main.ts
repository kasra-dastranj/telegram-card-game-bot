import Phaser from "phaser";
import "./styles.css";
import "./tabletop.css";
import { ApiError, api, type CardData, type CardPage, type ClaimStatus, type DeckData, type Difficulty, type FightData, type FusionPreview, type MissionData, type ProfileData, type QuickState, type RoundData, type SkinCollection, type StatKey, type ThreeRoundState, type UpgradePreview } from "./api";
import { BattleScene } from "./BattleScene";

type Screen = "splash" | "onboarding" | "lobby" | "profileHub" | "collection" | "decks" | "progress" | "shop" | "quickMenu" | "quickWait" | "threeMenu" | "threeWait" | "threeMatch" | "threeResult" | "cards" | "quickMatch" | "quickResult" | "battle" | "result";

const state: {
  screen: Screen;
  onboardingStep: number;
  bootProgress: number;
  bootLabel: string;
  profile?: ProfileData;
  profileStatus: "loading" | "ready" | "error";
  profileError?: string;
  cards: CardData[];
  featuredCards: CardData[];
  selected?: CardData;
  difficulty: Difficulty;
  fight?: FightData;
  lastRound?: RoundData;
  loading: boolean;
  playMode: "solo" | "quick" | "three";
  quick?: QuickState;
  incomingInvite?: string;
  three?: ThreeRoundState;
  incomingThreeInvite?: string;
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
  rewardAbility?: { key: string; title: string };
  skinPanel?: { cardId: string; data: SkinCollection };
  fusion: { target: "epic" | "legend"; cardIds: string[]; retainedId?: string; preview?: FusionPreview };
} = {
  screen: "splash",
  onboardingStep: 0,
  bootProgress: 12,
  bootLabel: "در حال بیدار کردن میدان…",
  profileStatus: "loading",
  cards: [],
  featuredCards: [],
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
let threePollTimer: number | undefined;
const onboardingStorageKey = "telbattle:onboarding:v1";
const threeStorageKey = "telbattle:three-round-request:v1";

const onboardingSlides = [
  {
    eyebrow: "فراخوان میدان",
    title: "فرمانده، نوبت توست",
    body: "سال‌هاست قهرمانان در کارت‌ها خاموش مانده‌اند. میدان دوباره بیدار شده و فقط یک فرمانده می‌تواند قدرت واقعی آن‌ها را آشکار کند.",
    mode: "mentor",
  },
  {
    eyebrow: "قانون اول",
    title: "هر کارت، یک قهرمان است",
    body: "قدرت، سرعت، هوش و محبوبیت چهار مسیر پیروزی‌اند. کارت مناسب را بشناس و ویژگی‌ای را انتخاب کن که حریف در آن نقطه‌ضعف دارد.",
    mode: "stats",
  },
  {
    eyebrow: "راهنمای نبرد",
    title: "سه انتخاب تا پیروزی",
    body: "وارد میدان شو، قهرمانت را انتخاب کن و بهترین ویژگی را در لحظه‌ی درست به کار ببر. هر تصمیم، نتیجه‌ی راند را عوض می‌کند.",
    mode: "guide",
  },
  {
    eyebrow: "آغاز فصل اول",
    title: "افسانه‌ات را بساز",
    body: "کارت جمع کن، دک بساز، مأموریت‌ها را کامل کن و در نبردهای واقعی رتبه‌ات را بالا ببر. میدان منتظر اولین حرکت توست.",
    mode: "ready",
  },
] as const;

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
  if (state.loading || (state.playMode === "quick" ? state.quick?.phase !== "card_selection" || state.quick.my_card_locked : state.playMode === "three" ? state.three?.phase !== "card_selection" || state.three.my_card_locked : true)) return;
  const card = state.cards.find((item) => item.card_id === cardId);
  if (!card) return;
  state.selected = card;
  if (state.playMode === "three") void submitThreeCard();
  else void submitQuickCard();
});

function render(): void {
  ui.dataset.screen = state.screen;
  document.body.dataset.appScreen = state.screen;
  if (state.screen === "splash") ui.innerHTML = splashTemplate();
  if (state.screen === "onboarding") ui.innerHTML = onboardingTemplate();
  if (state.screen === "lobby") ui.innerHTML = lobbyTemplate();
  if (state.screen === "profileHub") ui.innerHTML = profileHubTemplate();
  if (state.screen === "collection") ui.innerHTML = collectionTemplate();
  if (state.screen === "decks") ui.innerHTML = decksTemplate();
  if (state.screen === "progress") ui.innerHTML = progressTemplate();
  if (state.screen === "shop") ui.innerHTML = shopTemplate();
  if (state.screen === "quickMenu") ui.innerHTML = quickMenuTemplate();
  if (state.screen === "quickWait") ui.innerHTML = quickWaitTemplate();
  if (state.screen === "threeMenu") ui.innerHTML = threeMenuTemplate();
  if (state.screen === "threeWait") ui.innerHTML = threeWaitTemplate();
  if (state.screen === "threeMatch") ui.innerHTML = threeMatchTemplate();
  if (state.screen === "threeResult") ui.innerHTML = threeResultTemplate();
  if (state.screen === "cards") ui.innerHTML = cardsTemplate();
  if (state.screen === "quickMatch") ui.innerHTML = quickMatchTemplate();
  if (state.screen === "quickResult") ui.innerHTML = quickResultTemplate();
  if (state.screen === "battle") ui.innerHTML = battleTemplate();
  if (state.screen === "result") ui.innerHTML = resultTemplate();
}

function splashTemplate(): string {
  return `<section class="splash-screen" aria-label="در حال ورود به TelBattle Arena">
    <div class="splash-screen__art" aria-hidden="true"></div>
    <div class="splash-screen__veil" aria-hidden="true"></div>
    <header class="splash-brand">
      <span class="splash-brand__sigil" aria-hidden="true">
        <svg viewBox="0 0 48 48"><path d="M14 10h20l6 8-16 21L8 18l6-8Z"/><path d="m15 18 9-5 9 5-9 13-9-13Z"/></svg>
      </span>
      <span>یک میدان. هزار افسانه.</span>
    </header>
    <div class="splash-copy">
      <p class="splash-copy__chapter">CHAPTER 01 · AWAKENING</p>
      <h1><span>TelBattle</span> Arena</h1>
      <p>قهرمانت را انتخاب کن؛ سرنوشت میدان با اولین کارت تو آغاز می‌شود.</p>
    </div>
    <footer class="splash-loading" role="status" aria-live="polite">
      <div><span>${escapeHtml(state.bootLabel)}</span><b>${state.bootProgress.toLocaleString("fa-IR")}٪</b></div>
      <i style="--boot-progress:${state.bootProgress}%"><b></b></i>
    </footer>
  </section>`;
}

function onboardingVisual(mode: typeof onboardingSlides[number]["mode"]): string {
  if (mode === "mentor") {
    return `<div class="onboarding-mentor" aria-hidden="true"></div>`;
  }
  if (mode === "stats") {
    return `<div class="onboarding-stats" aria-hidden="true">
      <span class="stat-orb stat-orb--power"><b>POW</b><small>قدرت</small></span>
      <span class="stat-orb stat-orb--speed"><b>SPD</b><small>سرعت</small></span>
      <span class="stat-orb stat-orb--iq"><b>IQ</b><small>هوش</small></span>
      <span class="stat-orb stat-orb--pop"><b>POP</b><small>محبوبیت</small></span>
    </div>`;
  }
  if (mode === "guide") {
    return `<div class="onboarding-guide" aria-label="مراحل نبرد">
      <article><span>۱</span><div><b>ورود به میدان</b><small>حالت نبرد را انتخاب کن</small></div></article>
      <i aria-hidden="true"></i>
      <article><span>۲</span><div><b>انتخاب قهرمان</b><small>کارت مناسب زمین را بردار</small></div></article>
      <i aria-hidden="true"></i>
      <article><span>۳</span><div><b>ضربه‌ی نهایی</b><small>بهترین ویژگی را بازی کن</small></div></article>
    </div>`;
  }
  return `<div class="onboarding-ready" aria-hidden="true">
    <span class="onboarding-ready__card onboarding-ready__card--one"></span>
    <span class="onboarding-ready__card onboarding-ready__card--two"></span>
    <span class="onboarding-ready__card onboarding-ready__card--three"></span>
    <span class="onboarding-ready__sigil">T</span>
  </div>`;
}

function onboardingTemplate(): string {
  const slide = onboardingSlides[state.onboardingStep] || onboardingSlides[0];
  const isLast = state.onboardingStep === onboardingSlides.length - 1;
  return `<section class="onboarding-screen onboarding-screen--${slide.mode}" aria-label="معرفی TelBattle، مرحله ${state.onboardingStep + 1} از ${onboardingSlides.length}">
    <div class="onboarding-screen__art" aria-hidden="true"></div>
    <header class="onboarding-topbar">
      <span class="onboarding-logo"><b>T</b><small>TELBATTLE</small></span>
      <button data-action="onboarding-skip" aria-label="رد کردن معرفی">رد کردن</button>
    </header>
    <div class="onboarding-visual">${onboardingVisual(slide.mode)}</div>
    <div class="story-panel">
      ${slide.mode === "mentor" ? `<div class="story-speaker"><span>راهنمای شما</span><strong>استاد رادمان</strong></div>` : ""}
      <p class="eyebrow">${slide.eyebrow}</p>
      <h1>${slide.title}</h1>
      <p class="story-panel__body">${slide.body}</p>
      <div class="story-progress" aria-label="پیشرفت معرفی">${onboardingSlides.map((_, index) => `<i class="${index === state.onboardingStep ? "is-active" : index < state.onboardingStep ? "is-done" : ""}"></i>`).join("")}</div>
      <div class="story-actions">
        ${state.onboardingStep > 0 ? `<button class="story-back" data-action="onboarding-back" aria-label="مرحله قبل">←</button>` : `<span></span>`}
        <button class="primary-button story-next" data-action="onboarding-next">${isLast ? "ورود به میدان" : "ادامه"}<span class="button-arrow" aria-hidden="true">←</span></button>
      </div>
    </div>
  </section>`;
}

function onboardingSeen(): boolean {
  try { return localStorage.getItem(onboardingStorageKey) === "done"; }
  catch { return false; }
}

function finishOnboarding(): void {
  try { localStorage.setItem(onboardingStorageKey, "done"); } catch { /* Storage may be unavailable in private mode. */ }
  state.screen = "lobby";
  state.onboardingStep = 0;
  scene.showIdle();
  haptic("success");
  render();
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
    game: '<path d="m4 3 4 1 11 13-3 3L4 7V3Zm16 0-4 1-3 4M4 17l5-6M8 20l3-4M14 16l6 5M10 16l-6 5"/>',
    cards: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="m9 8 3-2 3 2-3 4-3-4Z"/>',
    decks: '<path d="m6 4 12 3-12 3-3-3 3-3Z"/><path d="m3 12 3 3 12-3M3 17l3 3 12-3"/>',
    progress: '<path d="M7 3h10v6a5 5 0 0 1-10 0V3Zm0 2H3v3a4 4 0 0 0 4 4m10-7h4v3a4 4 0 0 1-4 4M12 14v6m-5 1h10"/>',
    shop: '<path d="m14 3 7 7-3 3-7-7 3-3Zm-2 5-8 9a2 2 0 0 0 3 3l8-9M3 22h18"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[kind]}</svg>`;
}

function lobbyIcon(kind: "heart" | "coin" | "cards" | "decks" | "quick" | "solo" | "shield" | "arrow"): string {
  const paths = {
    heart: '<path d="M12 20.2 4.8 13a4.7 4.7 0 0 1 6.6-6.7l.6.6.6-.6a4.7 4.7 0 1 1 6.6 6.7L12 20.2Z"/>',
    coin: '<circle cx="12" cy="12" r="8.5"/><path d="M14.8 8.8c-.7-.7-1.6-1-2.8-1-1.5 0-2.7.7-2.7 1.8 0 2.9 5.5 1.2 5.5 4.2 0 1.3-1.2 2.2-2.9 2.2-1.3 0-2.4-.4-3.1-1.2M12 6.2v11.6"/>',
    cards: '<rect x="6" y="4" width="12" height="16" rx="2"/><path d="m9.5 10 2.5-2 2.5 2-2.5 3-2.5-3ZM4 7.5v9"/>',
    decks: '<path d="m5 6 7-3 7 3-7 3-7-3Z"/><path d="m5 11 7 3 7-3M5 16l7 3 7-3"/>',
    quick: '<path d="m13 2-7 11h5l-1 9 8-12h-5V2Z"/>',
    solo: '<path d="M12 3 5 6v5c0 4.6 2.9 8.1 7 10 4.1-1.9 7-5.4 7-10V6l-7-3Z"/><path d="m9 12 2 2 4-5"/>',
    shield: '<path d="M12 3 5 6v5c0 4.6 2.9 8.1 7 10 4.1-1.9 7-5.4 7-10V6l-7-3Z"/>',
    arrow: '<path d="M19 12H5m6-6-6 6 6 6"/>',
  };
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[kind]}</svg>`;
}

function bottomNav(active?: "game" | "cards" | "decks" | "progress" | "shop"): string {
  const items: Array<["game" | "cards" | "decks" | "progress" | "shop", string, string]> = [
    ["game", "بازی", "hub-game"],
    ["cards", "کارت‌ها", "open-collection"],
    ["decks", "دک‌ها", "hub-decks"],
    ["progress", "پیشرفت", "hub-progress"],
    ["shop", "کارگاه", "hub-shop"],
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
    <button class="hub-avatar" data-action="open-profile" aria-label="نمایش پروفایل ${escapeHtml(p?.first_name || "بازیکن")}">${escapeHtml((p?.first_name || "T").slice(0, 1))}<i aria-hidden="true"></i></button>
    <div class="hub-level"><span><span><small>فرمانده</small><strong>${escapeHtml(p?.first_name || "بازیکن")}</strong></span><span><b>LV ${p?.level ?? 1}</b><small>${escapeHtml(p?.current_tier ?? "Bronze")}</small></span></span><i><b style="width:${percent}%"></b></i></div>
    <div class="hub-resources">
      <span class="hub-resource hub-heart">${lobbyIcon("heart")}<span><small>جان</small><b dir="ltr">${p ? `${p.hearts}/${p.max_hearts}` : value()}</b></span></span>
      <span class="hub-resource hub-coin">${lobbyIcon("coin")}<span><small>سکه</small><b>${value(p?.coins)}</b></span></span>
      <span class="hub-resource hub-cards">${lobbyIcon("cards")}<span><small>کارت</small><b>${value(p?.counts?.cards)}</b></span></span>
      <span class="hub-resource hub-decks">${lobbyIcon("decks")}<span><small>دک</small><b>${value(p?.counts?.decks)}</b></span></span>
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
      <span class="collection-card__body"><small>${escapeHtml(card.rarity.toUpperCase())}</small><strong dir="auto">${escapeHtml(card.name)}</strong>${cardStatStrip(card)}</span>
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
            <label><span>کمیابی</span><select id="collection-rarity"><option value="all">همه کارت‌ها</option><option value="normal" ${state.collectionRarity === "normal" ? "selected" : ""}>معمولی</option><option value="rare" ${state.collectionRarity === "rare" ? "selected" : ""}>کمیاب</option><option value="epic" ${state.collectionRarity === "epic" ? "selected" : ""}>حماسی</option><option value="legend" ${state.collectionRarity === "legend" ? "selected" : ""}>افسانه‌ای</option></select></label>
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
      <p class="section-note">سه کارت انتخاب کن؛ ترکیبی بساز که نقطه‌ضعف‌های هم را پوشش بدهند.</p>
      <div class="deck-list">${state.loading ? skeletons() : decks || `<div class="empty-deck"><div class="empty-deck__cards" aria-hidden="true"><i></i><i>${lobbyIcon("decks")}</i><i></i></div><h2>ترکیب برنده‌ات را بساز</h2><p>هنوز دکی نساختی.</p><button class="secondary-button" data-action="new-deck">ساخت اولین دک</button></div>`}</div>
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
    ${state.rewardCard ? `<article class="reward-reveal glass-panel"><span style="background-image:url('${escapeHtml(state.rewardCard.image_url)}')"></span><div><small>پاداش تازه</small><h2 dir="auto">${escapeHtml(state.rewardCard.name)}</h2><b dir="ltr">${escapeHtml(state.rewardCard.rarity.toUpperCase())}</b>${state.rewardAbility ? `<p>🎁 Ability مصرفی Quick: ${escapeHtml(state.rewardAbility.title)} ×۱</p>` : ""}</div></article>` : ""}
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

function cardStatStrip(card: CardData): string {
  return `<span class="card-stat-strip">${(Object.keys(labels) as StatKey[]).map((key) => `<span><b>${card[key].toLocaleString("fa-IR")}</b><small>${labels[key].title}</small></span>`).join("")}</span>`;
}

function lobbyTemplate(): string {
  const p = state.profile;
  const featured = state.featuredCards.length ? state.featuredCards : [undefined, undefined, undefined];
  const pending = state.profileStatus === "loading" && !p;
  const value = (amount?: number) => pending ? "…" : amount === undefined ? "—" : amount.toLocaleString("fa-IR");
  const firstName = escapeHtml(p?.first_name || "بازیکن");
  const initial = escapeHtml((p?.first_name || "T").slice(0, 1));
  return `
    <section class="screen lobby-screen hub-screen">
      <header class="lobby-command-bar glass-panel">
        <button class="lobby-identity" data-action="open-profile" aria-label="نمایش پروفایل ${firstName}">
          <span class="lobby-identity__avatar">${initial}<i aria-hidden="true"></i></span>
          <span class="lobby-identity__copy"><small>فرمانده</small><strong>${firstName}</strong></span>
          <span class="lobby-identity__level" dir="ltr">LV ${p?.level ?? 1}</span>
        </button>
        <div class="lobby-resource-grid" aria-label="منابع بازیکن">
          <span class="lobby-resource lobby-resource--heart">${lobbyIcon("heart")}<span><small>جان</small><b dir="ltr">${p ? `${p.hearts}/${p.max_hearts}` : value()}</b></span></span>
          <span class="lobby-resource lobby-resource--coin">${lobbyIcon("coin")}<span><small>سکه</small><b>${value(p?.coins)}</b></span></span>
          <span class="lobby-resource lobby-resource--cards">${lobbyIcon("cards")}<span><small>کارت</small><b>${value(p?.counts?.cards)}</b></span></span>
          <span class="lobby-resource lobby-resource--decks">${lobbyIcon("decks")}<span><small>دک</small><b>${value(p?.counts?.decks)}</b></span></span>
        </div>
      </header>
      ${profileStatusNotice()}
      <div class="lobby-table">
        <header class="table-heading"><span class="table-heading__line"></span><span dir="ltr">TELBATTLE <b>ARENA</b></span><span class="table-heading__line"></span></header>
        <div class="table-copy"><p>کلکسیون تو. سبک نبرد تو.</p><h1>با کدام کارت وارد می‌شوی؟</h1></div>
        <button class="featured-hand" style="--card-count:${featured.length}" data-action="open-collection" aria-label="دیدن کلکسیون کارت‌ها">
          <span class="table-orbit" aria-hidden="true"></span>
          ${featured.map((card, index) => card ? `<span class="featured-card rarity-${escapeHtml(card.rarity)}" style="--card-index:${index}"><span class="featured-card__art" style="background-image:url('${escapeHtml(card.image_url)}')"></span><span class="featured-card__rarity">${escapeHtml(card.rarity.toUpperCase())}</span><span class="featured-card__name" dir="auto">${escapeHtml(card.name)}</span>${cardStatStrip(card)}</span>` : `<span class="featured-card featured-card--back" style="--card-index:${index}" aria-hidden="true"><span>${lobbyIcon("cards")}</span><b dir="ltr">TB</b></span>`).join("")}
        </button>
        <button class="collection-link" data-action="open-collection">${state.featuredCards.length ? "مشاهده کلکسیون" : "کارت‌هایت را کشف کن"} ${lobbyIcon("arrow")}</button>
      </div>
      <div class="battle-console">
        <div class="battle-mode-list">
          <button class="battle-mode battle-mode--quick" data-action="enter-quick" ${state.loading ? "disabled" : ""}>
            <span class="battle-mode__icon">${lobbyIcon("quick")}</span>
            <span class="battle-mode__copy"><strong>ورود به نبرد</strong><small>حریف واقعی · یک راند · یک انتخاب</small></span>
            <span class="battle-mode__meta"><em>${lobbyIcon("arrow")}</em></span>
          </button>
          <button class="battle-mode battle-mode--solo" data-action="enter-three" ${state.loading ? "disabled" : ""}>
            <span class="battle-mode__icon">${lobbyIcon("solo")}</span>
            <span class="battle-mode__copy"><strong>نبرد سه‌راندی</strong><small>حریف واقعی یا تمرین با ASO</small></span>
            <span class="battle-mode__meta"><em>${lobbyIcon("arrow")}</em></span>
          </button>
        </div>
      </div>
      <button class="lobby-reward" data-action="hub-progress"><span class="lobby-reward__icon">${lobbyIcon("cards")}</span><span><strong>پاداش روزانه</strong><small>${p?.claim?.can_claim ? "کارت تازه‌ات منتظر توست" : p?.claim ? "مأموریت‌ها و زمان پاداش بعدی" : "پاداش‌ها و مأموریت‌های کارت"}</small></span>${lobbyIcon("arrow")}</button>
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

function threeMenuTemplate(): string {
  const invite = state.incomingThreeInvite;
  return `<section class="screen quick-menu-screen">
    <header class="section-header"><button class="icon-button" data-action="home" aria-label="بازگشت">←</button><div><p class="eyebrow">THREE ROUNDS</p><h2>${invite ? "دعوت نبرد سه‌راندی" : "نبرد سه‌راندی"}</h2></div></header>
    <div class="quick-hero glass-panel"><span class="quick-hero__mark">3</span><div><strong>یک کارت، سه راند</strong><p>در هر راند یک ویژگی تازه انتخاب کن. زمین در تمام نبرد ثابت است؛ اولین نفر با دو برد پیروز می‌شود.</p></div></div>
    ${invite ? `<button class="primary-button" data-action="accept-three" ${state.loading ? "disabled" : ""}>پذیرش دعوت</button><button class="secondary-button" data-action="dismiss-three">رد کردن</button>` : `<div class="quick-options">
      <button class="mode-card" data-action="three-random" ${state.loading ? "disabled" : ""}><span class="mode-card__icon">⌁</span><div><strong>حریف تصادفی واقعی</strong><small>اتصال خودکار به بازیکن دیگر</small></div><i>←</i></button>
      <button class="mode-card" data-action="three-invite" ${state.loading ? "disabled" : ""}><span class="mode-card__icon">↗</span><div><strong>دعوت دوست با لینک</strong><small>لینک دعوت پنج دقیقه‌ای</small></div><i>←</i></button>
      <button class="mode-card" data-action="enter-arena"><span class="mode-card__icon">✦</span><div><strong>تمرین با ASO</strong><small>نبرد تمرینی سه‌راندی</small></div><i>←</i></button>
    </div>`}
  </section>`;
}

function threeWaitTemplate(): string {
  const match = state.three;
  const closed = match?.status === "expired" || match?.status === "cancelled";
  const seconds = Math.max(0, Math.ceil((new Date(match?.expires_at || 0).getTime() - Date.now()) / 1000));
  return `<section class="screen quick-wait-screen">
    <header class="section-header"><button class="icon-button" data-action="cancel-three" aria-label="بازگشت">←</button><div><p class="eyebrow">THREE ROUNDS</p><h2>${closed ? "درخواست پایان یافت" : "در جستجوی حریف"}</h2></div></header>
    <div class="radar ${closed ? "is-stopped" : ""}"><i></i><i></i><span>VS</span></div>
    <div class="waiting-copy"><strong>${closed ? "حریف پیدا نشد" : match?.source === "invite_link" ? "منتظر پذیرش دوستت هستیم" : "در حال اتصال تصادفی"}</strong><p>پس از ورود حریف، کارت خود را انتخاب می‌کنی.</p></div>
    <div class="wait-panel glass-panel"><div><small>مهلت باقی‌مانده</small><strong class="countdown">${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}</strong></div>
    ${match?.invite_url && !closed ? `<button class="share-button" data-action="share-three" data-url="${escapeHtml(match.invite_url)}">اشتراک لینک دعوت</button>` : ""}
    <button class="secondary-button" data-action="cancel-three">${closed ? "بازگشت" : "لغو درخواست"}</button></div>
  </section>`;
}

function threeMatchTemplate(): string {
  const match = state.three;
  const mine = match?.rounds_won?.[String(match.user_id)] ?? 0;
  const rival = match?.rounds_won?.[String(match.opponent_id)] ?? 0;
  const last = match?.last_round;
  const myLast = last?.values[String(match?.user_id)];
  const rivalLast = last?.values[String(match?.opponent_id)];
  return `<section class="screen quick-match-screen">
    <header class="quick-match-hud glass-panel"><div><small>راند ${match?.round ?? 1} از ۳</small><strong>${match?.arena?.emoji ?? "◇"} ${escapeHtml(match?.arena?.name_fa ?? "میدان")}</strong></div><div class="versus-chip"><span>${mine}</span><i>VS</i><span>${rival}</span></div></header>
    <div class="arena-banner"><span>${match?.arena?.emoji ?? "◇"}</span><div><small>ویژگی زمین</small><strong>${match?.arena?.boost_stat ? labels[match.arena.boost_stat].title : "—"}</strong><p>تقویت فقط برای کارت سازگار اعمال می‌شود. زمین هر سه راند ثابت است.</p></div></div>
    ${match?.opponent_card ? `<div class="reveal-card glass-panel"><span class="reveal-card__art" style="background-image:url('${escapeHtml(match.opponent_card.image_url)}')"></span><div><small>کارت حریف</small><strong>${escapeHtml(match.opponent_card.name)}</strong></div></div>` : ""}
    ${last ? `<div class="glass-panel" style="padding:12px;margin:10px 0"><strong>راند ${last.round}: ${last.winner_id === null ? "مساوی" : last.winner_id === match?.user_id ? "برد تو" : "برد حریف"}</strong><p>${myLast ? `${labels[myLast.stat].title} ${myLast.base}${myLast.boost ? ` + ${myLast.boost}` : ""} = ${myLast.total}` : "—"} · ${rivalLast ? `${labels[rivalLast.stat].title} ${rivalLast.base}${rivalLast.boost ? ` + ${rivalLast.boost}` : ""} = ${rivalLast.total}` : "—"}</p></div>` : ""}
    <div class="decision-panel glass-panel">${match?.phase === "card_selection" || match?.my_stat_locked ? `<div class="choice-locked"><span>✓</span><strong>انتخابت ثبت شد</strong><p>منتظر تصمیم حریف هستیم…</p></div>` : `<div class="decision-title"><small>هر ویژگی فقط یک بار</small><strong>ویژگی راند ${match?.round ?? 1} را انتخاب کن</strong></div><div class="stat-grid quick-stat-grid">${(Object.keys(labels) as StatKey[]).map((key) => `<button class="stat-button ${(match?.my_boosts?.[key] ?? 0) > 0 ? "is-boosted" : ""}" data-action="three-stat" data-value="${key}" ${(match?.available_stats || []).includes(key) && !state.loading ? "" : "disabled"}><span>${labels[key].short}</span><strong>${match?.my_values?.[key] ?? "—"}</strong><small>${labels[key].title}${match?.my_boosts?.[key] ? ` +${match.my_boosts[key]} زمین` : ""}</small></button>`).join("")}</div>`}</div>
  </section>`;
}

function threeResultTemplate(): string {
  const match = state.three;
  const report = match?.report;
  const tie = report?.is_tie;
  const won = report?.winner_id === match?.user_id;
  const mine = report?.rounds_won?.[String(match?.user_id)] ?? 0;
  const rival = report?.rounds_won?.[String(match?.opponent_id)] ?? 0;
  return `<section class="screen result-screen quick-result-screen">
    <div class="result-emblem ${won ? "result-emblem--win" : "result-emblem--lose"}"><span>${tie ? "=" : won ? "W" : "L"}</span></div>
    <p class="eyebrow">THREE ROUNDS COMPLETE</p><h2>${tie ? "نبرد مساوی شد" : won ? "تو برنده شدی" : "حریف برنده شد"}</h2>
    <p>${report?.forfeit ? "نبرد به‌خاطر پایان مهلت انتخاب تمام شد." : `${report?.rounds.length ?? 0} راند در ${escapeHtml(match?.arena?.name_fa ?? "میدان")} انجام شد.`}</p>
    <div class="reward-panel glass-panel"><div><small>برد راندها</small><strong>${mine} — ${rival}</strong></div></div>
    ${(report?.rounds || []).map((round) => { const a = round.values[String(match?.user_id)]; const b = round.values[String(match?.opponent_id)]; return `<div class="glass-panel" style="padding:12px;margin-bottom:10px"><strong>راند ${round.round}: ${round.winner_id === null ? "مساوی" : round.winner_id === match?.user_id ? "برد تو" : "برد حریف"}</strong><p>تو: ${a ? `${labels[a.stat].title} ${a.base} + ${a.boost} = ${a.total}` : "—"} · حریف: ${b ? `${labels[b.stat].title} ${b.base} + ${b.boost} = ${b.total}` : "—"}</p></div>`; }).join("")}
    <button class="primary-button" data-action="enter-three">نبرد سه‌راندی دوباره</button><button class="secondary-button" data-action="home">بازگشت به پایگاه</button>
  </section>`;
}

function cardsTemplate(): string {
  if (state.playMode === "quick" || state.playMode === "three") {
    const arena = state.playMode === "quick" ? state.quick?.arena : state.three?.arena;
    const arenaName = arena && ("name" in arena ? arena.name : arena.name_fa);
    return `
      <section class="screen cards-screen drag-card-screen">
        <header class="section-header drag-card-header">
          <button class="icon-button" data-action="back" aria-label="بازگشت">←</button>
          <div><p class="eyebrow">${state.playMode === "three" ? "THREE ROUNDS" : "QUICK"} · DRAG TO PLAY</p><h2>${arena ? `${arena.emoji || ""} ${arenaName}` : "کارتت را وارد میدان کن"}</h2></div>
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
      <span class="card-choice__name" dir="auto">${escapeHtml(card.name)}</span>
      <span class="card-choice__rarity">${escapeHtml(card.rarity.toUpperCase())}</span>
      ${cardStatStrip(card)}
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
  const cardTypeLabels: Record<StatKey, string> = { power: "قدرتی", speed: "سرعتی", iq: "هوشی", popularity: "محبوبیتی" };
  const arenaEffects = (arena?.effects || []).map((effect) => `کارت‌های ${cardTypeLabels[effect.card_type]}: ${labels[effect.stat].title} <bdi dir="ltr">${effect.delta > 0 ? "+" : ""}${effect.delta}</bdi>`).join(" · ");
  return `
    <section class="screen quick-match-screen">
      <header class="quick-match-hud glass-panel">
        <div><small>QUICK</small><strong>${phaseTitle}</strong></div>
        <div class="versus-chip"><span>تو</span><i>VS</i><span>حریف</span></div>
      </header>
      ${arena ? `<div class="arena-banner"><span>${arena.emoji || "◇"}</span><div><small>میدان</small><strong>${arena.name}</strong><p>${arenaEffects || "بدون تغییر عددی برای نوع کارت‌ها"}</p></div></div>` : ""}
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
          ${quick.scoring_rule === "sum_selected_stats_v1" ? "<p>امتیاز هر کارت از جمع ویژگی انتخابی تو و حریف به دست می‌آید؛ عدد هر دکمه فقط سهم آن ویژگی است.</p>" : ""}
          <div class="stat-grid quick-stat-grid">
            ${(Object.keys(labels) as StatKey[]).map((key) => {
              const enabled = (quick.allowed_stats || []).includes(key) && !state.loading;
              return `<button class="stat-button" data-action="quick-stat" data-value="${key}" ${enabled ? "" : "disabled"}><span>${labels[key].short}</span><strong>${quick.my_final_values?.[key] ?? quick.my_card?.[key] ?? "—"}</strong><small>${labels[key].title}</small></button>`;
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
  const calculation = mine?.scored_stats && opponent?.scored_stats
    ? `<details class="glass-panel" style="padding: 12px; margin-bottom: 16px;">
        <summary>محاسبهٔ امتیاز Quick</summary>
        <p>ویژگی‌های انتخاب‌شده برای هر دو کارت جمع می‌شوند. اثر زمین، Passive و Ability پیش از جمع اعمال شده است.</p>
        <p>کارت تو: ${mine.scored_stats.map((stat, index) => `${labels[stat].title} ${mine.final_components?.[index] ?? "—"}`).join(" + ")} = ${mine.final_value}</p>
        <p>کارت حریف: ${opponent.scored_stats.map((stat, index) => `${labels[stat].title} ${opponent.final_components?.[index] ?? "—"}`).join(" + ")} = ${opponent.final_value}</p>
      </details>`
    : "";
  return `
    <section class="screen result-screen quick-result-screen">
      <div class="result-emblem ${won ? "result-emblem--win" : "result-emblem--lose"}"><span>${tie ? "=" : won ? "W" : "L"}</span></div>
      <p class="eyebrow">QUICK COMPLETE</p>
      <h2>${tie ? "نبرد مساوی شد" : won ? "تصمیم تو برنده شد" : "حریف این نبرد را برد"}</h2>
      <p>${report?.forfeit ? "نتیجه به‌خاطر پایان مهلت انتخاب ثبت شد." : mine?.scored_stats ? "امتیاز هر کارت از جمع ویژگی انتخابی دو بازیکن به دست آمد. برای توضیح بیشتر، محاسبهٔ امتیاز را باز کن." : "ویژگی انتخابی هر بازیکن مقایسه شد."}</p>
      <div class="reward-panel glass-panel"><div><small>امتیاز Quick</small><strong>${mine?.scored_stats ? "جمع دو ویژگی" : mine ? labels[mine.selected_stat].short : "—"}</strong></div><div class="reward-list"><span><small>YOU</small><strong>${mine?.final_value ?? "—"}</strong></span><span><small>RIVAL</small><strong>${opponent?.final_value ?? "—"}</strong></span></div></div>
      ${calculation}
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
        <div class="console-title"><div><small>حرکت بعدی</small><strong>ویژگی حمله را انتخاب کن</strong></div><span>تقویت زمین: ${fight ? labels[fight.arena.boost_stat].title : "—"}</span></div>
        <div class="stat-grid">
          ${(Object.keys(labels) as StatKey[]).map((key) => {
            const value = fight?.player_card[key] ?? 0;
            const enabled = available.includes(key) && !state.loading && !round?.game_over;
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
    refreshFeaturedCards();
  } catch (error) {
    state.profileStatus = "error";
    state.profileError = profileErrorMessage(error);
    throw error;
  }
}

let featuredRequest = 0;
function refreshFeaturedCards(): void {
  const request = ++featuredRequest;
  // Optional artwork must never block authentication, startup, or navigation.
  void api.cardPage({ limit: 3, sort: "rarity" }).then((page) => {
    if (request !== featuredRequest) return;
    state.featuredCards = page.cards.slice(0, 3);
    if (state.screen === "lobby") render();
  }).catch(() => undefined);
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
  try { const result = await api.claimDaily(); state.rewardCard = result.data.card; state.rewardAbility = result.data.ability; state.profile = { ...(state.profile || {} as ProfileData), ...result.profile }; state.claimStatus = await api.claimStatus(); haptic("success"); showToast(result.message); }
  catch (error) { showToast(error instanceof Error ? error.message : "دریافت کارت انجام نشد"); }
  finally { state.loading = false; render(); }
}

async function claimMission(missionId: string): Promise<void> {
  if (state.loading) return; state.loading = true; render();
  try { const result = await api.claimMission(missionId); state.rewardCard = result.data.card; state.rewardAbility = undefined; state.missions = await api.missions(); await refreshProfile(); haptic("success"); showToast(result.message); }
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
  try { const result = await api.executeFusion(fusion.cardIds, fusion.retainedId, fusion.target); state.rewardCard = result.data.card; state.rewardAbility = undefined; state.profile = { ...(state.profile || {} as ProfileData), ...result.profile }; state.cards = await api.cards(); state.fusion = { target: fusion.target, cardIds: [] }; haptic("success"); showToast(result.message); }
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
      }, quick.arena);
    }
  } else {
    state.screen = "quickMatch";
    if (quick.my_card) scene.showQuickDuel(quick.my_card, quick.opponent_card, quick.arena);
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

function stopThreePolling(): void {
  if (threePollTimer !== undefined) window.clearTimeout(threePollTimer);
  threePollTimer = undefined;
}

function rememberThree(): void {
  try {
    if (state.three && !["expired", "cancelled", "completed"].includes(state.three.status)) localStorage.setItem(threeStorageKey, state.three.request_id);
    else localStorage.removeItem(threeStorageKey);
  } catch { /* Storage is optional. */ }
}

function syncThreeScreen(): void {
  const match = state.three;
  if (!match) return;
  rememberThree();
  if (["waiting", "expired", "cancelled"].includes(match.status)) {
    state.screen = "threeWait";
    scene.showIdle();
  } else if (match.phase === "card_selection" && !match.my_card_locked) {
    state.playMode = "three";
    state.screen = "cards";
    scene.showCardHand(state.cards, match.arena?.arena_id);
  } else if (match.phase === "completed") {
    state.screen = "threeResult";
    stopThreePolling();
    if (match.my_card && match.opponent_card) {
      const last = match.last_round;
      scene.showQuickResult(match.my_card, match.opponent_card, {
        outcome: match.report?.is_tie ? "tie" : match.report?.winner_id === match.user_id ? "win" : "loss",
        playerValue: last?.values[String(match.user_id)]?.total,
        opponentValue: last?.values[String(match.opponent_id)]?.total,
      }, { arena_id: match.arena?.arena_id, background_url: match.arena?.background_url });
    }
  } else {
    state.screen = "threeMatch";
    if (match.my_card) scene.showQuickDuel(match.my_card, match.opponent_card || undefined, { arena_id: match.arena?.arena_id, background_url: match.arena?.background_url });
  }
}

function scheduleThreePoll(delay = 2200): void {
  stopThreePolling();
  if (!state.three || ["expired", "cancelled", "completed"].includes(state.three.status)) return;
  threePollTimer = window.setTimeout(() => void pollThree(), delay);
}

async function pollThree(): Promise<void> {
  const requestId = state.three?.request_id;
  if (!requestId) return;
  try {
    const updated = await api.threeStatus(requestId);
    if (state.three?.request_id !== requestId) return;
    state.three = updated;
    if (updated.phase === "card_selection" && !updated.my_card_locked) await loadCards();
    syncThreeScreen();
    render();
    scheduleThreePoll();
  } catch (error) {
    showToast(error instanceof Error ? error.message : "وضعیت نبرد دریافت نشد");
    scheduleThreePoll(4000);
  }
}

async function beginThree(kind: "random" | "invite"): Promise<void> {
  state.loading = true; state.playMode = "three"; render();
  try {
    state.three = kind === "random" ? await api.threeMatchmaking() : await api.createThreeInvite();
    state.selected = undefined;
    if (state.three.phase === "card_selection") await loadCards();
    syncThreeScreen(); scheduleThreePoll(900);
  } catch (error) { showToast(error instanceof Error ? error.message : "ساخت درخواست ممکن نشد"); }
  finally { state.loading = false; render(); }
}

async function acceptThree(): Promise<void> {
  if (!state.incomingThreeInvite) return;
  state.loading = true; render();
  try {
    state.three = await api.acceptThreeInvite(state.incomingThreeInvite);
    state.incomingThreeInvite = undefined; state.playMode = "three";
    await loadCards(); syncThreeScreen(); scheduleThreePoll();
  } catch (error) { showToast(error instanceof Error ? error.message : "پذیرش دعوت ممکن نشد"); }
  finally { state.loading = false; render(); }
}

async function submitThreeCard(): Promise<void> {
  if (!state.three || !state.selected || state.loading) return;
  state.loading = true; render();
  try {
    state.three = await api.threeCard(state.three.request_id, state.selected.card_id);
    syncThreeScreen(); scheduleThreePoll(); haptic("success");
  } catch (error) { showToast(error instanceof Error ? error.message : "کارت ثبت نشد"); scene.resetCardHand(); }
  finally { state.loading = false; render(); }
}

async function submitThreeStat(stat: StatKey): Promise<void> {
  if (!state.three || state.loading) return;
  state.loading = true; render();
  try {
    state.three = await api.threeStat(state.three.request_id, stat);
    syncThreeScreen(); scheduleThreePoll(); haptic("medium");
  } catch (error) { showToast(error instanceof Error ? error.message : "ویژگی ثبت نشد"); }
  finally { state.loading = false; render(); }
}

async function cancelThree(): Promise<void> {
  stopThreePolling();
  if (state.three?.status === "waiting") {
    try { state.three = await api.cancelThree(state.three.request_id); }
    catch {
      try { state.three = await api.threeStatus(state.three.request_id); }
      catch { /* An expired request will be cleared below. */ }
    }
  }
  if (state.three?.status === "active" || state.three?.status === "accepted") rememberThree();
  else { state.three = undefined; rememberThree(); }
  state.selected = undefined;
  state.screen = "lobby"; scene.showIdle(); render();
}

async function openThreeMenu(): Promise<void> {
  stopThreePolling();
  state.incomingThreeInvite = undefined;
  let pending: string | null = null;
  try { pending = localStorage.getItem(threeStorageKey); } catch { /* Optional storage. */ }
  if (pending) {
    try {
      state.three = await api.threeStatus(pending);
      if (state.three.phase === "card_selection" && !state.three.my_card_locked) await loadCards();
      if (!["expired", "cancelled", "completed"].includes(state.three.status)) {
        syncThreeScreen(); render(); scheduleThreePoll(); return;
      }
    } catch { /* An old request may no longer exist. */ }
    try { localStorage.removeItem(threeStorageKey); } catch { /* Optional storage. */ }
  }
  state.three = undefined; state.playMode = "three"; state.screen = "threeMenu";
  scene.showIdle(); render();
}

async function shareInvite(url: string): Promise<void> {
  try {
    const canShare = typeof navigator.share === "function";
    if (canShare) await navigator.share({ title: "دعوت به TelBattle", text: url.includes("three_invite=") ? "بیا نبرد سه‌راندی بازی کنیم" : "بیا با هم Quick بازی کنیم", url });
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
  if (!state.fight || state.loading || state.lastRound?.game_over) return;
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
  if (action === "onboarding-skip") { finishOnboarding(); return; }
  if (action === "onboarding-back") {
    state.onboardingStep = Math.max(0, state.onboardingStep - 1);
    render();
    return;
  }
  if (action === "onboarding-next") {
    if (state.onboardingStep >= onboardingSlides.length - 1) finishOnboarding();
    else { state.onboardingStep += 1; render(); }
    return;
  }
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
  if (action === "hub-game") { state.screen = "lobby"; state.detailCard = undefined; scene.showIdle(); refreshFeaturedCards(); render(); }
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
  if (action === "enter-three") void openThreeMenu();
  if (action === "three-random") void beginThree("random");
  if (action === "three-invite") void beginThree("invite");
  if (action === "accept-three") void acceptThree();
  if (action === "dismiss-three") { state.incomingThreeInvite = undefined; state.screen = "lobby"; render(); }
  if (action === "cancel-three") void cancelThree();
  if (action === "share-three") void shareInvite(button.dataset.url || "");
  if (action === "quick-random") void beginQuick("random");
  if (action === "quick-invite") void beginQuick("invite");
  if (action === "accept-invite") void acceptInvite();
  if (action === "dismiss-invite") { state.incomingInvite = undefined; state.screen = "lobby"; render(); }
  if (action === "cancel-quick") void cancelQuick();
  if (action === "share-invite") void shareInvite(button.dataset.url || "");
  if (action === "back") {
    if (state.playMode === "quick") void cancelQuick();
    else if (state.playMode === "three") void cancelThree();
    else { state.screen = "lobby"; state.selected = undefined; scene.showIdle(); render(); }
  }
  if (action === "home") {
    stopQuickPolling();
    stopThreePolling();
    state.screen = "lobby";
    state.quick = undefined;
    state.three = undefined;
    state.selected = undefined;
    scene.showIdle();
    render();
    void refreshProfile().then(render).catch(() => undefined);
  }
  if (action === "difficulty") { state.difficulty = button.dataset.value as Difficulty; render(); }
  if (action === "select-card") { state.selected = state.cards.find((card) => card.card_id === button.dataset.id); render(); }
  if (action === "start") { if (state.playMode === "quick") void submitQuickCard(); else if (state.playMode === "three") void submitThreeCard(); else void startFight(); }
  if (action === "quick-ability") void submitQuickAbility(button.dataset.value || "skip");
  if (action === "quick-stat") void submitQuickStat(button.dataset.value as StatKey);
  if (action === "three-stat") void submitThreeStat(button.dataset.value as StatKey);
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
  tg?.setHeaderColor?.("#131714");
  tg?.setBackgroundColor?.("#131714");
  state.incomingInvite = new URLSearchParams(location.search).get("invite") || undefined;
  state.incomingThreeInvite = new URLSearchParams(location.search).get("three_invite") || undefined;
  state.screen = "splash";
  state.bootProgress = 18;
  state.bootLabel = "در حال بیدار کردن میدان…";
  render();
  const minimumSplash = new Promise<void>((resolve) => window.setTimeout(resolve, 1500));
  state.bootProgress = 44;
  state.bootLabel = "در حال همگام‌سازی فرمانده…";
  render();
  try {
    await refreshProfile();
  } catch {
    // The lobby remains usable and renders a visible retryable auth error.
  }
  state.bootProgress = 78;
  state.bootLabel = "در حال چیدن کارت‌ها…";
  render();
  await minimumSplash;
  state.bootProgress = 100;
  state.bootLabel = "میدان آماده است";
  render();
  await new Promise<void>((resolve) => window.setTimeout(resolve, 320));
  if (state.incomingThreeInvite) state.screen = "threeMenu";
  else if (state.incomingInvite) state.screen = "quickMenu";
  else state.screen = onboardingSeen() ? "lobby" : "onboarding";
  scene.showIdle();
  render();
  if (!state.incomingInvite && !state.incomingThreeInvite && state.profileStatus === "ready") {
    let pending: string | null = null;
    try { pending = localStorage.getItem(threeStorageKey); } catch { /* Optional storage. */ }
    if (pending) {
      try {
        state.three = await api.threeStatus(pending);
        if (state.three.phase === "card_selection" && !state.three.my_card_locked) await loadCards();
        syncThreeScreen(); render(); scheduleThreePoll();
      } catch { try { localStorage.removeItem(threeStorageKey); } catch { /* Optional storage. */ } }
    }
  }
}

void boot();
