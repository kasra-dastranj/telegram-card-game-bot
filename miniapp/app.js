// miniapp/app.js — router ساده

const state = {
  screen: "mode_select",
  profile: null,
  selectedDifficulty: null,
  selectedCardId: null,
  selectedCard: null,
  currentFight: null,
  lastFightResult: null,
  cards: [],
  leaderboard: null,
  loading: false,
  error: null,
};

function navigate(screen, data = {}) {
  Object.assign(state, data);
  state.screen = screen;
  render();
}

function render() {
  const app = document.getElementById("app");
  switch (state.screen) {
    case "mode_select":   app.innerHTML = renderModeSelect(state); break;
    case "aso_select":    app.innerHTML = renderAsoSelect(state); break;
    case "card_select":   app.innerHTML = renderCardSelect(state); break;
    case "battle":        app.innerHTML = renderBattle(state); break;
    case "result":        app.innerHTML = renderResult(state); break;
    case "profile":       app.innerHTML = renderProfile(state); break;
    case "leaderboard":   app.innerHTML = renderLeaderboard(state); break;
    default:              app.innerHTML = renderModeSelect(state);
  }
  bindEvents();
}

function bindEvents() {
  document.querySelectorAll("[data-action]").forEach(el => {
    el.removeEventListener("click", handleAction);
    el.addEventListener("click", handleAction);
  });
}

async function handleAction(e) {
  const el = e.currentTarget;
  const action = el.dataset.action;
  const value = el.dataset.value;

  switch (action) {
    case "go_aso_select":
      navigate("aso_select");
      break;

    case "select_difficulty":
      navigate("card_select", { selectedDifficulty: value });
      await loadCards();
      break;

    case "select_card": {
      const card = state.cards.find(c => c.card_id === value);
      state.selectedCardId = value;
      state.selectedCard = card || null;
      render(); // re-render to show selection highlight + bottom sheet
      break;
    }

    case "confirm_card":
      if (!state.selectedCardId) return;
      navigate("battle", {});
      await startFight();
      break;

    case "select_stat":
      await playRound(value);
      break;

    case "go_home":
      navigate("mode_select");
      break;

    case "play_again":
      navigate("aso_select");
      break;

    case "go_profile":
      navigate("profile", { profile: state.profile });
      loadProfile();
      break;

    case "go_leaderboard":
      navigate("leaderboard");
      loadLeaderboard();
      break;

    case "filter_rarity":
      await loadCards(value);
      break;

    case "filter_leaderboard":
      await loadLeaderboard(value);
      break;
  }
}

async function startFight() {
  try {
    showLoading("battle");
    const fight = await API.soloStart(state.selectedCardId, state.selectedDifficulty);
    state.currentFight = fight;
    render();
  } catch (err) {
    showError(err.message);
    navigate("card_select");
  }
}

async function playRound(stat) {
  if (state.loading) return;
  state.loading = true;

  try {
    const result = await API.soloRound(state.currentFight.fight_id, stat);
    // آپدیت available_stats
    state.currentFight = { ...state.currentFight, ...result };
    if (result.game_over) {
      navigate("result", { lastFightResult: result.final_result });
    } else {
      render();
    }
  } catch (err) {
    showError(err.message);
    render();
  } finally {
    state.loading = false;
  }
}

async function loadCards(rarity = "all") {
  state.loading = true;
  render();
  try {
    const data = await API.getCards(rarity);
    state.cards = data.cards;
    state.selectedCard = null;
    state.selectedCardId = null;
  } catch (err) {
    console.warn("loadCards error:", err.message);
    state.cards = [];
  } finally {
    state.loading = false;
    render();
  }
}

async function loadProfile() {
  try {
    const data = await API.getProfile();
    state.profile = data;
    render();
  } catch (err) {
    showError(err.message);
  }
}

async function loadLeaderboard(period = "weekly") {
  try {
    const data = await API.getLeaderboard(period);
    state.leaderboard = data;
    render();
  } catch (err) {
    showError(err.message);
  }
}

function showLoading(screen) {
  state.loading = true;
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="min-h-screen flex items-center justify-center">
      <div class="text-center">
        <div class="font-headline-lg text-headline-lg text-primary italic mb-4">TelBattle</div>
        <div class="text-on-surface-variant font-body-md">در حال بارگذاری...</div>
      </div>
    </div>`;
}

function showError(msg) {
  const tg = window.Telegram?.WebApp;
  if (tg?.showAlert) {
    tg.showAlert(msg);
  } else {
    alert(msg);
  }
}

// شروع اپ
async function initApp() {
  const tg = window.Telegram?.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  // بارگذاری پروفایل در پس‌زمینه — اگه خطا داد مشکلی نیست
  try {
    state.profile = await API.getProfile();
  } catch (e) {
    console.warn("Profile load failed:", e.message);
  }

  // navigate صفحه رو render می‌کنه و loading رو جایگزین می‌کنه
  navigate("mode_select");
}

// اجرای فوری — script‌ها بدون defer لود میشن
initApp();
