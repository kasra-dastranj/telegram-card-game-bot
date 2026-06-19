// screens/battle.js — صفحه مبارزه

const STATS_FA = {
  power: { label: "قدرت", emoji: "💪", icon: "bolt", color: "rarity-rare" },
  speed: { label: "سرعت", emoji: "⚡", icon: "directions_run", color: "primary" },
  iq: { label: "هوش", emoji: "🧠", icon: "psychology", color: "secondary" },
  popularity: { label: "شهرت", emoji: "⭐", icon: "favorite", color: "rarity-epic" },
};

function renderBattle(state) {
  const fight = state.currentFight;

  // اگه fight هنوز لود نشده
  if (!fight || !fight.fight_id) {
    return `
<div class="min-h-screen flex items-center justify-center">
  <div class="text-center">
    <div class="font-headline-lg text-headline-lg text-primary italic mb-4">TelBattle</div>
    <div class="text-on-surface-variant font-body-md">در حال شروع نبرد...</div>
  </div>
</div>`;
  }

  // اگه نتیجه راوند هست، overlay نشون بده
  if (state.roundResult) {
    return renderRoundResultOverlay(state);
  }

  const playerCard = fight.player_card;
  const aiCard = fight.ai_card;
  const arena = fight.arena;
  const availableStats = fight.available_stats || ["power", "speed", "iq", "popularity"];
  const usedStats = (fight.used_stats && fight.used_stats.player) || [];
  const playerRounds = fight.player_rounds_won || 0;
  const aiRounds = fight.ai_rounds_won || 0;
  const currentRound = fight.current_round || 1;
  const asoDialog = fight.aso_dialog || "«آماده‌ای؟»";

  // دایره‌های راوند
  const roundDots = [1, 2, 3].map(i => {
    let color = "bg-surface-variant";
    if (i <= playerRounds) color = "bg-secondary";
    return `<div class="w-3 h-3 rounded-full ${color} shadow-[0_0_8px_rgba(240,192,64,0.6)]"></div>`;
  }).join('');

  const aiRoundDots = [1, 2, 3].map(i => {
    let color = "bg-surface-variant";
    if (i <= aiRounds) color = "bg-rarity-rare";
    return `<div class="w-3 h-3 rounded-full ${color}"></div>`;
  }).join('');

  // دکمه‌های stat
  const statButtons = ["power", "speed", "iq", "popularity"].map(stat => {
    const s = STATS_FA[stat];
    const isUsed = usedStats.includes(stat);
    const isAvailable = availableStats.includes(stat);
    const value = playerCard ? playerCard[stat] : '?';

    if (isUsed) {
      return `
<div class="w-full bg-surface-container/50 border border-outline/10 rounded-xl py-3 px-4 flex items-center justify-between stat-disabled">
  <div class="flex items-center gap-2">
    <span class="text-lg">${s.emoji}</span>
    <span class="font-button-label text-button-label text-outline line-through">${s.label}</span>
  </div>
  <span class="font-stat-numeric text-stat-numeric text-outline">${value}</span>
</div>`;
    }

    return `
<button data-action="select_stat" data-value="${stat}" ${state.loading ? 'disabled' : ''}
  class="w-full bg-surface-container hover:bg-surface-bright active:scale-95 transition-all border border-white/10 rounded-xl py-3 px-4 flex items-center justify-between group shadow-lg ${state.loading ? 'opacity-60 cursor-wait' : ''}">
  <div class="flex items-center gap-2">
    <span class="text-lg">${s.emoji}</span>
    <span class="font-button-label text-button-label text-on-surface">${s.label}</span>
  </div>
  <span class="font-stat-numeric text-stat-numeric text-secondary group-hover:text-tertiary transition-colors">${value}</span>
</button>`;
  }).join('');

  return `
<div class="min-h-screen flex flex-col bg-background-deep text-on-background overflow-hidden relative"
  style="background-image: linear-gradient(to right, rgba(255,255,255,0.05) 1px, transparent 1px),
         linear-gradient(to bottom, rgba(255,255,255,0.05) 1px, transparent 1px);
         background-size: 20px 20px;">

  <!-- Atmospheric blobs -->
  <div class="fixed top-0 left-0 w-full h-full pointer-events-none z-0 overflow-hidden">
    <div class="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] bg-primary-container/10 rounded-full blur-[120px]"></div>
    <div class="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-surface-bright/20 rounded-full blur-[100px]"></div>
  </div>

  <!-- Battle Header -->
  <header class="w-full px-[16px] pt-6 pb-4 flex flex-col items-center gap-4 z-10 relative">
    <div class="flex justify-between items-center w-full">
      <div class="flex items-center gap-2 bg-surface-container/80 backdrop-blur-md px-4 py-2 rounded-full border border-white/5">
        <span class="text-lg">${arena ? (arena.emoji || '⚔️') : '⚔️'}</span>
        <span class="font-headline-sm text-headline-sm text-text-primary">${arena ? (arena.name_fa || 'Arena') : 'Arena'}</span>
        ${arena && arena.boost_stat ? `<span class="font-label-caps text-label-caps text-secondary text-xs ml-1">+1 ${STATS_FA[arena.boost_stat]?.label || arena.boost_stat}</span>` : ''}
      </div>
      <div class="flex items-center gap-1.5">
        ${roundDots}
      </div>
    </div>
    <div class="flex justify-between items-center w-full max-w-sm mt-2 px-2">
      <div class="flex flex-col items-center">
        <span class="font-label-caps text-label-caps text-rarity-epic">آسو</span>
        <span class="font-headline-md text-headline-md text-rarity-rare">${aiRounds}</span>
      </div>
      <div class="font-button-label text-button-label text-outline bg-surface-container px-4 py-1 rounded-lg">
        راوند ${currentRound}/3
      </div>
      <div class="flex flex-col items-center">
        <span class="font-label-caps text-label-caps text-on-surface-variant">شما</span>
        <span class="font-headline-md text-headline-md text-secondary">${playerRounds}</span>
      </div>
    </div>
  </header>

  <!-- Cards Area -->
  <main class="flex-grow flex flex-col items-center justify-center w-full px-[16px] relative z-10 -mt-4">
    <div class="flex items-center justify-between w-full max-w-md gap-4 relative">
      <!-- Aso Card -->
      <div class="relative">
        <div class="absolute -top-12 left-2 bg-surface-variant/90 backdrop-blur-md border border-rarity-epic
                    text-text-primary px-3 py-1.5 rounded-2xl rounded-bl-sm text-sm z-30 whitespace-nowrap max-w-[160px]">
          ${asoDialog}
        </div>
        <div class="w-36 h-56 bg-surface-card rounded-xl border-2 border-rarity-epic flex flex-col items-center justify-center
                    overflow-hidden shadow-[0_0_25px_rgba(156,39,176,0.5)] transform -rotate-2">
          <div class="h-1/2 w-full bg-gradient-to-br from-rarity-epic to-background-deep flex items-center justify-center relative">
            <span class="material-symbols-outlined text-[48px] text-white fill-icon">person</span>
            <div class="absolute top-2 right-2 bg-rarity-epic text-white text-[10px] font-label-caps px-2 py-0.5 rounded-sm">BOSS</div>
          </div>
          <div class="h-1/2 w-full p-2 flex flex-col justify-between bg-gradient-to-t from-background-deep to-surface-card">
            <h3 class="font-headline-sm text-headline-sm text-rarity-epic truncate text-center mb-1">${fight.ai_name || 'آسو'}</h3>
            ${aiCard ? `
            <div class="grid grid-cols-2 gap-1 gap-y-2 mt-auto opacity-70">
              <div class="flex items-center gap-1"><span class="text-[10px]">💪</span><span class="font-stat-numeric text-[12px] text-on-surface">${aiCard.power}</span></div>
              <div class="flex items-center gap-1 justify-end"><span class="font-stat-numeric text-[12px] text-on-surface">${aiCard.speed}</span><span class="text-[10px]">⚡</span></div>
              <div class="flex items-center gap-1"><span class="text-[10px]">🧠</span><span class="font-stat-numeric text-[12px] text-on-surface">${aiCard.iq}</span></div>
              <div class="flex items-center gap-1 justify-end"><span class="font-stat-numeric text-[12px] text-on-surface">${aiCard.popularity}</span><span class="text-[10px]">⭐</span></div>
            </div>` : ''}
          </div>
        </div>
      </div>

      <!-- VS Badge -->
      <div class="absolute left-1/2 top-1/2 transform -translate-x-1/2 -translate-y-1/2 z-20 flex flex-col items-center">
        <div class="w-14 h-14 rounded-full bg-surface-card border-2 border-primary flex items-center justify-center
                    shadow-[0_0_20px_rgba(123,94,234,0.8)] relative">
          <div class="absolute inset-0 rounded-full bg-primary/20 animate-pulse"></div>
          <span class="font-headline-md text-headline-md text-text-primary italic relative z-10 tracking-widest">VS</span>
        </div>
      </div>

      <!-- Player Card -->
      <div class="w-36 h-56 bg-surface-card rounded-xl border border-rarity-legend relative overflow-hidden
                  shadow-[0_0_25px_rgba(240,192,64,0.4)] transform rotate-2 flex flex-col">
        <div class="h-1/2 w-full bg-surface-container-high flex items-center justify-center relative">
          ${playerCard && playerCard.image_path
            ? `<img src="${playerCard.image_path}" alt="${playerCard.name}" class="w-full h-full object-cover"/>`
            : `<span class="material-symbols-outlined text-[48px] text-outline fill-icon">person</span>`}
          <div class="absolute top-2 right-2 bg-rarity-legend text-on-secondary-fixed text-[10px] font-label-caps px-2 py-0.5 rounded-sm">YOU</div>
        </div>
        <div class="h-1/2 p-2 flex flex-col justify-between bg-gradient-to-t from-background-deep to-surface-card">
          <h3 class="font-headline-sm text-headline-sm text-text-primary truncate text-center mb-1">
            ${playerCard ? playerCard.name : 'کارت شما'}
          </h3>
          ${playerCard ? `
          <div class="grid grid-cols-2 gap-1 gap-y-2 mt-auto">
            <div class="flex items-center gap-1"><span class="text-[10px]">💪</span><span class="font-stat-numeric text-[12px] text-on-surface">${playerCard.power}</span></div>
            <div class="flex items-center gap-1 justify-end"><span class="font-stat-numeric text-[12px] text-on-surface">${playerCard.speed}</span><span class="text-[10px]">⚡</span></div>
            <div class="flex items-center gap-1"><span class="text-[10px]">🧠</span><span class="font-stat-numeric text-[12px] text-on-surface">${playerCard.iq}</span></div>
            <div class="flex items-center gap-1 justify-end"><span class="font-stat-numeric text-[12px] text-on-surface">${playerCard.popularity}</span><span class="text-[10px]">⭐</span></div>
          </div>` : ''}
        </div>
      </div>
    </div>
  </main>

  <!-- Stat Selection Panel -->
  <section class="w-full bg-surface-container-lowest/90 backdrop-blur-xl border-t border-white/5 rounded-t-2xl p-6 pb-8 z-20 shadow-[0_-8px_30px_rgba(10,10,26,0.8)] relative">
    <h2 class="font-headline-sm text-headline-sm text-text-primary text-center mb-4">
      راوند ${currentRound}: آماری رو انتخاب کن
    </h2>
    <div class="grid grid-cols-2 gap-3 max-w-sm mx-auto">
      ${statButtons}
    </div>
  </section>
</div>`;
}

