// screens/mode_select.js — صفحه اصلی

function renderModeSelect(state) {
  const profile = state.profile;
  const hearts = profile ? profile.hearts : '?';
  const coins = profile ? profile.coins.toLocaleString('fa-IR') : '?';
  const name = profile ? profile.first_name : '';
  const level = profile ? profile.level : '?';
  const tier = profile ? profile.current_tier : '';

  return `
<div class="min-h-screen flex flex-col pb-20">
  <!-- Header -->
  <header class="fixed top-0 w-full z-50 bg-surface/80 backdrop-blur-xl border-b border-white/10 shadow-[0_0_15px_rgba(123,94,234,0.3)] flex justify-between items-center px-[16px] py-4">
    <div class="flex items-center gap-3">
      <div class="font-headline-lg text-headline-lg font-bold tracking-wider text-primary italic">TelBattle</div>
      ${name ? `<span class="font-label-caps text-label-caps text-on-surface-variant uppercase">${name}</span>` : ''}
    </div>
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-1 bg-surface-container px-3 py-1 rounded-full border border-white/10">
        <span class="material-symbols-outlined text-rarity-rare fill-icon text-[16px]">favorite</span>
        <span class="font-stat-numeric text-stat-numeric text-rarity-rare">${hearts}</span>
      </div>
      <div class="flex items-center gap-2 bg-surface-container-high px-3 py-1 rounded-full border border-white/10">
        <span class="material-symbols-outlined text-secondary fill-icon text-[18px]">monetization_on</span>
        <span class="font-stat-numeric text-stat-numeric text-secondary">${coins}</span>
      </div>
    </div>
  </header>

  <!-- Content -->
  <main class="pt-[80px] px-[16px] flex flex-col gap-6">
    <!-- Hero Section -->
    <section class="mt-4 text-center">
      <h1 class="font-headline-lg text-headline-lg text-primary drop-shadow-[0_0_10px_rgba(203,190,255,0.3)] mb-2">نبرد افسانه‌ها</h1>
      ${level !== '?' ? `<div class="inline-flex items-center gap-2 bg-surface-container px-4 py-1 rounded-full border border-white/10">
        <span class="font-label-caps text-label-caps text-on-surface-variant">LEVEL ${level}</span>
        <span class="w-1 h-1 rounded-full bg-outline-variant"></span>
        <span class="font-label-caps text-label-caps text-secondary">${tier}</span>
      </div>` : ''}
    </section>

    <!-- Solo Mode Card -->
    <section class="bg-surface-card border border-primary-container/30 rounded-xl p-5 relative overflow-hidden shadow-[0_0_25px_rgba(123,94,234,0.15)]">
      <div class="absolute inset-0 bg-gradient-to-br from-primary-container/10 to-transparent pointer-events-none"></div>
      <div class="flex items-start gap-4 mb-4">
        <div class="w-14 h-14 rounded-xl bg-primary-container/20 border border-primary-container/40 flex items-center justify-center">
          <span class="material-symbols-outlined text-primary fill-icon text-[32px]">sports_esports</span>
        </div>
        <div>
          <h2 class="font-headline-md text-headline-md text-text-primary mb-1">Solo vs آسو</h2>
          <p class="font-body-md text-body-md text-on-surface-variant">با خدای TelBattle مبارزه کن</p>
        </div>
      </div>
      <button data-action="go_aso_select"
        class="w-full bg-primary-container text-on-primary-container font-button-label text-button-label uppercase py-3 rounded-lg shadow-[0_0_20px_rgba(123,94,234,0.4)] active:scale-95 transition-transform">
        شروع نبرد
      </button>
    </section>

    <!-- PvP Coming Soon -->
    <section class="bg-surface-card border border-white/5 rounded-xl p-5 relative overflow-hidden opacity-60">
      <div class="flex items-start gap-4">
        <div class="w-14 h-14 rounded-xl bg-surface-container border border-white/10 flex items-center justify-center">
          <span class="material-symbols-outlined text-outline fill-icon text-[32px]">swords</span>
        </div>
        <div>
          <h2 class="font-headline-md text-headline-md text-on-surface-variant mb-1">PvP Arena</h2>
          <p class="font-body-md text-body-md text-outline">به زودی...</p>
        </div>
      </div>
    </section>
  </main>

  <!-- Bottom Nav -->
  <nav class="fixed bottom-0 w-full z-50 rounded-t-xl bg-surface-container border-t border-white/5 shadow-[0_-4px_20px_rgba(0,0,0,0.5)] flex justify-around items-center h-16 px-[12px]">
    <button class="flex flex-col items-center justify-center text-secondary drop-shadow-[0_0_8px_rgba(240,192,64,0.6)]">
      <span class="material-symbols-outlined fill-icon">sports_esports</span>
      <span class="font-label-caps text-label-caps mt-1">Arena</span>
    </button>
    <button data-action="go_profile" class="flex flex-col items-center justify-center text-outline hover:text-primary transition-all">
      <span class="material-symbols-outlined">person</span>
      <span class="font-label-caps text-label-caps mt-1">Profile</span>
    </button>
    <button data-action="go_leaderboard" class="flex flex-col items-center justify-center text-outline hover:text-primary transition-all">
      <span class="material-symbols-outlined">military_tech</span>
      <span class="font-label-caps text-label-caps mt-1">Rank</span>
    </button>
  </nav>
</div>`;
}
