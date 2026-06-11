// miniapp/api.js — همه ارتباطات با backend

const API_BASE = "/api/v1";

function getAuthHeader() {
  const tg = window.Telegram?.WebApp;
  if (tg?.initData) {
    return { "Authorization": `tma ${tg.initData}` };
  }
  // حالت dev
  return { "X-Debug-User-Id": "1" };
}

async function apiRequest(method, path, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API_BASE + path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "خطای سرور");
  return data;
}

const API = {
  getProfile: () => apiRequest("GET", "/profile"),
  getCards: (rarity = "all", page = 1) =>
    apiRequest("GET", `/cards?rarity=${rarity}&page=${page}&limit=20`),
  getDailyLimit: () => apiRequest("GET", "/solo/daily-limit"),
  soloStart: (playerCardId, difficulty) =>
    apiRequest("POST", "/solo/start", { player_card_id: playerCardId, difficulty }),
  soloRound: (fightId, playerStat) =>
    apiRequest("POST", "/solo/round", { fight_id: fightId, player_stat: playerStat }),
  soloResult: (fightId) => apiRequest("GET", `/solo/result/${fightId}`),
  getLeaderboard: (period = "weekly") =>
    apiRequest("GET", `/leaderboard?period=${period}`),
};