function renderRoundResultOverlay(state) {
  const r = state.roundResult;
  const playerStatInfo = STATS_FA[r.player_stat] || { label: r.player_stat, emoji: "?" };
  const aiStatInfo = STATS_FA[r.ai_stat] || { label: r.ai_stat, emoji: "?" };

  let winnerText, winnerColor, winnerEmoji;
  if (r.round_winner === "player") {
    winnerText = "تو بردی!";
    winnerColor = "text-secondary";
    winnerEmoji = "🎉";
  } else if (r.round_winner === "ai") {
    winnerText = "آسو برد!";
    winnerColor = "text-rarity-rare";
    winnerEmoji = "😈";
  } else {
    winnerText = "مساوی!";
    winnerColor = "text-outline";
    winnerEmoji = "🤝";
  }

  return `
<div class="min-h-screen flex flex-col items-center justify-center bg-background-deep text-on-background p-6">
  <!-- Round Number -->
  <div class="font-label-caps text-label-caps text-outline mb-2">نتیجه راوند ${r.round_number}</div>

  <!-- Winner -->
  <div class="text-4xl mb-2">${winnerEmoji}</div>
  <div class="font-headline-lg text-headline-lg ${winnerColor} mb-6">${winnerText}</div>

  <!-- Aso Dialog -->
  <div class="bg-surface-container/80 border border-white/10 rounded-2xl px-4 py-2 mb-6 max-w-xs text-center">
    <span class="text-on-surface-variant font-body-md">${r.aso_dialog || ''}</span>
  </div>

  <!-- Stat Comparison -->
  <div class="w-full max-w-sm bg-surface-container rounded-2xl border border-white/10 p-4 mb-6">
    <div class="flex justify-between items-center mb-3">
      <div class="text-center flex-1">
        <div class="font-label-caps text-label-caps text-on-surface-variant mb-1">شما</div>
        <div class="font-headline-sm text-headline-sm text-secondary">${playerStatInfo.emoji} ${playerStatInfo.label}</div>
      </div>
      <div class="text-outline font-headline-sm">VS</div>
      <div class="text-center flex-1">
        <div class="font-label-caps text-label-caps text-on-surface-variant mb-1">آسو</div>
        <div class="font-headline-sm text-headline-sm text-rarity-epic">${aiStatInfo.emoji} ${aiStatInfo.label}</div>
      </div>
    </div>
    <div class="flex justify-between items-center">
      <div class="text-center flex-1">
        <span class="font-stat-numeric text-stat-numeric text-on-surface text-2xl">${r.player_total}</span>
        ${r.player_boost > 0 ? `<span class="text-secondary text-xs ml-1">(+${r.player_boost})</span>` : ''}
      </div>
      <div class="text-outline">—</div>
      <div class="text-center flex-1">
        <span class="font-stat-numeric text-stat-numeric text-on-surface text-2xl">${r.ai_total}</span>
        ${r.ai_boost > 0 ? `<span class="text-rarity-epic text-xs ml-1">(+${r.ai_boost})</span>` : ''}
      </div>
    </div>
  </div>

  <!-- Score -->
  <div class="flex gap-4 mb-6">
    <div class="bg-surface-container px-3 py-1.5 rounded-full border border-white/10">
      <span class="text-secondary font-stat-numeric">${r.player_rounds_won}</span>
      <span class="text-outline text-xs mx-1">-</span>
      <span class="text-rarity-rare font-stat-numeric">${r.ai_rounds_won}</span>
    </div>
  </div>

  <!-- Continue Button -->
  <button data-action="dismiss_round" data-value=""
    class="w-full max-w-xs bg-primary hover:bg-primary/80 text-on-primary font-button-label text-button-label py-3 px-6 rounded-xl transition-all active:scale-95 shadow-lg">
    ${r.game_over ? 'مشاهده نتیجه' : 'راوند بعدی ➜'}
  </button>
</div>`;
}
