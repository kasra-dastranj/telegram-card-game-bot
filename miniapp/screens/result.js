// screens/result.js — صفحه نتیجه

function renderResult(state) {
  const result = state.lastFightResult;
  const fight = state.currentFight;

  if (!result) {
    return `
<div class="min-h-screen flex items-center justify-center">
  <button data-action="go_home" class="bg-primary-container text-on-primary-container font-button-label px-6 py-3 rounded-lg">بازگشت به خانه</button>
</div>`;
  }

  const isWin = result.winner === "player";
  const isTie = result.winner === "tie";
  const xpGained = result.rewards ? result.rewards.xp_gained : 0;
  const scoreGained = result.rewards ? result.rewards.score_gained : 0;
  const tierPoints = result.rewards ? result.rewards.tier_points_change : 0;
  const heartsLost = result.rewards ? result.rewards.hearts_lost : 0;
  const levelUp = result.rewards ? result.rewards.level_up : false;
  const newLevel = result.rewards ? result.rewards.new_level : null;
  const tierChange = result.rewards ? result.rewards.tier_change : null;
  const asoDialog = result.aso_dialog || (isWin ? '«امروز رحم کردم.»' : '«ضعیف بودی.»');

  const confettiScript = isWin ? `
<script>
(function() {
  var container = document.getElementById('confetti-container');
  if (!container) return;
  var colors = ['#f0c040', '#7b5eea', '#cbbeff', '#FF9800', '#9C27B0'];
  for (var i = 0; i < 60; i++) {
    var conf = document.createElement('div');
    conf.className = 'confetti-piece';
    conf.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    conf.style.left = Math.random() * 100 + 'vw';
    conf.style.animationDuration = (Math.random() * 3 + 2) + 's';
    conf.style.animationDelay = (Math.random() * 2) + 's';
    container.appendChild(conf);
  }
})();
<\/script>` : '';

  // نمایش راوندها
  const roundsHistory = result.rounds_detail || [];
  const roundsHtml = roundsHistory.length > 0 ? `
<div class="mt-4 bg-surface-container-low rounded-lg p-4 border border-white/5">
  <h4 class="font-label-caps text-label-caps text-outline mb-3 uppercase">جزئیات راوندها</h4>
  ${roundsHistory.map(r => {
    const won = r.winner === 'player';
    const lost = r.winner === 'ai';
    return `
  <div class="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
    <span class="font-label-caps text-label-caps text-outline">راوند ${r.round}</span>
    <div class="flex items-center gap-3 text-sm">
      <span class="text-on-surface">${r.player_total}</span>
      <span class="${won ? 'text-secondary' : lost ? 'text-rarity-rare' : 'text-outline'}">
        ${won ? '✅ برد' : lost ? '❌ باخت' : '🤝 مساوی'}
      </span>
      <span class="text-on-surface-variant">${r.ai_total}</span>
    </div>
  </div>`;
  }).join('')}
</div>` : '';

  return `
<div class="min-h-screen flex flex-col text-text-primary relative pb-24 font-body-md">
  ${isWin ? '<div class="absolute inset-0 pointer-events-none overflow-hidden z-0" id="confetti-container"></div>' : ''}

  <main class="flex-1 flex flex-col items-center justify-center p-[16px] z-10 w-full max-w-[375px] mx-auto">
    <!-- Hero Icon -->
    ${isWin ? `
    <div class="relative w-32 h-32 flex items-center justify-center rounded-full mb-6 shadow-[0_0_40px_rgba(240,192,64,0.4)] bg-surface-card border border-secondary/20">
      <span class="material-symbols-outlined text-[80px] text-secondary fill-icon pulse-glow">emoji_events</span>
    </div>` : isTie ? `
    <div class="relative w-32 h-32 flex items-center justify-center rounded-full mb-6 shadow-[0_0_30px_rgba(203,190,255,0.3)] bg-surface-card border border-primary/20">
      <span class="text-6xl">🤝</span>
    </div>` : `
    <div class="relative w-32 h-32 flex items-center justify-center rounded-full mb-6 shadow-[0_0_40px_rgba(244,67,54,0.4)] bg-surface-card border border-rarity-rare/20">
      <span class="material-symbols-outlined text-[80px] text-rarity-rare fill-icon">heart_broken</span>
    </div>`}

    <!-- Result Text -->
    <div class="text-center mb-6 w-full">
      <h1 class="font-headline-lg text-headline-lg mb-2 ${isWin ? 'text-secondary' : isTie ? 'text-primary' : 'text-rarity-rare'}">
        ${isWin ? 'بُردی!' : isTie ? 'مساوی!' : 'باختی...'}
      </h1>
      <p class="text-on-surface-variant font-body-md">${asoDialog}</p>
    </div>

    ${levelUp ? `
    <div class="w-full bg-primary-container/20 border border-primary-container/50 rounded-xl p-3 mb-4 text-center">
      <span class="font-headline-sm text-headline-sm text-primary">🎉 LEVEL UP! → ${newLevel}</span>
    </div>` : ''}

    ${tierChange ? `
    <div class="w-full bg-secondary/10 border border-secondary/30 rounded-xl p-3 mb-4 text-center">
      <span class="font-label-caps text-label-caps text-secondary">Tier جدید: ${tierChange}</span>
    </div>` : ''}

    <!-- Rewards Card -->
    <div class="w-full bg-surface-card border border-white/10 rounded-xl p-5 mb-8 shadow-lg relative overflow-hidden">
      <div class="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent pointer-events-none"></div>
      <h3 class="font-headline-sm text-headline-sm mb-4 border-b border-white/10 pb-2">نتایج نبرد</h3>
      <div class="space-y-3">
        ${isWin ? `
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-primary fill-icon">stars</span>
            <span>امتیاز</span>
          </div>
          <span class="font-stat-numeric text-stat-numeric text-primary">+${scoreGained}</span>
        </div>` : ''}
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-rarity-epic fill-icon">bolt</span>
            <span>تجربه (XP)</span>
          </div>
          <span class="font-stat-numeric text-stat-numeric text-rarity-epic">+${xpGained}</span>
        </div>
        ${!isTie ? `<div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-secondary fill-icon">military_tech</span>
            <span>Tier Points</span>
          </div>
          <span class="font-stat-numeric text-stat-numeric ${tierPoints >= 0 ? 'text-secondary' : 'text-rarity-rare'}">${tierPoints >= 0 ? '+' : ''}${tierPoints}</span>
        </div>` : ''}
        ${heartsLost > 0 ? `
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-rarity-rare fill-icon">favorite</span>
            <span>قلب کم شد</span>
          </div>
          <span class="font-stat-numeric text-stat-numeric text-rarity-rare">-${heartsLost}</span>
        </div>` : ''}
      </div>
      ${roundsHtml}
    </div>

    <!-- Action Buttons -->
    <div class="w-full flex flex-col gap-3">
      <button data-action="play_again"
        class="w-full bg-primary-container text-on-primary-container font-button-label text-button-label uppercase py-3 rounded-lg
               shadow-[0_0_20px_rgba(123,94,234,0.4)] active:scale-95 transition-all flex items-center justify-center gap-2">
        <span class="material-symbols-outlined">replay</span>
        بازی دوباره
      </button>
      <button data-action="go_home"
        class="w-full bg-surface-container-high border border-outline/30 text-text-primary font-button-label text-button-label uppercase py-3 rounded-lg
               active:scale-95 transition-all flex items-center justify-center gap-2">
        <span class="material-symbols-outlined fill-icon">home</span>
        خانه
      </button>
    </div>
  </main>

  ${confettiScript}
</div>`;
}
