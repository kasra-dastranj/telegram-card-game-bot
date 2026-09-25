export type Difficulty = "easy" | "medium" | "hard";
export type StatKey = "power" | "speed" | "iq" | "popularity";

export interface CardData {
  card_id: string;
  name: string;
  rarity: "normal" | "rare" | "epic" | "legend" | string;
  power: number;
  speed: number;
  iq: number;
  popularity: number;
  card_type: string;
  abilities: string[];
  biography: string;
  image_url: string;
  is_in_cooldown?: boolean;
  score?: number;
  upgrade?: UpgradePreview;
}

export interface UpgradePreview {
  ok: boolean;
  error?: string;
  error_code?: string;
  upgrade_key?: string;
  card_id?: string;
  card_name?: string;
  from_rarity?: string;
  to_rarity?: string;
  price?: number;
  xp?: number;
  coins?: number;
  can_afford?: boolean;
  blocked_by_match?: boolean;
}

export interface UpgradeResult {
  ok: boolean;
  message: string;
  profile: ProfileData;
  data: { upgrade: UpgradePreview & { xp_gained: number; old_level: number; new_level: number }; card: CardData };
}

export interface DeckData {
  deck_id: string;
  deck_name: string;
  is_valid: boolean;
  total_points: number;
  synergy: { score: number; reasons: string[] };
  cards: CardData[];
}

export interface ClaimStatus { can_claim: boolean; remaining_seconds: number; pool_count: number; }
export interface MissionData {
  mission_id: string; card_id: string; card_name: string; name: string; description: string;
  target: number; current_progress: number; progress_percent: number; completed: boolean;
  reward_claimed: boolean; rarity: string; can_claim: boolean;
}
export interface SkinData {
  skin_id: string; card_id: string; name: string; skin_type: string; image_url: string;
  price: number; description?: string; unlocked: number | boolean;
}
export interface SkinCollection { ok: boolean; active_skin_id: string | null; skins: SkinData[]; }
export interface FusionPreview {
  ok: boolean; target_rarity: "epic" | "legend"; source_rarity: "normal" | "epic";
  retained_card_id: string; consumed_card_ids: string[]; cards: CardData[]; xp: number;
}

export interface ProfileData {
  user_id?: number;
  first_name: string;
  username?: string;
  level: number;
  current_tier: string;
  hearts: number;
  max_hearts: number;
  heart_reset_seconds?: number;
  coins: number;
  total_score: number;
  current_xp?: number;
  xp_to_next_level?: number;
  tier_points?: number;
  stats?: Record<string, number>;
  best_card?: CardData | null;
  claim?: {
    can_claim: boolean;
    remaining_seconds: number;
    message?: string | null;
  };
  counts?: {
    cards: number;
    decks: number;
    missions_ready: number;
    rarities: Record<string, number>;
  };
}

export interface CardPage {
  total: number;
  page: number;
  limit: number;
  page_count: number;
  cards: CardData[];
}

