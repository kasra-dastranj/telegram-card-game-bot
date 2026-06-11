// screens/profile.js — پروفایل کاربر

function renderProfile(state) {
  const p = state.profile;

  if (!p) {
    return `
<div class="min-h-screen flex items-center justify-center">
  <div class="text-on-surface-variant font-body-md">در حال بارگذاری...</div>
</div>`;
  }

  const winRate = p.stats && p.stats.total_fights > 0
    ? Math.round((p.stats.wins / p.stats.total_fights) * 100)
    : 0;

  const xpPercent = p.xp_to_next_level > 0
    ? Math.min(100, Math.round((p.current_xp / p.xp_to_next_level) * 100))
    : 0;

  const tierColors = {
    Bronze: "tertiary", Silver: "outline", Gold: "secondary",
    Platinum: "primary", Diamond: "rarity-epic", Master: "rarity-legend",
    Grandmaster: "rarity-rare"
  };
  const tierColor = tierColors[p.current_tier] || "secondary";

  return `
<div class="min-h-screen flex flex-col pb-20">
  <!-- Header -->
  <header class="fixed top-0 w-full z-50 bg-surface/80 backdrop-blur-xl border-b border-white/10 flex justify-between items-center px-[16px] py-4">
    <div class="flex items-center gap-3">
      <button data-action="go_home" class="text-on-surface-variant hover:text-primary transition-colors active:scale-95">
        <span class="material-symbols-outlined">arrow_back</span>
      </button>
      <div class="font-headline-md text-headline-md text-primary uppercase">Profile</div>
    </div>
  </header>

  <main class="pt-[80px] px-[16px] flex flex-col gap-5">
    <!-- User Info -->
    <section class="bg-surface-card border border-white/10 rounded-xl p-5 flex items-center gap-4 mt-4">
      <div class="w-16 h-16 rounded-full bg-primary-container/20 border-2 border-primary-container flex items-center justify-center">
        <span class="material-symbols-outlined text-[36px] text-primary fill-icon">person</span>
      </div>
      <div class="flex-1">
        <h2 class="font-headline-md text-headline-md text-text-primary">${p.first_name || 'کاربر'}</h2>
        ${p.username ? `<p class="font-body-md text-body-md text-on-surface-variant">@${p.username}</p>` : ''}
        <div class="flex items-center gap-2 mt-1">
          <span class="font-label-caps text-label-caps text-${tierColor} bg-${tierColor}/10 px-2 py-0.5 rounded">${p.current_tier}</span>
          <span class="font-label-caps text-label-caps text-outline">LEVEL ${p.level}</span>
        </div>
      </div>
    </section>

    <!-- Stats Row -->
    <section class="grid grid-cols-3 gap-3">
      ${[
        { label: "قلب", value: `${p.hearts}/${p.max_hearts}`, icon: "favorite", color: "rarity-rare" },
        { label: "سکه", value: p.coins.toLocaleString(), icon: "monetization_on", color: "secondary" },
        { label: "امتیاز", value: p.total_score, icon: "stars", color: "primary" },
      ].map(s => `
      <div class="bg-surface-card border border-white/5 rounded-xl p-3 text-center">
        <span class="material-symbols-outlined text-${s.color} fill-icon text-[24px]">${s.icon}</span>
        <div class="font-stat-numeric text-stat-numeric text-text-primary mt-1">${s.value}</div>
        <div class="font-label-caps text-label-caps text-outline text-[10px] mt-0.5">${s.label}</div>
      </div>`).join('')}
    </section>

    <!-- XP Progress -->
    <section class="bg-surface-card border border-white/5 rounded-xl p-4">
      <div class="flex justify-between items-center mb-2">
        <span class="font-label-caps text-label-caps text-outline uppercase">تجربه (XP)</span>
        <span class="font-stat-numeric text-stat-numeric text-primary">${p.current_xp} / ${p.xp_to_next_level}</span>
      </div>
      <div class="w-full h-2 bg-surface rounded-full overflow-hidden">
        <div class="h-full progress-bar-fill rounded-full transition-all" style="width:${xpPercent}%"></div>
      </div>
    </section>

    <!-- Fight Stats -->
    <section class="bg-surface-card border border-white/5 rounded-xl p-5">
      <h3 class="font-headline-sm text-headline-sm text-on-surface-variant mb-4 uppercase">آمار نبردها</h3>
      <div class="grid grid-cols-2 gap-3">
        ${[
          { label: "کل مبارزات", value: p.stats.total_fights },
          { label: "نرخ برد", value: winRate + "%" },
          { label: "Solo", value: p.stats.solo_fights },
          { label: "Solo برد", value: p.stats.solo_wins },
          { label: "PvP", value: p.stats.pvp_fights },
          { label: "PvP برد", value: p.stats.pvp_wins },
        ].map(s => `
        <div class="bg-surface-container-low rounded-lg p-3 border border-white/5">
          <div class="font-stat-numeric text-headline-md text-text-primary">${s.value}</div>
          <div class="font-label-caps text-label-caps text-outline text-[11px] mt-0.5">${s.label}</div>
        </div>`).join('')}
      </div>
    </section>

    <!-- Best Card -->
    ${p.best_card ? `
    <section class="bg-surface-card border border-secondary/20 rounded-xl p-4">
      <h3 class="font-label-caps text-label-caps text-outline mb-3 uppercase">بهترین کارت</h3>
      <div class="flex items-center gap-4">
        <div class="w-14 h-14 rounded-xl bg-surface-container-high flex items-center justify-center">
          ${p.best_card.image_path
            ? `<img src="${p.best_card.image_path}" alt="${p.best_card.name}" class="w-full h-full object-cover rounded-xl"/>`
            : `<span class="material-symbols-outlined text-[32px] text-outline fill-icon">person</span>`}
        </div>
        <div>
          <div class="font-headline-sm text-headline-sm text-text-primary">${p.best_card.name}</div>
          <div class="font-label-caps text-label-caps text-secondary uppercase">${p.best_card.rarity}</div>
        </div>
      </div>
    </section>` : ''}
  </main>

  <!-- Bottom Nav -->
  <nav class="fixed bottom-0 w-full z-50 rounded-t-xl bg-surface-container border-t border-white/5 shadow-[0_-4px_20px_rgba(0,0,0,0.5)] flex justify-around items-center h-16 px-[12px]">
    <button data-action="go_home" class="flex flex-col items-center justify-center text-outline hover:text-primary transition-all">
      <span class="material-symbols-outlined">sports_esports</span>
      <span class="font-label-caps text-label-caps mt-1">Arena</span>
    </button>
    <button class="flex flex-col items-center justify-center text-secondary drop-shadow-[0_0_8px_rgba(240,192,64,0.6)]">
      <span class="material-symbols-outlined fill-icon">person</span>
      <span class="font-label-caps text-label-caps mt-1">Profile</span>
    </button>
    <button data-action="go_leaderboard" class="flex flex-col items-center justify-center text-outline hover:text-primary transition-all">
      <span class="material-symbols-outlined">military_tech</span>
      <span class="font-label-caps text-label-caps mt-1">Rank</span>
    </button>
  </nav>
</div>`;
}