export interface CardFilters {
  page?: number;
  limit?: number;
  rarity?: string;
  sort?: string;
  query?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface FightData {
  fight_id: string;
  player_card: CardData;
  ai_card: CardData;
  ai_name: string;
  aso_dialog: string;
  arena: { arena_id: string; name_fa: string; boost_stat: StatKey; emoji: string; version?: number | null; background_url?: string | null };
  current_round: number;
  available_stats: StatKey[];
}

export interface RoundData {
  round_number: number;
  player_stat: StatKey;
  player_value: number;
  player_boost: number;
  player_total: number;
  ai_stat: StatKey;
  ai_value: number;
  ai_boost: number;
  ai_total: number;
  round_winner: "player" | "ai" | "tie";
  player_rounds_won: number;
  ai_rounds_won: number;
  game_over: boolean;
  next_round: number;
  available_stats: StatKey[];
  aso_dialog: string;
  final_result?: {
    winner: "player" | "ai" | "tie";
    aso_dialog: string;
    rewards: Record<string, number>;
  };
}

export type QuickPhase = "card_selection" | "ability_selection" | "stat_selection" | "completed";

export interface QuickAbility {
  ability_key: string;
  quantity: number;
  title: string;
  description: string;
}

export interface QuickReport {
  winner_id: number | null;
  is_tie: boolean;
  forfeit?: boolean;
  reason?: string;
  breakdown: Record<string, {
    card_name: string;
    selected_stat: StatKey;
    scored_stats?: StatKey[];
    base_components?: number[];
    final_components?: number[];
    base_value?: number;
    final_value: number;
  }>;
}

export interface QuickState {
  request_id: string;
  user_id: number;
  status: "waiting" | "accepted" | "active" | "completed" | "expired" | "cancelled";
  source: "random_queue" | "invite_link";
  variant: "normal" | "random";
  expires_at: string;
  matchmaking_status?: "waiting" | "matched";
  invite_token?: string;
  invite_url?: string;
  message?: string;
  opponent_id?: number;
  phase?: QuickPhase;
  scoring_rule?: string;
  deadline?: string;
  arena?: {
    id: string;
    arena_id?: string;
    version?: number | null;
    background_url?: string | null;
    name: string;
    emoji: string;
    effects: Array<{ card_type: StatKey; stat: StatKey; delta: number }>;
    abilities_enabled: boolean;
  };
  my_card?: CardData;
  my_final_values?: Partial<Record<StatKey, number>>;
  my_arena_effects?: Array<{ card_type: StatKey; stat: StatKey; delta: number }>;
  my_card_locked?: boolean;
  opponent_card_selected?: boolean;
  opponent_card?: CardData;
  abilities?: QuickAbility[];
  my_ability?: string;
  my_ability_locked?: boolean;
  opponent_ability_selected?: boolean;
  allowed_stats?: StatKey[];
  my_stat?: StatKey;
  my_stat_locked?: boolean;
  opponent_stat_selected?: boolean;
  report?: QuickReport;
}

const API_BASE = "/api/v1";
const demoParams = new URLSearchParams(location.search);
const demoMode = demoParams.has("demo");
const denseDemoMode = demoParams.has("dense");
let demoRound = 0;
let demoQuickPolls = 0;
let demoQuick: QuickState | undefined;
let demoDecks: DeckData[] = [];
let demoClaimed = false;
let demoActiveSkin: string | null = null;

const demoBaseCards: CardData[] = [
  { card_id: "demo-heisenberg", name: "Heisenberg", rarity: "legend", power: 91, speed: 63, iq: 97, popularity: 86, card_type: "IQ_TYPE", abilities: ["ذهن برتر"], biography: "سلطان محاسبه و غافلگیری", image_url: "/card-images/heisenberg.png" },
  { card_id: "demo-batman", name: "Batman", rarity: "epic", power: 84, speed: 82, iq: 94, popularity: 96, card_type: "IQ_TYPE", abilities: ["آمادگی کامل"], biography: "شوالیه‌ای که همیشه نقشه دارد", image_url: "/card-images/batman.png" },
  { card_id: "demo-thanos", name: "Thanos", rarity: "legend", power: 99, speed: 58, iq: 88, popularity: 93, card_type: "POWER_TYPE", abilities: ["تعادل نهایی"], biography: "قدرتی که میدان را می‌لرزاند", image_url: "/card-images/thanos.png" },
];

const demoCards: CardData[] = denseDemoMode
  ? [
      ...demoBaseCards,
      ...Array.from({ length: 5 }, (_, index) => ({
        ...demoBaseCards[index % demoBaseCards.length],
        card_id: `demo-reserve-${index + 1}`,
        name: `${demoBaseCards[index % demoBaseCards.length].name} ${index + 2}`,
      })),
      ...Array.from({ length: 3 }, (_, index) => ({ ...demoBaseCards[index], card_id: `demo-normal-${index + 1}`, name: `Starter ${index + 1}`, rarity: "normal" })),
    ]
  : demoBaseCards;

function makeDemoQuick(source: QuickState["source"]): QuickState {
  demoQuickPolls = 0;
  demoQuick = {
    request_id: "demo-quick",
    user_id: 1,
    status: "waiting",
    source,
    variant: "normal",
    expires_at: new Date(Date.now() + 5 * 60_000).toISOString(),
    matchmaking_status: "waiting",
    invite_token: source === "invite_link" ? "TELBATTLE-DEMO" : undefined,
    invite_url: source === "invite_link" ? `${location.origin}/?demo=1&invite=TELBATTLE-DEMO` : undefined,
  };
  return { ...demoQuick };
}

function advanceDemoQueue(): QuickState {
  if (!demoQuick) return makeDemoQuick("random_queue");
  demoQuickPolls += 1;
  if (demoQuick.status === "waiting" && demoQuickPolls >= 1) {
    demoQuick = { ...demoQuick, status: "accepted", matchmaking_status: "matched", opponent_id: 202, phase: "card_selection", deadline: new Date(Date.now() + 60_000).toISOString() };
  }
  return { ...demoQuick };
}

function authHeaders(): Record<string, string> {
  const tg = window.Telegram?.WebApp;
  return tg?.initData
    ? { Authorization: `tma ${tg.initData}` }
    : { "X-Debug-User-Id": "1" };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(API_BASE + path, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const payload = data as { error?: string; error_code?: string };
    throw new ApiError(payload.error || "ارتباط با سرور برقرار نشد", response.status, payload.error_code);
  }
  return data as T;
}

export const api = {
  async profile(): Promise<ProfileData> {
    if (demoMode) return {
      first_name: "فرمانده",
      level: 12,
      current_tier: "Gold",
      hearts: 4,
      max_hearts: 5,
      coins: 1840,
      total_score: 7620,
      counts: { cards: demoCards.length, decks: demoDecks.length, missions_ready: 1, rarities: {} },
    };
    return request("GET", "/profile");
  },
  async cardPage(filters: CardFilters = {}): Promise<CardPage> {
    if (demoMode) {
      const rarity = filters.rarity || "all";
      const query = (filters.query || "").trim().toLocaleLowerCase();
      const page = filters.page || 1;
      const limit = filters.limit || 20;
      let cards = demoCards.filter((card) => rarity === "all" || card.rarity === rarity);
      if (query) cards = cards.filter((card) => card.name.toLocaleLowerCase().includes(query));
      const total = cards.length;
      return {
        total,
        page,
        limit,
        page_count: Math.max(1, Math.ceil(total / limit)),
        cards: cards.slice((page - 1) * limit, page * limit),
      };
    }
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== "") params.set(key, String(value));
    });
    return request("GET", `/cards?${params.toString()}`);
  },
  async cardDetail(cardId: string): Promise<CardData> {
    if (demoMode) {
      const card = demoCards.find((item) => item.card_id === cardId) || demoCards[0];
      const target = card.rarity === "normal" ? "epic" : card.rarity === "epic" ? "legend" : undefined;
      return { ...card, upgrade: target ? { ok: true, upgrade_key: `${card.rarity}_to_${target}`, card_id: card.card_id, card_name: card.name, from_rarity: card.rarity, to_rarity: target, price: target === "epic" ? 100 : 500, xp: target === "epic" ? 15 : 30, coins: 1840, can_afford: true, blocked_by_match: false } : { ok: false, error: "این کارت قابلیت ارتقای بیشتر ندارد", error_code: "not_upgradeable" } };
    }
    return request("GET", `/cards/${encodeURIComponent(cardId)}`);
  },
  async upgradePreview(cardId: string): Promise<UpgradePreview> {
    if (demoMode) return (await this.cardDetail(cardId)).upgrade || { ok: false, error: "قابل ارتقا نیست" };
    return request("POST", `/cards/${encodeURIComponent(cardId)}/upgrade/preview`);
  },
  async upgradeCard(cardId: string, upgradeKey: string): Promise<UpgradeResult> {
    if (demoMode) {
      const index = demoCards.findIndex((card) => card.card_id === cardId);
      const source = index >= 0 ? demoCards[index] : demoCards[0];
      const target = source.rarity === "normal" ? "epic" : "legend";
      const upgraded = { ...source, rarity: target };
      if (index >= 0) demoCards[index] = upgraded;
      return { ok: true, message: "کارت با موفقیت ارتقا پیدا کرد", profile: await this.profile(), data: { upgrade: { ok: true, upgrade_key: upgradeKey, to_rarity: target, xp_gained: target === "epic" ? 15 : 30, old_level: 12, new_level: 12 }, card: upgraded } };
    }
    return request("POST", `/cards/${encodeURIComponent(cardId)}/upgrade`, { upgrade_key: upgradeKey });
  },
  async cards(): Promise<CardData[]> {
    if (demoMode) return demoCards;
    const first = await request<CardPage>("GET", "/cards?limit=60&page=1");
    const cards = [...first.cards];
    for (let page = 2; page <= first.page_count; page += 1) {
      const next = await request<CardPage>("GET", `/cards?limit=60&page=${page}`);
      cards.push(...next.cards);
    }
    return cards;
  },
  async decks(): Promise<DeckData[]> {
    if (demoMode) return demoDecks.map((deck) => ({ ...deck, cards: [...deck.cards] }));
    return (await request<{ decks: DeckData[] }>("GET", "/decks")).decks;
  },
  async createDeck(name: string, cardIds: string[]): Promise<DeckData> {
    if (demoMode) {
      const cards = cardIds.map((id) => demoCards.find((card) => card.card_id === id)).filter(Boolean) as CardData[];
      const deck: DeckData = { deck_id: `demo-deck-${Date.now()}`, deck_name: name || `دک ${demoDecks.length + 1}`, is_valid: cards.length === 3, total_points: cards.reduce((sum, card) => sum + (card.rarity === "legend" ? 3 : card.rarity === "normal" ? 1 : 2), 0), synergy: { score: 0, reasons: [] }, cards };
      demoDecks = [...demoDecks, deck];
      return deck;
    }
    return (await request<{ data: DeckData }>("POST", "/decks", { name, card_ids: cardIds })).data;
  },
  async updateDeck(deckId: string, name: string, cardIds: string[]): Promise<DeckData> {
    if (demoMode) {
      const cards = cardIds.map((id) => demoCards.find((card) => card.card_id === id)).filter(Boolean) as CardData[];
      const current = demoDecks.find((deck) => deck.deck_id === deckId)!;
      const updated = { ...current, deck_name: name, cards };
      demoDecks = demoDecks.map((deck) => deck.deck_id === deckId ? updated : deck);
      return updated;
    }
    return (await request<{ data: DeckData }>("PUT", `/decks/${encodeURIComponent(deckId)}`, { name, card_ids: cardIds })).data;
  },
  async deleteDeck(deckId: string): Promise<void> {
    if (demoMode) { demoDecks = demoDecks.filter((deck) => deck.deck_id !== deckId); return; }
    await request("DELETE", `/decks/${encodeURIComponent(deckId)}`);
  },
  async claimStatus(): Promise<ClaimStatus> {
    if (demoMode) return { can_claim: !demoClaimed, remaining_seconds: demoClaimed ? 3600 : 0, pool_count: 12 };
    return request("GET", "/claim");
  },
  async claimDaily(): Promise<{ message: string; data: { card: CardData }; profile: ProfileData }> {
    if (demoMode) { demoClaimed = true; return { message: "کارت روزانه دریافت شد", data: { card: demoCards[0] }, profile: await this.profile() }; }
    return request("POST", "/claim");
  },
  async missions(): Promise<MissionData[]> {
    if (demoMode) return [
      { mission_id: "demo-batman", card_id: "demo-batman", card_name: "Batman", name: "برد با هوش", description: "با این کارت 5 برد هوشی بگیر", target: 5, current_progress: 5, progress_percent: 100, completed: true, reward_claimed: false, rarity: "epic", can_claim: true },
      { mission_id: "demo-heisenberg", card_id: "demo-heisenberg", card_name: "Heisenberg", name: "برد کلی", description: "با این کارت 10 بار ببر", target: 10, current_progress: 6, progress_percent: 60, completed: false, reward_claimed: false, rarity: "legend", can_claim: false },
    ];
    return (await request<{ missions: MissionData[] }>("GET", "/missions")).missions;
  },
  async claimMission(missionId: string): Promise<{ message: string; data: { card: CardData } }> {
    if (demoMode) return { message: "پاداش مأموریت دریافت شد", data: { card: { ...demoCards[1], rarity: "legend" } } };
    return request("POST", `/missions/${encodeURIComponent(missionId)}/claim`);
  },
  async cardSkins(cardId: string): Promise<SkinCollection> {
    if (demoMode) return { ok: true, active_skin_id: demoActiveSkin, skins: [
      { skin_id: "demo-night", card_id: cardId, name: "Night Ops", skin_type: "special", image_url: "/card-images/batman.png", price: 150, description: "ظاهر شبانه", unlocked: true },
      { skin_id: "demo-gold", card_id: cardId, name: "Gold Frame", skin_type: "premium", image_url: "/card-images/heisenberg.png", price: 300, description: "قاب طلایی", unlocked: false },
    ] };
    return request("GET", `/cards/${encodeURIComponent(cardId)}/skins`);
  },
  async purchaseSkin(cardId: string, skinId: string): Promise<void> {
    if (demoMode) return;
    await request("POST", `/cards/${encodeURIComponent(cardId)}/skins/${encodeURIComponent(skinId)}/purchase`);
  },
  async activateSkin(cardId: string, skinId: string | null): Promise<void> {
    if (demoMode) { demoActiveSkin = skinId; return; }
    await request("POST", `/cards/${encodeURIComponent(cardId)}/skins/activate`, { skin_id: skinId });
  },
  async fusionPreview(cardIds: string[], retainedCardId: string, targetRarity: "epic" | "legend"): Promise<FusionPreview> {
    if (demoMode) return { ok: true, target_rarity: targetRarity, source_rarity: targetRarity === "epic" ? "normal" : "epic", retained_card_id: retainedCardId, consumed_card_ids: cardIds.filter((id) => id !== retainedCardId), cards: cardIds.map((id) => demoCards.find((card) => card.card_id === id)!).filter(Boolean), xp: targetRarity === "epic" ? 15 : 30 };
    return request("POST", "/fusions/preview", { card_ids: cardIds, retained_card_id: retainedCardId, target_rarity: targetRarity });
  },
  async executeFusion(cardIds: string[], retainedCardId: string, targetRarity: "epic" | "legend"): Promise<{ message: string; data: { card: CardData; consumed_cards: CardData[] }; profile: ProfileData }> {
    if (demoMode) {
      const retainedIndex = demoCards.findIndex((card) => card.card_id === retainedCardId);
      const retained = { ...demoCards[retainedIndex], rarity: targetRarity };
      for (const cardId of cardIds.filter((id) => id !== retainedCardId)) {
        const index = demoCards.findIndex((card) => card.card_id === cardId); if (index >= 0) demoCards.splice(index, 1);
      }
      const updatedIndex = demoCards.findIndex((card) => card.card_id === retainedCardId); if (updatedIndex >= 0) demoCards[updatedIndex] = retained;
      return { message: "Fusion با موفقیت انجام شد", data: { card: retained, consumed_cards: [] }, profile: await this.profile() };
    }
    return request("POST", "/fusions", { card_ids: cardIds, retained_card_id: retainedCardId, target_rarity: targetRarity });
  },
  async start(cardId: string, difficulty: Difficulty): Promise<FightData> {
    if (demoMode) {
      demoRound = 0;
      const player = demoCards.find((card) => card.card_id === cardId) || demoCards[0];
      return { fight_id: "demo-fight", player_card: player, ai_card: demoCards[2], ai_name: "ASO / تاکتیکی", aso_dialog: "ببینم تا کدام راند دوام می‌آوری.", arena: { arena_id: "neon", name_fa: "برج خاموش", boost_stat: "iq", emoji: "" }, current_round: 1, available_stats: ["power", "speed", "iq", "popularity"] };
    }
    return request("POST", "/solo/start", { player_card_id: cardId, difficulty });
  },
  async round(fightId: string, stat: StatKey): Promise<RoundData> {
    if (!demoMode) return request("POST", "/solo/round", { fight_id: fightId, player_stat: stat });
    demoRound += 1;
    const playerWins = demoRound;
    const gameOver = demoRound >= 2;
    return { round_number: demoRound, player_stat: stat, player_value: 91, player_boost: stat === "iq" ? 8 : 0, player_total: stat === "iq" ? 99 : 91, ai_stat: demoRound === 1 ? "power" : "popularity", ai_value: 88, ai_boost: 0, ai_total: 88, round_winner: "player", player_rounds_won: playerWins, ai_rounds_won: 0, game_over: gameOver, next_round: demoRound + 1, available_stats: ["power", "speed", "iq", "popularity"].filter((item) => item !== stat) as StatKey[], aso_dialog: demoRound === 1 ? "این فقط شروع بود..." : "این نبرد را به خاطر می‌سپارم.", final_result: gameOver ? { winner: "player", aso_dialog: "امروز میدان برای تو بود.", rewards: { coins: 180, score: 240, xp: 90 } } : undefined };
  },
  async quickMatchmaking(variant: QuickState["variant"] = "normal"): Promise<QuickState> {
    if (demoMode) return makeDemoQuick("random_queue");
    return request("POST", "/quick/matchmaking", { variant });
  },
  async createQuickInvite(variant: QuickState["variant"] = "normal"): Promise<QuickState> {
    if (demoMode) return makeDemoQuick("invite_link");
    return request("POST", "/quick/invites", { variant });
  },
  async acceptQuickInvite(token: string): Promise<QuickState> {
    if (demoMode) {
      demoQuick = makeDemoQuick("invite_link");
      demoQuick = { ...demoQuick, status: "accepted", opponent_id: 101, phase: "card_selection", deadline: new Date(Date.now() + 60_000).toISOString() };
      return { ...demoQuick };
    }
    return request("POST", `/quick/invites/${encodeURIComponent(token)}/accept`);
  },
  async quickStatus(requestId: string): Promise<QuickState> {
    if (demoMode) return advanceDemoQueue();
    return request("GET", `/quick/requests/${encodeURIComponent(requestId)}`);
  },
  async cancelQuick(requestId: string): Promise<QuickState> {
    if (demoMode && demoQuick) return { ...demoQuick, status: "cancelled" };
    return request("POST", `/quick/requests/${encodeURIComponent(requestId)}/cancel`);
  },
  async quickCard(requestId: string, cardId: string): Promise<QuickState> {
    if (demoMode && demoQuick) {
      const card = demoCards.find((item) => item.card_id === cardId) || demoCards[0];
      demoQuick = { ...demoQuick, status: "active", phase: "ability_selection", my_card: card, my_card_locked: true, opponent_card_selected: true, arena: { id: "city", name: "شهر نئون", emoji: "", effects: [{ card_type: "power", stat: "power", delta: 1 }, { card_type: "iq", stat: "iq", delta: 1 }], abilities_enabled: true }, abilities: [{ ability_key: "reveal_opponent", quantity: 1, title: "مشاهده کارت حریف", description: "پیش از انتخاب ویژگی، کارت حریف را می‌بینی." }], deadline: new Date(Date.now() + 30_000).toISOString() };
      return { ...demoQuick };
    }
    return request("POST", `/quick/matches/${encodeURIComponent(requestId)}/card`, { card_id: cardId });
  },
  async quickAbility(requestId: string, abilityKey: string): Promise<QuickState> {
    if (demoMode && demoQuick) {
      demoQuick = { ...demoQuick, phase: "stat_selection", my_ability: abilityKey, my_ability_locked: true, opponent_ability_selected: true, opponent_card: abilityKey === "reveal_opponent" ? demoCards[1] : undefined, allowed_stats: ["power", "speed", "iq", "popularity"], deadline: new Date(Date.now() + 60_000).toISOString() };
      return { ...demoQuick };
    }
    return request("POST", `/quick/matches/${encodeURIComponent(requestId)}/ability`, { ability_key: abilityKey });
  },
  async quickStat(requestId: string, stat: StatKey): Promise<QuickState> {
    if (demoMode && demoQuick) {
      demoQuick = { ...demoQuick, status: "completed", phase: "completed", my_stat: stat, my_stat_locked: true, opponent_stat_selected: true, opponent_card: demoCards[1], report: { winner_id: 1, is_tie: false, breakdown: { "1": { card_name: demoQuick.my_card?.name || "Heisenberg", selected_stat: stat, final_value: stat === "iq" ? 98 : 92 }, "202": { card_name: "Batman", selected_stat: "power", final_value: 85 } } } };
      return { ...demoQuick };
    }
    return request("POST", `/quick/matches/${encodeURIComponent(requestId)}/stat`, { stat });
  },
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData?: string;
        ready(): void;
        expand(): void;
        setHeaderColor?(color: string): void;
        setBackgroundColor?(color: string): void;
        HapticFeedback?: { impactOccurred(style: string): void; notificationOccurred(type: string): void };
      };
    };
  }
}
